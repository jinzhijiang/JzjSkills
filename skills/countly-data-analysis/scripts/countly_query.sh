#!/usr/bin/env bash
# Countly Read API helper (self-hosted analytics.jzj.plus).
# Requires: bash, curl, python3.
#
# Usage:
#   countly_query.sh list
#   countly_query.sh event <name> [period]
#   countly_query.sh views [--period 30days] [--limit 100]
#   countly_query.sh summary [period]
#   countly_query.sh crash <dashboard-url-or-crash-group-id>
#
# Credentials resolve per project (see _project_config below):
#   ~/.config/ai-ignore-config/<项目名>/countly.env
# Override with --config PATH, $COUNTLY_CONFIG, or COUNTLY_TOKEN/COUNTLY_APP_ID env vars.
#
# period: hour | yesterday | 7days | 30days | 60days | month  (default: 30days)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_FILE=""

BASE="https://analytics.jzj.plus/o"
APP_ID=""
TOKEN=""

_load_env_file() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" || "$line" != *=* ]] && continue
    local key="${line%%=*}"
    local val="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    val="${val#"${val%%[![:space:]]*}"}"
    val="${val%"${val##*[![:space:]]}"}"
    val="${val%\"}"; val="${val#\"}"
    val="${val%\'}"; val="${val#\'}"
    if [[ -n "$key" && -z "${!key:-}" ]]; then
      export "${key}=${val}"
    fi
  done < "$file"
}

# 凭据按**项目**隔离：一个 Countly 实例下挂着多个 App，配置若共用一份，
# 从 A 项目跑脚本会静默查到 B 项目的数据——数据看着正常但不是你要的那个应用，
# 比报错难查得多。项目名取 git 根目录名（不在 git 仓库里则退回当前目录名）。
_project_name() {
  local root
  root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  [[ -n "$root" ]] || root="$PWD"
  basename "$root"
}

_project_config() {
  echo "${HOME}/.config/ai-ignore-config/$(_project_name)/countly.env"
}

_load_config() {
  if [[ -n "$CONFIG_FILE" ]]; then
    _load_env_file "$CONFIG_FILE"
  else
    # 显式的 $COUNTLY_CONFIG 优先于按项目名推断，方便 CI 或临时切 App。
    CONFIG_FILE="${COUNTLY_CONFIG:-$(_project_config)}"
    _load_env_file "$CONFIG_FILE"
  fi
  BASE="${COUNTLY_BASE:-https://analytics.jzj.plus/o}"
  APP_ID="${COUNTLY_APP_ID:-}"
  TOKEN="${COUNTLY_TOKEN:-}"
}

_require_credentials() {
  if [[ -z "$TOKEN" ]]; then
    local proj expected
    proj="$(_project_name)"
    expected="$(_project_config)"
    cat >&2 <<EOF
error: COUNTLY_TOKEN not configured for project "${proj}".
  First-time setup:
    mkdir -p "$(dirname "${expected}")"
    cp "${SKILL_DIR}/config.example.env" "${expected}"
    # then fill COUNTLY_APP_ID (Dashboard → App Settings) and COUNTLY_TOKEN
  Looked for: ${CONFIG_FILE}
EOF
    exit 2
  fi
  if [[ -z "$APP_ID" ]]; then
    echo "error: COUNTLY_APP_ID not configured in ${CONFIG_FILE} (see config.example.env)" >&2
    exit 2
  fi
}

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 is required for JSON parsing" >&2
  exit 2
fi

# Common curl: GET /o with method + auth_token + app_id + extra urlencoded args.
_query() {
  local method="$1"; shift
  local args=(--data-urlencode "method=${method}"
              --data-urlencode "auth_token=${TOKEN}"
              --data-urlencode "app_id=${APP_ID}")
  while [[ $# -gt 0 ]]; do
    args+=(--data-urlencode "$1")
    shift
  done
  curl -sS -G "${BASE}" "${args[@]}"
}

_die_if_error() {
  python3 -c "
import json, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw)
except Exception:
    print(raw)
    sys.exit(1)
if isinstance(data, dict) and 'result' in data and isinstance(data['result'], str) and len(data) == 1:
    print(f'error: {data[\"result\"]}', file=sys.stderr)
    sys.exit(3)
print(raw)
"
}

cmd_list() {
  _query get_events | _die_if_error | python3 -c "
import json, sys
data = json.load(sys.stdin)
events = sorted(data.get('list', []))
segments = data.get('segments', {})
print(f'Registered events ({len(events)}):')
for ev in events:
    seg = segments.get(ev) or []
    seg = [s for s in seg if s]
    if seg:
        print(f'  - {ev:30}  segments: {seg}')
    else:
        print(f'  - {ev}')
limits = data.get('limits', {})
if limits:
    print()
    print('limits:', limits)
"
}

# Sum yearly totals from a Countly events tree.
# The response is shaped { "<year>": { "c": N, "<month>": { "c": M, "<day>": { ... } } }, "meta": {...} }
# Each level repeats the same total via its own "c". Summing all "c" naively over-counts 4x
# (year + month + day + hour). Taking only the top-level (year) "c" avoids this.
# NOTE: Countly's `period` is currently ignored on /o?method=events for this instance;
# the response always contains full history. Filter by period in client if needed.
_sum_c_py='
import json, sys
data = json.load(sys.stdin)
total = 0
if isinstance(data, dict):
    for k, v in data.items():
        if k in ("meta", "eventName"):
            continue
        if isinstance(v, dict) and isinstance(v.get("c"), (int, float)):
            total += int(v["c"])
print(total)
'

# Sum counts only within a specific [start_year, start_month, start_day] .. [end_*] inclusive window.
# Reads window from env CLY_FROM / CLY_TO as "YYYY-MM-DD". Used for true period filtering.
_sum_window_py='
import json, os, sys, datetime
data = json.load(sys.stdin)
def parse(s):
    if not s: return None
    return datetime.date.fromisoformat(s)
start = parse(os.environ.get("CLY_FROM"))
end = parse(os.environ.get("CLY_TO"))
total = 0
for ys, ydata in data.items():
    if ys in ("meta", "eventName") or not isinstance(ydata, dict):
        continue
    if not ys.isdigit(): continue
    year = int(ys)
    for ms, mdata in ydata.items():
        if ms == "c" or not isinstance(mdata, dict) or not ms.isdigit():
            continue
        month = int(ms)
        for ds, ddata in mdata.items():
            if ds == "c" or not isinstance(ddata, dict) or not ds.isdigit():
                continue
            day = int(ds)
            try:
                d = datetime.date(year, month, day)
            except ValueError:
                continue
            if start and d < start: continue
            if end and d > end: continue
            c = ddata.get("c")
            if isinstance(c, (int, float)):
                total += int(c)
print(total)
'

cmd_event() {
  local name="${1:-}"
  if [[ -z "${name}" ]]; then
    echo "usage: countly_query.sh event <name>" >&2
    echo "  (Countly's /o?method=events ignores 'period' on this instance," >&2
    echo "   the response always contains full history. Use 'range' for a real time window.)" >&2
    exit 2
  fi
  local raw
  raw=$(_query events "event=${name}")
  local total
  total=$(echo "${raw}" | python3 -c "${_sum_c_py}" 2>/dev/null || echo "?")
  echo "event:        ${name}"
  echo "total (all):  ${total}"
  echo
  echo "daily breakdown (recent):"
  echo "${raw}" | python3 -c "
import json, sys
d = json.load(sys.stdin)
rows = []
for ys, ydata in d.items():
    if ys in ('meta','eventName') or not isinstance(ydata, dict) or not ys.isdigit(): continue
    for ms, mdata in ydata.items():
        if ms == 'c' or not isinstance(mdata, dict) or not ms.isdigit(): continue
        for ds, ddata in mdata.items():
            if ds == 'c' or not isinstance(ddata, dict) or not ds.isdigit(): continue
            rows.append((int(ys), int(ms), int(ds), int(ddata.get('c', 0))))
rows.sort()
for y,m,d_,c in rows[-14:]:
    print(f'  {y:04d}-{m:02d}-{d_:02d}  c={c}')
"
}

cmd_range() {
  local name="${1:-}"
  local from="${2:-}"
  local to="${3:-}"
  if [[ -z "${name}" || -z "${from}" || -z "${to}" ]]; then
    echo "usage: countly_query.sh range <name> <YYYY-MM-DD> <YYYY-MM-DD>" >&2
    exit 2
  fi
  local raw
  raw=$(_query events "event=${name}")
  local total
  total=$(CLY_FROM="${from}" CLY_TO="${to}" python3 -c "${_sum_window_py}" <<< "${raw}" 2>/dev/null || echo "?")
  echo "event: ${name}"
  echo "range: ${from} .. ${to}"
  echo "count: ${total}"
}

# Page views. NOTE: method=views 必须带 action，否则返回 {"data":[]}——
# 空 action 查的是「指定视图的时间序列」，要配套 selectedViews=[{view,action}]，
# 不传当然是空的。曾有人据此误判「视图没上报」，别再踩。
#   action=getTable   视图列表 + 指标（视图名在 view 字段，_id 是 ObjectId）
#   action=getTotals  Total / Unique 汇总
cmd_views() {
  local period="30days" limit="100"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --period) period="${2:-}"; shift 2 ;;
      --limit)  limit="${2:-}";  shift 2 ;;
      *) echo "usage: countly_query.sh views [--period 30days] [--limit 100]" >&2; exit 2 ;;
    esac
  done

  echo "app_id: ${APP_ID}"
  echo "period: ${period}"
  echo

  _query views "action=getTotals" "period=${period}" | _die_if_error | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('totals:  views={}  unique={}  sessions={}  bounce={}'.format(
    d.get('t', 0), d.get('uvc', 0), d.get('s', 0), d.get('b', 0)))
"
  echo
  _query views "action=getTable" "period=${period}" \
               "iDisplayStart=0" "iDisplayLength=${limit}" | _die_if_error | python3 -c "
import json, sys
d = json.load(sys.stdin)
rows = d.get('aaData') or []
total = d.get('iTotalRecords', len(rows))
print(f'views ({len(rows)} shown of {total}):')
if not rows:
    print('  (none)')
for r in sorted(rows, key=lambda x: x.get('t', 0), reverse=True):
    avg = r.get('d-calc', 0)
    avg = round(avg, 1) if isinstance(avg, (int, float)) else 0
    print('  {:<32} total={:<8} unique={:<8} avg={}s'.format(
        r.get('view', r.get('_id', '?')), r.get('t', 0), r.get('uvc', 0), avg))
"
}

cmd_crash() {
  local input="${1:-}"
  if [[ -z "${input}" ]]; then
    echo "usage: countly_query.sh crash <dashboard-url-or-crash-group-id>" >&2
    exit 2
  fi

  local crash_id="${input}"
  if [[ "${crash_id}" == *"/crashes/"* ]]; then
    crash_id="${crash_id##*/crashes/}"
  fi
  crash_id="${crash_id%%[\?#/]*}"

  if [[ -z "${crash_id}" ]]; then
    echo "error: could not parse crash group id from: ${input}" >&2
    exit 2
  fi

  # method=crashes&group=<id> returns the full crash-group detail document
  # (per-version / per-device / per-OS breakdowns + resource stats + recent
  # individual reports), unlike the bare crashes list which only has summary rows.
  _query crashes "group=${crash_id}" | python3 -c '
import datetime, html, json, sys

crash_id = sys.argv[1]
data = json.load(sys.stdin)

# Error payloads look like {"result": "..."} or lack the core crash fields.
if not isinstance(data, dict) or "error" not in data or "name" not in data:
    msg = data.get("result") if isinstance(data, dict) else None
    print(f"error: crash group detail not found: {crash_id}", file=sys.stderr)
    if msg:
        print(f"  server: {msg}", file=sys.stderr)
    sys.exit(3)

def fmt_ts(value):
    if not isinstance(value, (int, float)) or value <= 0:
        return "-"
    return datetime.datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")

def ver_key(k):
    # Countly stores app versions as "3:1:0" meaning 3.1.0.
    return str(k).replace(":", ".")

def top_counts(d, limit=8, transform=str):
    if not isinstance(d, dict) or not d:
        return "-"
    items = [(k, v) for k, v in d.items() if isinstance(v, (int, float))]
    items.sort(key=lambda kv: kv[1], reverse=True)
    shown = items[:limit]
    extra = len(items) - len(shown)
    s = ", ".join(f"{transform(k)}={v}" for k, v in shown)
    if extra > 0:
        s += f", (+{extra} more)"
    return s

def avg(stat):
    if isinstance(stat, dict) and stat.get("count"):
        return round(stat["total"] / stat["count"], 1)
    return None

print("crash_id:       {}".format(crash_id))
print("name:           {}".format(html.unescape(str(data.get("name", "")))))
print("os:             {}".format(data.get("os", "-")))
print("latest_version: {}".format(data.get("latest_version", "-")))
print("reports:        {}".format(data.get("reports", "-")))
print("users:          {}".format(data.get("users", "-")))
print("nonfatal:       {}".format(data.get("nonfatal", "-")))
print("resolved:       {}".format(data.get("is_resolved", "-")))
print("first_seen:     {}".format(fmt_ts(data.get("startTs"))))
print("last_seen:      {}".format(fmt_ts(data.get("lastTs"))))
print("app_versions:   {}".format(top_counts(data.get("app_version"), transform=ver_key)))
print("os_versions:    {}".format(top_counts(data.get("os_version"))))
print("devices:        {}".format(top_counts(data.get("device"))))
print("resolutions:    {}".format(top_counts(data.get("resolution"))))
print("cpu:            {}".format(top_counts(data.get("cpu"))))
print("orientation:    {}".format(top_counts(data.get("orientation"))))
print("root:           {}".format(top_counts(data.get("root"))))
print("muted:          {}".format(top_counts(data.get("muted"))))
print("online:         {}".format(top_counts(data.get("online"))))
print("background:     {}".format(top_counts(data.get("background"))))

res = []
for label, key, unit in (("ram", "ram", "%"), ("disk", "disk", "%"),
                         ("battery", "bat", "%"), ("run", "run", "s")):
    a = avg(data.get(key))
    if a is not None:
        res.append(f"{label}~{a}{unit}")
if res:
    print("resources(avg): {}".format(", ".join(res)))

reports = data.get("data")
if isinstance(reports, list) and reports:
    print()
    print("recent reports (latest {}):".format(min(5, len(reports))))
    for r in sorted(reports, key=lambda x: x.get("ts", 0), reverse=True)[:5]:
        print("  {}  v{}  Android {}  {}  bat={}%".format(
            fmt_ts(r.get("ts")),
            r.get("app_version", "-"),
            r.get("os_version", "-"),
            r.get("device", "-"),
            r.get("bat", "-"),
        ))

print()
print("stack:")
print(html.unescape(str(data.get("error", ""))))
' "${crash_id}"
}

# Pull event constants from lib/core/services/countly_service.dart
# (matches: static const String eventXxx = '...';).
_code_events() {
  local file="lib/core/services/countly_service.dart"
  if [[ ! -f "${file}" ]]; then
    echo "warn: ${file} not found; summary will only show server data" >&2
    return
  fi
  python3 - "${file}" <<'PY'
import re, sys, pathlib
text = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')
events = re.findall(r"static const String\s+event\w+\s*=\s*'([^']+)'", text)
for e in sorted(set(events)):
    print(e)
PY
}

cmd_summary() {
  # Optional: summary [--from YYYY-MM-DD --to YYYY-MM-DD]
  local from="" to=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --from) from="$2"; shift 2 ;;
      --to)   to="$2";   shift 2 ;;
      *) echo "unknown summary arg: $1" >&2; exit 2 ;;
    esac
  done

  local list_raw
  list_raw=$(_query get_events)
  local server_events
  server_events=$(echo "${list_raw}" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for e in d.get('list', []):
    print(e)
")
  if [[ -z "${server_events}" ]]; then
    echo "error: server returned no events (check token / app_id)" >&2
    echo "${list_raw}" >&2
    exit 3
  fi

  local code_events
  code_events=$(_code_events)

  if [[ -n "${from}" && -n "${to}" ]]; then
    echo "Countly summary (range ${from} .. ${to})"
  else
    echo "Countly summary (all history; Countly /o?method=events ignores period)"
  fi
  echo "================================================================"
  printf "%-32s %12s  %-7s  %-9s\n" "event" "count" "in_code" "in_server"
  printf -- "----------------------------------------------------------------\n"

  union=$(printf "%s\n%s" "${server_events}" "${code_events}" | sort -u | grep -v '^$' || true)

  while IFS= read -r ev; do
    [[ -z "${ev}" ]] && continue
    local in_code="-"
    local in_srv="-"
    grep -qx "${ev}" <<< "${code_events}" && in_code="yes"
    grep -qx "${ev}" <<< "${server_events}" && in_srv="yes"
    local raw count="?"
    if [[ "${in_srv}" == "yes" ]]; then
      raw=$(_query events "event=${ev}" 2>/dev/null || echo '{}')
      if [[ -n "${from}" && -n "${to}" ]]; then
        count=$(CLY_FROM="${from}" CLY_TO="${to}" python3 -c "${_sum_window_py}" <<< "${raw}" 2>/dev/null || echo "?")
      else
        count=$(echo "${raw}" | python3 -c "${_sum_c_py}" 2>/dev/null || echo "?")
      fi
    else
      count="0"
    fi
    printf "%-32s %12s  %-7s  %-9s\n" "${ev}" "${count}" "${in_code}" "${in_srv}"
  done <<< "${union}"

  echo
  echo "legend:"
  echo "  in_code=yes,in_server=no   -> tracked in code but server never received (verify trigger / consent / platform)"
  echo "  in_code=no, in_server=yes  -> server has events not declared in code (legacy / test residue)"
}

main() {
  # --config 在任意位置都生效。以前只在子命令**之前**解析（碰到子命令就 break），
  # 写成 `list --config x.env` 时它会被当成子命令参数静默丢掉，于是回落到默认配置、
  # 查了另一个 App 的数据还看不出来——比报错难查得多。
  local args=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --config)
        CONFIG_FILE="${2:-}"
        if [[ -z "$CONFIG_FILE" ]]; then
          echo "error: --config requires a path" >&2
          exit 2
        fi
        shift 2
        ;;
      --config=*)
        CONFIG_FILE="${1#--config=}"
        shift
        ;;
      *)
        args+=("$1")
        shift
        ;;
    esac
  done
  set -- "${args[@]+"${args[@]}"}"

  if [[ -n "$CONFIG_FILE" && ! -f "$CONFIG_FILE" ]]; then
    echo "error: --config file not found: ${CONFIG_FILE}" >&2
    exit 2
  fi

  _load_config
  _require_credentials

  local sub="${1:-}"
  case "${sub}" in
    list)     shift; cmd_list "$@" ;;
    event)    shift; cmd_event "$@" ;;
    range)    shift; cmd_range "$@" ;;
    views)    shift; cmd_views "$@" ;;
    crash)    shift; cmd_crash "$@" ;;
    summary)  shift; cmd_summary "$@" ;;
    "" | -h | --help)
      cat <<USAGE
Countly Read API helper (analytics.jzj.plus)

Commands:
  list                                    List registered events + their segmentation keys
  event <name>                            Show total count + recent daily breakdown (all history)
  range <name> <YYYY-MM-DD> <YYYY-MM-DD>  Count an event in an inclusive date window
  views [--period 30days] [--limit 100]   List page views (name / total / unique / avg duration)
  crash <dashboard-url-or-crash-group-id> Fetch crash group summary + stack trace
  summary [--from YYYY-MM-DD --to YYYY-MM-DD]
                                          Cross-check code event constants with server data;
                                          when --from/--to omitted shows all-history totals

Options:
  --config PATH   Credentials file. Accepted anywhere on the command line,
                  before or after the subcommand. Also honours \$COUNTLY_CONFIG.
                  Default resolves per project:
                    ~/.config/ai-ignore-config/<git-repo-name>/countly.env
                  One Countly instance hosts several apps, so credentials are kept
                  per project — a shared default would silently query the wrong app.

NOTE on views: /o?method=views REQUIRES an 'action' param. Without it the server returns
      {"data":[]} — that is a malformed query, NOT "no views were recorded". The 'views'
      subcommand uses action=getTable / getTotals. View names live in the 'view' field
      of each row ('_id' is a Mongo ObjectId).

NOTE: This Countly instance ignores ?period= on /o?method=events; the response always
      contains the full per-day breakdown. The script filters client-side via 'range' /
      summary --from/--to to give a true time window.

Credentials (see skill config.example.env):
  COUNTLY_TOKEN     Read API auth_token or api_key
  COUNTLY_APP_ID    App id
  COUNTLY_BASE      API base (default: https://analytics.jzj.plus/o)
USAGE
      ;;
    *)
      echo "unknown subcommand: ${sub}" >&2
      exit 2
      ;;
  esac
}

main "$@"

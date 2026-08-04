#!/usr/bin/env python3
"""校验 commit message 是否符合 git-cz 契约。

只用 python3 标准库,不需要 node / npm —— Flutter、Java、HarmonyOS 等非 Node 项目
也能用同一套规则把关。配置读的是 git-cz 自己的 changelog.config.*,
和交互式 `git cz` 共用一份事实来源。

用法:
    check_commit_msg.py [--file <路径> | --message <文本> | -]  # 默认从 .git/COMMIT_EDITMSG 读
    check_commit_msg.py install-hook [--repo <目录>] [--force]
    check_commit_msg.py show-config  [--repo <目录>]

退出码: 0 通过(可能带警告) / 1 校验不通过 / 2 用法或内部错误
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

# git-cz 4.9.0 lib/defaults.js 的默认值,找不到配置文件时兜底。
DEFAULT_CONFIG = {
    "disableEmoji": False,
    "format": "{type}{scope}: {emoji}{subject}",
    "list": ["test", "feat", "fix", "chore", "docs", "refactor", "style", "ci", "perf"],
    "maxMessageLength": 64,
    "minMessageLength": 3,
    "questions": ["type", "scope", "subject", "body", "breaking", "issues"],
    "scopes": [],
    "types": {
        "chore": {"description": "Build process or auxiliary tool changes", "emoji": "🤖"},
        "ci": {"description": "CI related changes", "emoji": "🎡"},
        "docs": {"description": "Documentation only changes", "emoji": "✏️"},
        "feat": {"description": "A new feature", "emoji": "🎸"},
        "fix": {"description": "A bug fix", "emoji": "🐛"},
        "perf": {"description": "A code change that improves performance", "emoji": "⚡️"},
        "refactor": {"description": "A code change that neither fixes a bug or adds a feature", "emoji": "💡"},
        "release": {"description": "Create a release commit", "emoji": "🏹"},
        "style": {"description": "Markup, white-space, formatting, missing semi-colons...", "emoji": "💄"},
        "test": {"description": "Adding missing tests", "emoji": "💍"},
    },
    "breakingChangePrefix": "🧨 ",
    "closedIssueMessage": "Closes: ",
    "closedIssuePrefix": "✅ ",
}

# git-cz lib/getConfig.js 的查找顺序,自 git 根目录起逐级向上。
CONFIG_FILES = (".git-cz.json", "changelog.config.js", "changelog.config.cjs", "changelog.config.json")

MAX_LINE_WIDTH = 72  # git-cz 正文/页脚的换行宽度,标题也按同一列宽把关
SKIP_PREFIXES = ("Merge ", "Revert ", "fixup!", "squash!", "amend!")
SCISSORS = "# ------------------------ >8 ------------------------"


# --------------------------------------------------------------------------- 工具

def display_width(text: str) -> int:
    """终端列宽:CJK / emoji 按 2 列,组合符与变体选择符按 0 列。"""
    width = 0
    for ch in text:
        if unicodedata.combining(ch) or ch in ("️", "︎", "‍"):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def normalize_emoji(text: str) -> str:
    """去掉变体选择符再比较,免得 ✏ 与 ✏️ 被判成两个字符。"""
    return text.replace("️", "").replace("︎", "")


def git_root(start: Path) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        return Path(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def git_dir(start: Path) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--absolute-git-dir"],
            capture_output=True, text=True, check=True,
        )
        return Path(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


# --------------------------------------------------------------------------- 配置

def load_js_config(path: Path) -> dict | None:
    """求值 changelog.config.js:优先用 node,没有 node 就退回纯 python 解析。"""
    node = shutil.which("node")
    if node:
        script = "process.stdout.write(JSON.stringify(require(process.argv[1])))"
        try:
            out = subprocess.run(
                [node, "-e", script, str(path)],
                capture_output=True, text=True, check=True, timeout=20,
            )
            return json.loads(out.stdout)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return None
    return parse_module_exports(path.read_text(encoding="utf-8", errors="replace"))


def parse_module_exports(source: str) -> dict | None:
    """没有 node 时的兜底:把 `module.exports = { … }` 这种纯字面量转成 JSON 再解析。

    只认字面量(字符串 / 数字 / true / false / null / 数组 / 对象),
    碰到变量、函数、模板字符串等任何表达式一律返回 None,交给上层告警。
    """
    match = re.search(r"module\.exports\s*=\s*", source)
    if not match:
        return None
    body = _extract_object(_strip_js_comments(source[match.end():]))
    if body is None:
        return None
    converted = _js_literal_to_json(body)
    if converted is None:
        return None
    try:
        data = json.loads(converted)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _strip_js_comments(text: str) -> str:
    out: list[str] = []
    index, size, quote = 0, len(text), ""
    while index < size:
        char = text[index]
        if quote:
            out.append(char)
            if char == "\\" and index + 1 < size:
                out.append(text[index + 1])
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in "\"'`":
            quote = char
            out.append(char)
        elif char == "/" and index + 1 < size and text[index + 1] == "/":
            while index < size and text[index] != "\n":
                index += 1
            continue
        elif char == "/" and index + 1 < size and text[index + 1] == "*":
            index += 2
            while index + 1 < size and not (text[index] == "*" and text[index + 1] == "/"):
                index += 1
            index += 2
            continue
        else:
            out.append(char)
        index += 1
    return "".join(out)


def _extract_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth, index, quote = 0, start, ""
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
        elif char in "\"'`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
        index += 1
    return None


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "\\": "\\", "'": "'", '"': '"', "/": "/"}


def _js_literal_to_json(text: str) -> str | None:
    out: list[str] = []
    index, size, last = 0, len(text), ""
    while index < size:
        char = text[index]

        if char in "\"'":
            quote, cursor, buf = char, index + 1, []
            while cursor < size and text[cursor] != quote:
                if text[cursor] == "\\":
                    following = text[cursor + 1]
                    if following == "u":
                        buf.append(chr(int(text[cursor + 2:cursor + 6], 16)))
                        cursor += 6
                        continue
                    buf.append(_ESCAPES.get(following, following))
                    cursor += 2
                    continue
                buf.append(text[cursor])
                cursor += 1
            out.append(json.dumps("".join(buf), ensure_ascii=False))
            last, index = '"', cursor + 1
            continue

        if char == "`":
            return None  # 模板字符串可能含表达式,不猜

        if char.isalpha() or char in "_$":
            cursor = index
            while cursor < size and (text[cursor].isalnum() or text[cursor] in "_$"):
                cursor += 1
            word = text[index:cursor]
            probe = cursor
            while probe < size and text[probe] in " \t\r\n":
                probe += 1
            if probe < size and text[probe] == ":" and last in "{,":
                out.append(json.dumps(word))
                last = '"'
            elif word in ("true", "false", "null"):
                out.append(word)
                last = word[-1]
            else:
                return None  # 变量引用 / require(...) / 函数,放弃
            index = cursor
            continue

        if char == ",":  # 丢掉尾逗号
            probe = index + 1
            while probe < size and text[probe] in " \t\r\n":
                probe += 1
            if probe < size and text[probe] in "}]":
                index = probe
                continue

        if char in "();=+" and char not in ",:{}[]":
            return None  # 表达式,放弃

        out.append(char)
        if not char.isspace():
            last = char
        index += 1

    return "".join(out)


class Resolved:
    """一次配置解析的结果。unreadable 表示找到了配置但读不出来。"""

    def __init__(self, config: dict, source: Path | None, notes: list[str], unreadable: bool = False) -> None:
        self.config = config
        self.source = source
        self.notes = notes
        self.unreadable = unreadable


def find_overrides(start: Path) -> Resolved:
    """自 start 起逐级向上找配置,命中一个即停(与 git-cz 的查找顺序一致)。"""
    notes: list[str] = []
    directory = start.resolve()
    while True:
        for name in CONFIG_FILES:
            candidate = directory / name
            if not candidate.is_file():
                continue
            if candidate.suffix == ".json":
                try:
                    return Resolved(json.loads(candidate.read_text(encoding="utf-8")), candidate, notes)
                except json.JSONDecodeError as exc:
                    notes.append(f"{candidate} 不是合法 JSON({exc})")
                    return Resolved({}, candidate, notes, unreadable=True)
            data = load_js_config(candidate)
            if data is not None:
                return Resolved(data, candidate, notes)
            notes.append(
                f"读不出 {candidate}:本机没有 node,且该文件不是纯字面量(含变量/函数/模板字符串)。"
                "装个 node,或把配置改写成 .git-cz.json"
            )
            return Resolved({}, candidate, notes, unreadable=True)

        pkg = directory / "package.json"
        if pkg.is_file():
            try:
                changelog = json.loads(pkg.read_text(encoding="utf-8"))["config"]["commitizen"]["changelog"]
                if changelog:
                    return Resolved(changelog, pkg, notes)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        parent = directory.parent
        if parent == directory:
            return Resolved({}, None, notes)
        directory = parent


def load_config(repo: Path) -> Resolved:
    resolved = find_overrides(git_root(repo) or repo)
    if not isinstance(resolved.config, dict):
        resolved.notes.append(f"{resolved.source} 导出的不是对象,已忽略")
        resolved.config = {}
        resolved.unreadable = True
    resolved.config = {**DEFAULT_CONFIG, **resolved.config}
    return resolved


# --------------------------------------------------------------------------- 解析

TOKEN_RE = re.compile(r"\{(emoji|type|scope|subject)\}")


def build_header_re(fmt: str, *, emoji: str = "optional") -> re.Pattern[str]:
    """emoji: required(必须有) / absent(必须没有) / optional(有没有都行,单独捕获)。"""
    parts: list[str] = []
    pos = 0
    for match in TOKEN_RE.finditer(fmt):
        parts.append(re.escape(fmt[pos:match.start()]))
        token = match.group(1)
        if token == "emoji":
            parts.append({
                "required": r"(?P<emoji>\S+) ",
                "absent": r"",
                "optional": r"(?:(?P<emoji>\S+) )?",
            }[emoji])
        elif token == "type":
            parts.append(r"(?P<type>[A-Za-z][A-Za-z0-9_-]*)")
        elif token == "scope":
            parts.append(r"(?:\((?P<scope>[^()]*)\))?")
        else:
            parts.append(r"(?P<subject>.*)")
        pos = match.end()
    parts.append(re.escape(fmt[pos:]))
    return re.compile("^" + "".join(parts) + "$")


def example_header(config: dict) -> str:
    type_name = config["list"][0] if config.get("list") else "feat"
    emoji = config.get("types", {}).get(type_name, {}).get("emoji", "🎸")
    head = config.get("format", DEFAULT_CONFIG["format"])
    head = head.replace("{emoji}", "" if config.get("disableEmoji") else emoji + " ")
    head = head.replace("{scope}", "(scope)" if config.get("scopes") else "")
    return head.replace("{type}", type_name).replace("{subject}", "一句话描述这次改动")


def strip_comments(raw: str) -> str:
    if SCISSORS in raw:
        raw = raw.split(SCISSORS, 1)[0]
    lines = [line for line in raw.splitlines() if not line.startswith("#")]
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


# --------------------------------------------------------------------------- 校验

class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def validate(message: str, config: dict) -> Report:
    report = Report()
    body_text = strip_comments(message)

    if not body_text.strip():
        report.error("提交信息为空")
        return report

    lines = body_text.split("\n")
    header = lines[0]

    if header.startswith(SKIP_PREFIXES):
        return report  # merge / revert / fixup 由 git 生成,不套格式

    _validate_header(header, config, report)
    _validate_layout(lines, config, report)
    return report


def _validate_header(header: str, config: dict, report: Report) -> None:
    fmt = config.get("format") or DEFAULT_CONFIG["format"]
    types = config.get("types") or {}
    type_list = config.get("list") or list(types)
    disable_emoji = bool(config.get("disableEmoji"))

    owners = {normalize_emoji(spec.get("emoji", "")): name for name, spec in types.items() if spec.get("emoji")}

    # 依次按「带 emoji」「不带 emoji」「带一个不认识的前缀」去匹配,
    # 这样才能把「漏了 emoji」和「emoji 写错了」分开报,而不是把首个单词当成 emoji。
    match, emoji_state = None, "ok"
    if not disable_emoji:
        candidate = build_header_re(fmt, emoji="required").match(header)
        if candidate and normalize_emoji(candidate.group("emoji")) in owners:
            match = candidate
    if match is None:
        candidate = build_header_re(fmt, emoji="absent").match(header)
        if candidate:
            match, emoji_state = candidate, "ok" if disable_emoji else "missing"
    if match is None:
        candidate = build_header_re(fmt, emoji="optional").match(header)
        if candidate:
            match = candidate
            emoji_state = "unknown" if candidate.group("emoji") else "missing"

    if match is None:
        report.error(
            f"标题不符合格式 `{fmt}`\n"
            f"    实际: {header}\n"
            f"    期望: {example_header(config)}"
        )
        return

    groups = match.groupdict()
    type_name = groups.get("type") or ""
    scope = groups.get("scope")
    subject = groups.get("subject") or ""
    emoji = groups.get("emoji")

    # --- type
    if type_name not in types:
        report.error(f"未知类型 `{type_name}`;可用类型:{', '.join(type_list)}")
    elif type_name not in type_list:
        report.error(f"类型 `{type_name}` 未列入 config.list,交互式选不到它;可用类型:{', '.join(type_list)}")

    # --- emoji
    expected = types.get(type_name, {}).get("emoji", "?")
    if disable_emoji:
        if emoji and normalize_emoji(emoji) in owners:
            report.error(f"配置为 disableEmoji: true,标题不应带 emoji `{emoji}`")
    elif emoji_state == "missing":
        report.error(f"标题缺少 emoji,`{type_name}` 应为 `{expected}`")
    elif emoji_state == "unknown":
        report.error(f"标题开头的 `{emoji}` 不是本配置里的 emoji;`{type_name}` 应为 `{expected}`")
    elif emoji and normalize_emoji(emoji) != normalize_emoji(expected):
        owner = owners.get(normalize_emoji(emoji))
        hint = f",`{emoji}` 是 {owner} 的" if owner else ""
        report.error(f"emoji 与类型不匹配:`{type_name}` 应为 `{expected}`{hint}")

    # 形如 `feat: 🎸 主题` —— emoji 写在了冒号后面
    if not disable_emoji and subject:
        first = subject.split(" ", 1)[0]
        if normalize_emoji(first) in {normalize_emoji(t.get("emoji", "")) for t in types.values() if t.get("emoji")}:
            report.error(f"emoji 位置错误:按 `{fmt}` 应写在最前面,不是主题里")

    # --- scope
    scopes = config.get("scopes") or []
    if scope is not None:
        if not scope.strip():
            report.error("scope 为空括号,要么写内容要么整个去掉")
        elif scopes and scope not in scopes:
            report.error(f"未知 scope `{scope}`;可选:{', '.join(scopes)}")

    # --- subject
    min_len = int(config.get("minMessageLength", 3))
    max_len = int(config.get("maxMessageLength", 64)) - 3  # git-cz 给 emoji+空格 预留 3
    if subject != subject.strip():
        report.error("主题首尾有多余空格")
    stripped = subject.strip()
    if len(stripped) < min_len:
        report.error(f"主题太短(至少 {min_len} 个字符)")
    if len(stripped) > max_len:
        report.error(f"主题超长:{len(stripped)} 字符 > {max_len}(maxMessageLength {config.get('maxMessageLength')} - 3)")
    if stripped.endswith((".", "。", "!", "！", "?", "？")):
        report.error("主题结尾不要加标点(git-cz 会自动去掉英文句点)")
    if re.match(r"^[a-z]+(\([^()]*\))?\s*[:：]", stripped):
        report.error("主题里重复写了 type 前缀")

    width = display_width(header)
    if width > MAX_LINE_WIDTH:
        report.warn(f"标题 {width} 列 > {MAX_LINE_WIDTH} 列,建议压缩(中文一个字占 2 列)")


def _validate_layout(lines: list[str], config: dict, report: Report) -> None:
    if len(lines) == 1:
        return

    if lines[1].strip():
        report.error("标题与正文之间必须空一行")

    disable_emoji = bool(config.get("disableEmoji"))
    breaking_prefix = config.get("breakingChangePrefix", "🧨 ")
    closed_prefix = config.get("closedIssuePrefix", "✅ ")
    closed_message = config.get("closedIssueMessage", "Closes: ")

    for index, line in enumerate(lines[2:], start=3):
        width = display_width(line)
        if width > MAX_LINE_WIDTH:
            report.warn(f"第 {index} 行 {width} 列 > {MAX_LINE_WIDTH} 列,建议换行")

        low = line.lower()
        if low.startswith("breaking"):
            if not line.startswith("BREAKING CHANGE: "):
                report.error(f'第 {index} 行破坏性变更段必须以 "BREAKING CHANGE: " 开头(全大写、冒号后一个空格)')
            elif not disable_emoji and not line.startswith("BREAKING CHANGE: " + breaking_prefix):
                report.warn(f"第 {index} 行建议写成 `BREAKING CHANGE: {breaking_prefix}…`(与 git-cz 输出一致)")

        if closed_message.strip().lower() in low and "close" in low:
            expected = ("" if disable_emoji else closed_prefix) + closed_message
            if not line.startswith(expected):
                report.warn(f"第 {index} 行关闭 issue 建议写成 `{expected}#123`")


# --------------------------------------------------------------------------- 输出

def render(report: Report, header: str, strict: bool, use_json: bool) -> int:
    failed = bool(report.errors) or (strict and bool(report.warnings))

    if use_json:
        print(json.dumps({
            "ok": not failed,
            "errors": report.errors,
            "warnings": report.warnings,
            "header": header,
        }, ensure_ascii=False))
        return 1 if failed else 0

    for warning in report.warnings:
        print(f"⚠  {warning}", file=sys.stderr)
    for error in report.errors:
        print(f"✖  {error}", file=sys.stderr)

    if failed:
        print("\n提交信息不符合 git-cz 契约,已拒绝。改好后重试,或运行 `npx git-cz` 交互式生成。", file=sys.stderr)
        return 1
    if report.warnings:
        print("✔  提交信息通过(有警告)", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- 子命令

HOOK_TEMPLATE = """#!/bin/sh
# 由 git-cz skill 安装:校验提交信息格式
exec python3 {script} --file "$1"
"""


def cmd_install_hook(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    gitdir = git_dir(repo)
    if gitdir is None:
        print(f"✖  {repo} 不在 git 仓库里", file=sys.stderr)
        return 2

    try:
        hooks_path = subprocess.run(
            ["git", "-C", str(repo), "config", "--get", "core.hooksPath"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        hooks_dir = (repo / hooks_path).resolve() if hooks_path else gitdir / "hooks"
    except subprocess.CalledProcessError:
        hooks_dir = gitdir / "hooks"

    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir / "commit-msg"
    content = HOOK_TEMPLATE.format(script=Path(__file__).resolve())

    if hook.exists():
        if hook.read_text(encoding="utf-8", errors="replace") == content:
            print(f"✔  钩子已是最新:{hook}")
            return 0
        if not args.force:
            print(f"✖  {hook} 已存在且内容不同。确认可覆盖后加 --force(原文件会备份为 commit-msg.bak)", file=sys.stderr)
            return 1
        backup = hook.with_suffix(".bak")
        shutil.copy2(hook, backup)
        print(f"ℹ  原钩子已备份到 {backup}")

    hook.write_text(content, encoding="utf-8")
    hook.chmod(0o755)
    print(f"✔  已安装 commit-msg 钩子:{hook}")
    return 0


def cmd_show_config(args: argparse.Namespace) -> int:
    resolved = load_config(Path(args.repo).resolve())
    for note in resolved.notes:
        print(f"⚠  {note}", file=sys.stderr)
    print(f"ℹ  配置来源:{resolved.source or 'git-cz 内置默认值'}", file=sys.stderr)
    print(json.dumps(resolved.config, ensure_ascii=False, indent=2))
    return 1 if resolved.unreadable else 0


def cmd_check(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()

    if args.message is not None:
        raw = args.message
    elif args.file == "-":
        raw = sys.stdin.read()
    else:
        if args.file:
            path = Path(args.file)
        else:
            gitdir = git_dir(repo)
            if gitdir is None:
                print(f"✖  {repo} 不在 git 仓库里,请用 --file 或 --message 指定输入", file=sys.stderr)
                return 2
            path = gitdir / "COMMIT_EDITMSG"
        if not path.is_file():
            print(f"✖  找不到提交信息文件:{path}", file=sys.stderr)
            return 2
        raw = path.read_text(encoding="utf-8", errors="replace")

    resolved = load_config(repo)
    if not args.quiet:
        for note in resolved.notes:
            print(f"⚠  {note}", file=sys.stderr)
        if args.verbose:
            print(f"ℹ  配置来源:{resolved.source or 'git-cz 内置默认值'}", file=sys.stderr)

    if resolved.unreadable:
        # 拿不到真实配置就别拿默认值硬判——那只会把一堆合法提交拒掉。
        # 除非 --strict 明确要求从严。
        print("⚠  已跳过校验:配置读不出来,不拿 git-cz 默认值硬判", file=sys.stderr)
        return 1 if args.strict and not args.warn_only else 0

    report = validate(raw, resolved.config)
    stripped = strip_comments(raw)
    header = stripped.split("\n", 1)[0] if stripped else ""
    code = render(report, header, args.strict, args.json)
    return 0 if args.warn_only else code


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="check_commit_msg.py",
        description="校验 commit message 是否符合 git-cz 契约(读取 changelog.config.*)",
    )
    parser.add_argument("--repo", default=".", help="仓库路径,默认当前目录")
    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check", help="校验提交信息(默认子命令)")
    for target in (parser, check):
        target.add_argument("--file", help="提交信息文件,`-` 表示 stdin;默认 .git/COMMIT_EDITMSG")
        target.add_argument("--message", help="直接传入提交信息文本")
        target.add_argument("--strict", action="store_true", help="把警告也当成失败")
        target.add_argument("--warn-only", action="store_true", help="只报告不拦截,恒退出 0")
        target.add_argument("--json", action="store_true", help="输出机读 JSON")
        target.add_argument("--quiet", action="store_true", help="不打印配置提示")
        target.add_argument("--verbose", action="store_true", help="打印配置来源")
    check.add_argument("--repo", default=".", help="仓库路径,默认当前目录")

    hook = sub.add_parser("install-hook", help="安装 commit-msg 钩子")
    hook.add_argument("--repo", default=".", help="仓库路径,默认当前目录")
    hook.add_argument("--force", action="store_true", help="覆盖已存在的钩子(会先备份)")

    show = sub.add_parser("show-config", help="打印解析后的完整配置")
    show.add_argument("--repo", default=".", help="仓库路径,默认当前目录")

    args = parser.parse_args(argv)

    if args.command == "install-hook":
        return cmd_install_hook(args)
    if args.command == "show-config":
        return cmd_show_config(args)
    return cmd_check(args)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)

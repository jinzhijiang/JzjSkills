#!/usr/bin/env python3
"""校验 commit message 是否符合 git-cz 契约。

只用 python3 标准库,不需要 node / npm —— Flutter、Java、HarmonyOS 等非 Node 项目
也能用同一套规则把关。提交走普通 git(`git commit -F <消息文件>`),不调用 git-cz。
契约写死在本文件里(与 SKILL.md 的类型表一一对应),不读任何配置文件;
要改规则就改下面的常量,并同步 SKILL.md。

用法:
    check_commit_msg.py [--file <路径> | --message <文本> | -]  # 默认从 .git/COMMIT_EDITMSG 读
    check_commit_msg.py install-hook [--repo <目录>] [--force]

退出码: 0 通过(可能带警告) / 1 校验不通过 / 2 用法或内部错误
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

# --------------------------------------------------------------------------- 契约

# 标题格式;{emoji} 展开为「emoji + 一个空格」,{scope} 写成 `(模块名)`、没有时整体消失。
FORMAT = "{emoji}{type}{scope}: {subject}"

# type → emoji,顺序即 SKILL.md 类型表的顺序。emoji 取自 gitmoji,与 type 死绑定。
TYPES = {
    "feat": "✨",
    "fix": "🐛",
    "docs": "📝",
    "style": "🎨",
    "refactor": "♻️",
    "perf": "⚡️",
    "test": "✅",
    "chore": "🔧",
    "ci": "👷",
    "release": "🔖",
}

SUBJECT_MIN = 3
SUBJECT_MAX = 61  # 沿用 git-cz:主题上限 64 减去 emoji + 空格占的 3,按字符数计

BREAKING_PREFIX = "💥 "  # 接在 `BREAKING CHANGE: ` 之后
CLOSED_PREFIX = "✅ "
CLOSED_MESSAGE = "Closes: "

CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0002ffff]")

MAX_LINE_WIDTH = 72  # 标题、正文、页脚都按这个显示列宽把关(中文一个字 2 列)
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
    """去掉变体选择符再比较,免得 ♻ 与 ♻️ 被判成两个字符。"""
    return text.replace("️", "").replace("︎", "")


def git_dir(start: Path) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--absolute-git-dir"],
            capture_output=True, text=True, check=True,
        )
        return Path(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


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


def example_header() -> str:
    type_name = next(iter(TYPES))
    return (FORMAT.replace("{emoji}", TYPES[type_name] + " ")
            .replace("{scope}", "")
            .replace("{type}", type_name)
            .replace("{subject}", "一句话描述这次改动"))


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


def validate(message: str) -> Report:
    report = Report()
    body_text = strip_comments(message)

    if not body_text.strip():
        report.error("提交信息为空")
        return report

    lines = body_text.split("\n")
    header = lines[0]

    if header.startswith(SKIP_PREFIXES):
        return report  # merge / revert / fixup 由 git 生成,不套格式

    _validate_header(header, report)
    _validate_layout(lines, report)
    return report


def _validate_header(header: str, report: Report) -> None:
    owners = {normalize_emoji(emoji): name for name, emoji in TYPES.items()}

    # 依次按「带 emoji」「不带 emoji」「带一个不认识的前缀」去匹配,
    # 这样才能把「漏了 emoji」和「emoji 写错了」分开报,而不是把首个单词当成 emoji。
    match, emoji_state = None, "ok"
    candidate = build_header_re(FORMAT, emoji="required").match(header)
    if candidate and normalize_emoji(candidate.group("emoji")) in owners:
        match = candidate
    if match is None:
        candidate = build_header_re(FORMAT, emoji="absent").match(header)
        if candidate:
            match, emoji_state = candidate, "missing"
    if match is None:
        candidate = build_header_re(FORMAT, emoji="optional").match(header)
        if candidate:
            match = candidate
            emoji_state = "unknown" if candidate.group("emoji") else "missing"

    if match is None:
        report.error(
            f"标题不符合格式 `{FORMAT}`\n"
            f"    实际: {header}\n"
            f"    期望: {example_header()}"
        )
        return

    groups = match.groupdict()
    type_name = groups.get("type") or ""
    scope = groups.get("scope")
    subject = groups.get("subject") or ""
    emoji = groups.get("emoji")

    # --- type
    if type_name not in TYPES:
        report.error(f"未知类型 `{type_name}`;可用类型:{', '.join(TYPES)}")

    # --- emoji
    expected = TYPES.get(type_name, "?")
    if emoji_state == "missing":
        report.error(f"标题缺少 emoji,`{type_name}` 应为 `{expected}`")
    elif emoji_state == "unknown":
        report.error(f"标题开头的 `{emoji}` 不是契约里的 emoji;`{type_name}` 应为 `{expected}`")
    elif emoji and normalize_emoji(emoji) != normalize_emoji(expected):
        owner = owners.get(normalize_emoji(emoji))
        hint = f",`{emoji}` 是 {owner} 的" if owner else ""
        report.error(f"emoji 与类型不匹配:`{type_name}` 应为 `{expected}`{hint}")

    # 形如 `feat: 🎸 主题` —— emoji 写在了冒号后面
    if subject and normalize_emoji(subject.split(" ", 1)[0]) in owners:
        report.error(f"emoji 位置错误:按 `{FORMAT}` 应写在最前面,不是主题里")

    # --- scope:可选、不限取值,只拦空括号
    if scope is not None and not scope.strip():
        report.error("scope 为空括号,要么写内容要么整个去掉")

    # --- subject
    if subject != subject.strip():
        report.error("主题首尾有多余空格")
    stripped = subject.strip()
    if len(stripped) < SUBJECT_MIN:
        report.error(f"主题太短(至少 {SUBJECT_MIN} 个字符)")
    if len(stripped) > SUBJECT_MAX:
        report.error(f"主题超长:{len(stripped)} 字符 > {SUBJECT_MAX}")
    if stripped.endswith((".", "。", "!", "！", "?", "？")):
        report.error("主题结尾不要加标点")
    if re.match(r"^[a-z]+(\([^()]*\))?\s*[:：]", stripped):
        report.error("主题里重复写了 type 前缀")
    if stripped and not CJK_RE.search(stripped):
        report.error("主题要用中文写(技术名词、标识符、路径可保留原文)")

    width = display_width(header)
    if width > MAX_LINE_WIDTH:
        report.warn(f"标题 {width} 列 > {MAX_LINE_WIDTH} 列,建议压缩(中文一个字占 2 列)")


def _validate_layout(lines: list[str], report: Report) -> None:
    if len(lines) == 1:
        return

    if lines[1].strip():
        report.error("标题与正文之间必须空一行")

    for index, line in enumerate(lines[2:], start=3):
        width = display_width(line)
        if width > MAX_LINE_WIDTH:
            report.warn(f"第 {index} 行 {width} 列 > {MAX_LINE_WIDTH} 列,建议换行")

        low = line.lower()
        if low.startswith("breaking"):
            if not line.startswith("BREAKING CHANGE: "):
                report.error(f'第 {index} 行破坏性变更段必须以 "BREAKING CHANGE: " 开头(全大写、冒号后一个空格)')
            elif not line.startswith("BREAKING CHANGE: " + BREAKING_PREFIX):
                report.warn(f"第 {index} 行建议写成 `BREAKING CHANGE: {BREAKING_PREFIX}…`")

        if CLOSED_MESSAGE.strip().lower() in low and "close" in low:
            expected = CLOSED_PREFIX + CLOSED_MESSAGE
            if not line.startswith(expected):
                report.warn(f"第 {index} 行关闭 issue 建议写成 `{expected}#123`")

    body: list[str] = []
    for line in lines[2:]:
        if line.startswith("BREAKING") or line.startswith((CLOSED_PREFIX, CLOSED_MESSAGE)):
            break
        body.append(line)
    text = "\n".join(body).strip()
    # 纯代码块 / 路径 / trailer 之类没有散文,不该被判成"没写中文"
    prose = re.sub(r"`[^`]*`|^\s{4,}.*$|^[A-Za-z-]+: .*$", "", text, flags=re.MULTILINE)
    if re.search(r"[A-Za-z]{3,}", prose) and not CJK_RE.search(prose):
        report.warn("正文看着是英文,按约定用中文写(技术名词可保留原文)")


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
        print("\n提交信息不符合 git-cz 契约,已拒绝。改好消息文件后重试 `git commit -F <文件>`。", file=sys.stderr)
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

    report = validate(raw)
    stripped = strip_comments(raw)
    header = stripped.split("\n", 1)[0] if stripped else ""
    code = render(report, header, args.strict, args.json)
    return 0 if args.warn_only else code


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="check_commit_msg.py",
        description="校验 commit message 是否符合 git-cz 契约(规则写死在本脚本里,不读配置文件)",
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
        # 早先用来控制「配置来源」提示;配置文件去掉后已无作用,留着免得旧调用报错
        target.add_argument("--quiet", action="store_true", help=argparse.SUPPRESS)
        target.add_argument("--verbose", action="store_true", help=argparse.SUPPRESS)
    check.add_argument("--repo", default=".", help="仓库路径,默认当前目录")

    hook = sub.add_parser("install-hook", help="安装 commit-msg 钩子")
    hook.add_argument("--repo", default=".", help="仓库路径,默认当前目录")
    hook.add_argument("--force", action="store_true", help="覆盖已存在的钩子(会先备份)")

    args = parser.parse_args(argv)

    if args.command == "install-hook":
        return cmd_install_hook(args)
    return cmd_check(args)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)

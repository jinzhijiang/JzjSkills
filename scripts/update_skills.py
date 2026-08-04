#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""update_skills.py — 统一同步从 GitHub 引入的外部 skill。

用法:
    python3 scripts/update_skills.py --list              # 看清单:哪些 skill 归脚本管
    python3 scripts/update_skills.py --check             # 只问上游有没有新提交,不改文件
    python3 scripts/update_skills.py                     # 同步清单里的全部外部 skill
    python3 scripts/update_skills.py patrol-setup ...    # 只同步指定 skill
    python3 scripts/update_skills.py --source patrol     # 只同步某个上游来源
    python3 scripts/update_skills.py --no-deploy         # 只更新仓库,不部署到 ~/.cc-switch

清单是仓库根的 skills-upstream.json。**只有登记在清单里的 skill 会被覆盖**,自建 skill
不在清单里,脚本永远不碰——这也是 `cp -R skills/flutter-*` 那种前缀通配的替代品。

单个 skill 的同步流程:
    浅克隆上游(按需 sparse) → rsync --delete 覆盖 → 补 extra 文件(如 LICENSE)
    → 打本地适配 patch → 部署到 ~/.cc-switch/skills 并补 ~/.claude/skills 符号链接

同步成功后把上游 commit 回写进清单,下次 --check 就能判断是否真有更新。
脚本只改文件、不 commit,结束时打印 git diff --stat,由人确认后自己提交。

仅用 python3 标准库(外部命令只有 git 与 rsync)。

退出码: 0 全部成功 / 1 有 skill 同步失败 / 2 用法或环境错误
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "skills-upstream.json"
SKILLS_DIR = REPO_ROOT / "skills"

# 部署目标:~/.claude/skills 是指向 cc-switch 的符号链接农场,仓库→cc-switch 保持字节一致。
CC_SWITCH_SKILLS = Path.home() / ".cc-switch" / "skills"
CLAUDE_SKILLS = Path.home() / ".claude" / "skills"

CLONE_TIMEOUT = 300
GIT_TIMEOUT = 60

EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def run(cmd: list[str], cwd: Path | None = None, timeout: int = GIT_TIMEOUT,
        check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True,
                          text=True, timeout=timeout, check=False)
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"命令失败({proc.returncode}): {' '.join(cmd)}\n{proc.stderr.strip()}")
    return proc


def load_manifest() -> dict:
    if not MANIFEST.exists():
        log(f"[错误] 找不到清单: {MANIFEST}")
        sys.exit(EXIT_USAGE)
    with MANIFEST.open(encoding="utf-8") as fh:
        return json.load(fh)


def save_manifest(data: dict) -> None:
    # 保持人读友好:2 空格缩进、不转义中文、末尾换行,便于 git diff review。
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    MANIFEST.write_text(text, encoding="utf-8")


def select(manifest: dict, names: list[str], source_id: str | None) -> list[tuple[dict, list[dict]]]:
    """按 skill 名 / 来源 id 过滤,返回 [(source, [skill, ...]), ...]。"""
    known = {s["name"] for src in manifest["sources"] for s in src["skills"]}
    unknown = [n for n in names if n not in known]
    if unknown:
        log(f"[错误] 清单里没有这些 skill: {', '.join(unknown)}")
        log("       自建 skill 不归本脚本管;外部 skill 请先登记到 skills-upstream.json。")
        sys.exit(EXIT_USAGE)

    selected = []
    for source in manifest["sources"]:
        if source_id and source["id"] != source_id:
            continue
        picked = [s for s in source["skills"] if not names or s["name"] in names]
        if picked:
            selected.append((source, picked))
    if not selected:
        log(f"[错误] 没有匹配的来源: --source {source_id}")
        sys.exit(EXIT_USAGE)
    return selected


def remote_head(source: dict) -> str | None:
    """不克隆,直接问上游某个分支的最新 commit。"""
    try:
        proc = run(["git", "ls-remote", source["repo"], source["ref"]])
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        log(f"  [警告] 读取上游失败: {exc}")
        return None
    line = proc.stdout.strip().split("\n")[0] if proc.stdout.strip() else ""
    return line.split("\t")[0] if line else None


def clone_source(source: dict, dest: Path) -> str:
    """浅克隆上游到 dest,返回 HEAD commit。登记了 sparse 就只取那几个目录。"""
    cmd = ["git", "clone", "--depth", "1", "--branch", source["ref"]]
    if source.get("sparse"):
        cmd += ["--filter=blob:none", "--sparse"]
    cmd += [source["repo"], str(dest)]
    run(cmd, timeout=CLONE_TIMEOUT)
    if source.get("sparse"):
        # cone 模式:选中目录之外,仓库根目录下的文件也会保留(alicloud 的 LICENSE 靠这个)。
        run(["git", "sparse-checkout", "set", *source["sparse"]], cwd=dest)
    return run(["git", "rev-parse", "HEAD"], cwd=dest).stdout.strip()


def sync_skill(skill: dict, src_root: Path) -> None:
    """把上游内容覆盖到 skills/<name>/,再补 extra 文件、打本地 patch。"""
    name = skill["name"]
    src = (src_root / skill["src"]).resolve()
    dest = SKILLS_DIR / name
    if not src.is_dir():
        raise RuntimeError(f"上游里找不到 {skill['src']}——上游可能改了目录结构,请核对清单")

    excludes = [".git/"] + list(skill.get("exclude", []))
    cmd = ["rsync", "-a", "--delete"] + [f"--exclude={e}" for e in excludes]
    cmd += [f"{src}/", f"{dest}/"]
    run(cmd)

    for rel_src, rel_dest in skill.get("extra", {}).items():
        origin = src_root / rel_src
        if not origin.is_file():
            raise RuntimeError(f"上游里找不到附带文件 {rel_src}(清单 extra 项)")
        shutil.copy2(origin, dest / rel_dest)

    patch = skill.get("patch")
    if patch:
        patch_path = REPO_ROOT / patch
        if not patch_path.is_file():
            raise RuntimeError(f"找不到本地适配 patch: {patch}")
        probe = run(["git", "apply", "--check", "-p1", str(patch_path)],
                    cwd=REPO_ROOT, check=False)
        if probe.returncode != 0:
            raise RuntimeError(
                f"本地适配 patch 打不上了(上游动了被 patch 的位置):{patch}\n"
                f"{probe.stderr.strip()}\n"
                f"       现在 skills/{name} 是未打补丁的上游原样。手工合完改动后,用\n"
                f"       git diff -R --src-prefix=a/ --dst-prefix=b/ -- skills/{name} > {patch}\n"
                f"       重新生成 patch;想放弃本次同步则 git checkout -- skills/{name}")
        run(["git", "apply", "-p1", str(patch_path)], cwd=REPO_ROOT)


def deploy(name: str) -> None:
    """同步到 ~/.cc-switch/skills 并确保 ~/.claude/skills 下有符号链接。"""
    target = CC_SWITCH_SKILLS / name
    run(["rsync", "-a", "--delete", f"{SKILLS_DIR / name}/", f"{target}/"])
    link = CLAUDE_SKILLS / name
    if not (link.is_symlink() and link.resolve() == target.resolve()):
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target)
        log(f"  · 补建符号链接 {link} -> {target}")


def cmd_list(manifest: dict) -> int:
    total = 0
    for source in manifest["sources"]:
        commit = source.get("commit") or "(基线未知)"
        print(f"\n{source['id']}  {source['repo']}@{source['ref']}  上次同步 {commit[:12]}")
        if source.get("note"):
            print(f"  note: {source['note']}")
        for skill in source["skills"]:
            marks = []
            if skill.get("patch"):
                marks.append("本地适配 patch")
            if skill.get("extra"):
                marks.append("附带 " + ",".join(skill["extra"].values()))
            if skill.get("exclude"):
                marks.append("排除 " + ",".join(skill["exclude"]))
            suffix = f"  [{'; '.join(marks)}]" if marks else ""
            print(f"  - {skill['name']}{suffix}")
            total += 1
    print(f"\n共 {total} 个外部 skill 归脚本管;其余为自建,脚本不碰。")
    return EXIT_OK


def cmd_check(selected: list[tuple[dict, list[dict]]]) -> int:
    stale = 0
    for source, skills in selected:
        head = remote_head(source)
        recorded = source.get("commit")
        names = ", ".join(s["name"] for s in skills)
        if head is None:
            print(f"[?] {source['id']:<22} 读不到上游         ({names})")
        elif not recorded:
            stale += 1
            print(f"[!] {source['id']:<22} 基线未知,建议同步一次  上游 {head[:12]}  ({names})")
        elif head.startswith(recorded) or recorded.startswith(head):
            print(f"[=] {source['id']:<22} 已是最新 {head[:12]}  ({names})")
        else:
            stale += 1
            print(f"[+] {source['id']:<22} 有更新 {recorded[:12]} -> {head[:12]}  ({names})")
            print(f"    {source['repo']}/compare/{recorded[:12]}...{head[:12]}")
    print(f"\n{stale} 个来源需要同步。" if stale else "\n全部已是最新。")
    return EXIT_OK


def cmd_sync(manifest: dict, selected: list[tuple[dict, list[dict]]], do_deploy: bool) -> int:
    failed: list[str] = []
    synced: list[str] = []

    for source, skills in selected:
        log(f"\n== {source['id']}  {source['repo']}@{source['ref']}")
        with tempfile.TemporaryDirectory(prefix="skills-upstream-") as tmp:
            checkout = Path(tmp) / "upstream"
            try:
                head = clone_source(source, checkout)
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                log(f"  [失败] 克隆上游出错: {exc}")
                failed.extend(s["name"] for s in skills)
                continue
            log(f"  上游 HEAD {head[:12]}")

            ok_here = []
            for skill in skills:
                name = skill["name"]
                try:
                    sync_skill(skill, checkout)
                except (RuntimeError, subprocess.TimeoutExpired) as exc:
                    log(f"  [失败] {name}: {exc}")
                    failed.append(name)
                    continue
                if do_deploy and CC_SWITCH_SKILLS.is_dir():
                    try:
                        deploy(name)
                    except (RuntimeError, OSError) as exc:
                        log(f"  [失败] {name} 部署出错: {exc}")
                        failed.append(name)
                        continue
                log(f"  [完成] {name}")
                ok_here.append(name)
                synced.append(name)

            # 只有整个来源都同步成功才回写 commit——部分同步不能代表这个来源到了新版本。
            full = len(ok_here) == len(source["skills"])
            if full and not failed:
                source["commit"] = head
            elif ok_here:
                log(f"  · 本次只同步了该来源的部分 skill,清单里的 commit 不回写")

    if do_deploy and not CC_SWITCH_SKILLS.is_dir():
        log(f"\n[警告] 没有 {CC_SWITCH_SKILLS},跳过部署——仓库已更新,换台机器再部署即可。")

    save_manifest(manifest)

    log("")
    if synced:
        diff = run(["git", "diff", "--stat", "--", "skills", "skills-upstream.json"],
                   cwd=REPO_ROOT, check=False)
        body = diff.stdout.strip()
        print(body if body else "(工作区没有变化——上游内容与本地一致)")
    if failed:
        log(f"\n{len(failed)} 个 skill 同步失败: {', '.join(failed)}")
        return EXIT_FAILED
    log(f"\n{len(synced)} 个 skill 已同步。确认 diff 后自行提交(提交信息见 git-cz skill)。")
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(
        description="统一同步从 GitHub 引入的外部 skill(清单: skills-upstream.json)")
    parser.add_argument("names", nargs="*", metavar="skill", help="只同步这些 skill,默认全部")
    parser.add_argument("--source", metavar="id", help="只处理某个上游来源")
    parser.add_argument("--check", action="store_true", help="只报告上游有无新提交,不改文件")
    parser.add_argument("--list", action="store_true", help="列出清单内容")
    parser.add_argument("--no-deploy", action="store_true",
                        help="只更新仓库,不同步到 ~/.cc-switch/skills")
    args = parser.parse_args()

    for tool in ("git", "rsync"):
        if not shutil.which(tool):
            log(f"[错误] 缺少 {tool}")
            return EXIT_USAGE

    manifest = load_manifest()
    if args.list:
        return cmd_list(manifest)

    selected = select(manifest, args.names, args.source)
    if args.check:
        return cmd_check(selected)
    return cmd_sync(manifest, selected, do_deploy=not args.no_deploy)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("\n已中断")
        sys.exit(EXIT_USAGE)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_assistants.py — 在 bagua-furnace/references/*.md 与 Codeg 数据库 assistant 表之间校验或双向同步。

用法:
    python3 scripts/sync_assistants.py --check   # 校验 references/*.md 与 codeg.db 是否完全一致（默认）
    python3 scripts/sync_assistants.py --apply   # 将 references/*.md 写入 codeg.db 的 assistant 表
    python3 scripts/sync_assistants.py --export  # 从 codeg.db 导出最新提示词覆盖 references/*.md
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
REF_DIR = SKILL_ROOT / "references"
DEFAULT_DB = Path.home() / "Library/Application Support/app.codeg/codeg.db"

ASSISTANT_FILES: dict[int, str] = {
    1: "mu.md",
    2: "tu.md",
    3: "jin.md",
    4: "shui.md",
    5: "huo.md",
}


def parse_assistant_md(path: Path) -> dict[str, str | int]:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"{path} missing YAML frontmatter")
    end_idx = raw.find("\n---\n", 4)
    if end_idx == -1:
        raise ValueError(f"{path} unclosed YAML frontmatter")
    fm_block = raw[4:end_idx]
    body = raw[end_idx + 5 :].lstrip("\n").rstrip()

    meta: dict[str, str | int] = {}
    for line in fm_block.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        meta[k] = int(v) if k == "id" else v

    meta["instructions"] = body
    return meta


def format_assistant_md(meta: dict) -> str:
    return (
        f"---\n"
        f"id: {meta['id']}\n"
        f"name: {meta['name']}\n"
        f"emoji: {meta['emoji']}\n"
        f"color: {meta['color']}\n"
        f"agent_type: {meta['agent_type']}\n"
        f"agent_options: '{meta['agent_options']}'\n"
        f"description: {meta['description']}\n"
        f"---\n\n"
        f"{str(meta['instructions']).rstrip()}\n"
    )


def cmd_check(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    diffs = 0
    for aid, fname in ASSISTANT_FILES.items():
        fpath = REF_DIR / fname
        if not fpath.is_file():
            print(f"[MISSING] {fpath}", file=sys.stderr)
            diffs += 1
            continue
        md = parse_assistant_md(fpath)
        row = conn.execute(
            "SELECT id, name, description, avatar, instructions FROM assistant WHERE id = ?",
            (aid,),
        ).fetchone()
        if not row:
            print(f"[MISSING IN DB] id={aid}", file=sys.stderr)
            diffs += 1
            continue
        avatar = json.loads(row["avatar"])
        if (
            row["name"] != md["name"]
            or row["description"] != md["description"]
            or avatar.get("emoji") != md["emoji"]
            or avatar.get("color") != md["color"]
            or row["instructions"].rstrip() != str(md["instructions"]).rstrip()
        ):
            print(f"[DIFF] id={aid} ({fname}) differs from codeg.db", file=sys.stderr)
            diffs += 1
        else:
            print(f"[OK] id={aid} {md['name']} ({fname}) in sync")
    conn.close()
    return 1 if diffs else 0


def cmd_apply(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    with conn:
        for aid, fname in ASSISTANT_FILES.items():
            md = parse_assistant_md(REF_DIR / fname)
            avatar_json = json.dumps(
                {"kind": "emoji", "emoji": md["emoji"], "color": md["color"]},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            conn.execute(
                "UPDATE assistant SET name = ?, description = ?, avatar = ?, "
                "instructions = ?, revision = revision + 1, updated_at = ? WHERE id = ?",
                (
                    md["name"],
                    md["description"],
                    avatar_json,
                    md["instructions"],
                    now_iso,
                    aid,
                ),
            )
            print(f"[APPLIED] {fname} -> codeg.db (id={aid}, name={md['name']})")
    conn.close()
    return 0


def cmd_export(db_path: Path) -> int:
    REF_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    for aid, fname in ASSISTANT_FILES.items():
        row = conn.execute(
            "SELECT id, name, description, avatar, agent_type, agent_options, instructions "
            "FROM assistant WHERE id = ?",
            (aid,),
        ).fetchone()
        avatar = json.loads(row["avatar"])
        content = format_assistant_md(
            {
                "id": aid,
                "name": row["name"],
                "emoji": avatar["emoji"],
                "color": avatar["color"],
                "agent_type": row["agent_type"],
                "agent_options": row["agent_options"],
                "description": row["description"],
                "instructions": row["instructions"],
            }
        )
        (REF_DIR / fname).write_text(content, encoding="utf-8")
        print(f"[EXPORTED] codeg.db (id={aid}) -> {REF_DIR / fname}")
    conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Wuxing assistants with codeg.db")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="Check sync status (default)")
    group.add_argument("--apply", action="store_true", help="Write references/*.md to codeg.db")
    group.add_argument("--export", action="store_true", help="Export codeg.db to references/*.md")
    args = parser.parse_args()

    if args.apply:
        return cmd_apply(args.db)
    if args.export:
        return cmd_export(args.db)
    return cmd_check(args.db)


if __name__ == "__main__":
    sys.exit(main())

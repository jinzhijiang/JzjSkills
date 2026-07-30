#!/usr/bin/env python3
"""Verify a Flutter Android release artifact without reading signing secrets."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


ANDROID_NS = "http://schemas.android.com/apk/res/android"
ANDROID = f"{{{ANDROID_NS}}}"


def newest_existing(paths: list[Path]) -> Path | None:
    existing = [path for path in paths if path.is_file()]
    return max(existing, key=lambda path: path.stat().st_mtime) if existing else None


def find_manifest(root: Path) -> Path | None:
    preferred = [
        root
        / "build/app/intermediates/merged_manifests/release/"
        "processReleaseManifest/AndroidManifest.xml",
        root
        / "build/app/intermediates/packaged_manifests/release/"
        "processReleaseManifestForPackage/AndroidManifest.xml",
        root
        / "build/app/intermediates/merged_manifest/release/"
        "processReleaseMainManifest/AndroidManifest.xml",
    ]
    selected = newest_existing(preferred)
    if selected:
        return selected
    candidates = list(
        root.glob("build/app/intermediates/**/*release*/**/AndroidManifest.xml")
    )
    return newest_existing(candidates)


def parse_pubspec_version(path: Path) -> tuple[str | None, str | None]:
    if not path.is_file():
        return None, None
    match = re.search(
        r"(?m)^version:\s*['\"]?([^+'\"\s]+)(?:\+(\d+))?['\"]?\s*$",
        path.read_text(encoding="utf-8"),
    )
    return (match.group(1), match.group(2)) if match else (None, None)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_manifest(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    uses_sdk = root.find("uses-sdk")
    application = root.find("application")
    activities: list[dict[str, str]] = []
    if application is not None:
        for activity in application.findall("activity"):
            activities.append(
                {
                    "name": activity.get(f"{ANDROID}name", ""),
                    "screen_orientation": activity.get(
                        f"{ANDROID}screenOrientation", ""
                    ),
                }
            )
    return {
        "package": root.get("package"),
        "version_code": root.get(f"{ANDROID}versionCode"),
        "version_name": root.get(f"{ANDROID}versionName"),
        "min_sdk": uses_sdk.get(f"{ANDROID}minSdkVersion")
        if uses_sdk is not None
        else None,
        "target_sdk": uses_sdk.get(f"{ANDROID}targetSdkVersion")
        if uses_sdk is not None
        else None,
        "permissions": sorted(
            {
                node.get(f"{ANDROID}name", "")
                for node in root.findall("uses-permission")
                if node.get(f"{ANDROID}name")
            }
        ),
        "activities": activities,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect a built Flutter Android release for Play readiness."
    )
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--expect-package")
    parser.add_argument("--expect-target-sdk", type=int)
    parser.add_argument("--require-r8", action="store_true")
    parser.add_argument("--fail-on-fixed-orientation", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = args.project_root.expanduser().resolve()
    aab = root / "build/app/outputs/bundle/release/app-release.aab"
    manifest_path = find_manifest(root)
    pubspec_name, pubspec_code = parse_pubspec_version(root / "pubspec.yaml")
    errors: list[str] = []
    warnings: list[str] = []

    if not aab.is_file():
        errors.append(f"Release AAB not found: {aab}")
    if manifest_path is None:
        errors.append("Release merged/packaged AndroidManifest.xml not found")

    manifest = parse_manifest(manifest_path) if manifest_path else {}
    if args.expect_package and manifest.get("package") != args.expect_package:
        errors.append(
            f"Package mismatch: expected {args.expect_package}, "
            f"found {manifest.get('package')}"
        )
    if args.expect_target_sdk is not None:
        actual_target = manifest.get("target_sdk")
        if actual_target != str(args.expect_target_sdk):
            errors.append(
                f"Target SDK mismatch: expected {args.expect_target_sdk}, "
                f"found {actual_target}"
            )
    if pubspec_name and manifest.get("version_name") != pubspec_name:
        errors.append(
            f"Version name mismatch: pubspec {pubspec_name}, "
            f"manifest {manifest.get('version_name')}"
        )
    if pubspec_code and manifest.get("version_code") != pubspec_code:
        errors.append(
            f"Version code mismatch: pubspec {pubspec_code}, "
            f"manifest {manifest.get('version_code')}"
        )

    fixed_orientation = [
        activity
        for activity in manifest.get("activities", [])
        if activity.get("screen_orientation")
    ]
    if fixed_orientation:
        message = "Fixed activity orientation found: " + ", ".join(
            f"{item['name']}={item['screen_orientation']}"
            for item in fixed_orientation
        )
        (errors if args.fail_on_fixed_orientation else warnings).append(message)

    mapping_dir = root / "build/app/outputs/mapping/release"
    r8_files = {
        name: mapping_dir / name
        for name in ("mapping.txt", "resources.txt", "usage.txt")
    }
    missing_r8 = [name for name, path in r8_files.items() if not path.is_file()]
    if missing_r8:
        message = "Missing R8 outputs: " + ", ".join(missing_r8)
        (errors if args.require_r8 else warnings).append(message)

    report: dict[str, Any] = {
        "project_root": str(root),
        "aab": {
            "path": str(aab),
            "exists": aab.is_file(),
            "size_bytes": aab.stat().st_size if aab.is_file() else None,
            "sha256": sha256(aab) if aab.is_file() else None,
        },
        "manifest_path": str(manifest_path) if manifest_path else None,
        "manifest": manifest,
        "pubspec": {"version_name": pubspec_name, "version_code": pubspec_code},
        "r8_outputs": {
            name: {
                "exists": path.is_file(),
                "size_bytes": path.stat().st_size if path.is_file() else None,
            }
            for name, path in r8_files.items()
        },
        "advertising_id_permission": (
            "com.google.android.gms.permission.AD_ID"
            in manifest.get("permissions", [])
        ),
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Project: {root}")
        print(
            "AAB: "
            + (
                f"{aab} ({report['aab']['size_bytes']} bytes, "
                f"sha256={report['aab']['sha256']})"
                if aab.is_file()
                else "MISSING"
            )
        )
        print(f"Manifest: {report['manifest_path'] or 'MISSING'}")
        if manifest:
            print(
                "Identity: "
                f"{manifest.get('package')} "
                f"{manifest.get('version_name')} "
                f"({manifest.get('version_code')})"
            )
            print(
                f"SDK: min={manifest.get('min_sdk')} "
                f"target={manifest.get('target_sdk')}"
            )
            print(
                "AD_ID permission: "
                + ("yes" if report["advertising_id_permission"] else "no")
            )
        for warning in warnings:
            print(f"WARNING: {warning}")
        for error in errors:
            print(f"ERROR: {error}")
        print("Result: PASS" if not errors else "Result: FAIL")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())

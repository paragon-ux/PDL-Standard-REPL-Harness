#!/usr/bin/env python3
"""Version bump script for pdl-taskmaster.

Usage:
    python scripts/bump_version.py patch
    python scripts/bump_version.py minor
    python scripts/bump_version.py major
    python scripts/bump_version.py 2.5.0
    python scripts/bump_version.py patch --commit --tag
    python scripts/bump_version.py patch --dry-run
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT_PY = ROOT / "src" / "pdl_taskmaster" / "__init__.py"
VERSION_PATTERN = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
SEMVER_REGEX = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-?([a-zA-Z0-9.]+))?$")


def get_current_version() -> str:
    content = INIT_PY.read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(content)
    if not match:
        raise ValueError(f"Cannot find __version__ in {INIT_PY}")
    return match.group(1)


def compute_next_version(current: str, bump_type: str) -> str:
    bump_type = bump_type.strip().lower()
    match = SEMVER_REGEX.match(current)
    if not match:
        raise ValueError(f"Current version '{current}' is not valid SemVer (expected X.Y.Z)")

    major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))

    if bump_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump_type == "major":
        return f"{major + 1}.0.0"
    else:
        # User specified an explicit version string
        explicit = bump_type
        if not SEMVER_REGEX.match(explicit) and not re.match(r"^\d+\.\d+\.\d+.*$", explicit):
            raise ValueError(f"Invalid target version string: '{explicit}'")
        return explicit


def is_git_dirty() -> bool:
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return bool(res.stdout.strip())
    except Exception:
        return False


def update_init_file(new_version: str) -> None:
    content = INIT_PY.read_text(encoding="utf-8")
    new_content, count = VERSION_PATTERN.subn(f'__version__ = "{new_version}"', content)
    if count == 0:
        raise RuntimeError(f"Failed to substitute __version__ in {INIT_PY}")
    INIT_PY.write_text(new_content, encoding="utf-8")


def sync_lockfile() -> None:
    try:
        subprocess.run(["uv", "lock"], cwd=ROOT, check=True, capture_output=True)
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Bump pdl-taskmaster package version")
    parser.add_argument(
        "action",
        help="Bump target: 'patch', 'minor', 'major', or an explicit version string (e.g. '2.5.0')",
    )
    parser.add_argument(
        "--commit",
        "-c",
        action="store_true",
        help="Create a git commit with the bumped version",
    )
    parser.add_argument(
        "--tag",
        "-t",
        action="store_true",
        help="Create an annotated git tag (vX.Y.Z)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what version would be set without modifying files",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow running with uncommitted working tree changes",
    )

    args = parser.parse_args()

    if not args.dry_run and not args.allow_dirty and is_git_dirty():
        print("Error: Git working tree has uncommitted changes. Commit or stash them first, or use --allow-dirty.", file=sys.stderr)
        return 1

    current = get_current_version()
    try:
        target = compute_next_version(current, args.action)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Current version: {current}")
    print(f"Target version:  {target}")

    if args.dry_run:
        print("[dry-run] No files modified.")
        return 0

    update_init_file(target)
    print(f"[updated] {INIT_PY.relative_to(ROOT)} -> __version__ = \"{target}\"")

    sync_lockfile()
    print("[updated] uv.lock synchronized")

    tag_name = f"v{target}"

    if args.commit:
        files_to_add = ["src/pdl_taskmaster/__init__.py"]
        if (ROOT / "uv.lock").exists():
            files_to_add.append("uv.lock")
        subprocess.run(["git", "add"] + files_to_add, cwd=ROOT, check=True)
        commit_msg = f"chore(release): bump version to {target}"
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=ROOT, check=True)
        print(f"[git] Created commit: {commit_msg}")

    if args.tag:
        tag_msg = f"Release {tag_name}"
        subprocess.run(["git", "tag", "-a", tag_name, "-m", tag_msg], cwd=ROOT, check=True)
        print(f"[git] Created tag: {tag_name}")

    if not args.commit and not args.tag:
        print("\nNext steps to commit and tag:")
        print(f"  git add src/pdl_taskmaster/__init__.py uv.lock")
        print(f'  git commit -m "chore(release): bump version to {target}"')
        print(f'  git tag -a {tag_name} -m "Release {tag_name}"')
        print(f"  git push origin main")
        print(f"  git push origin {tag_name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

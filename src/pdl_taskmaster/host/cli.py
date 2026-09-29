"""PDLt Umbrella CLI: entry point for REPL, initialization, and verification."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pdl_taskmaster import __protocol_version__, __version__
from pdl_taskmaster.runtime.normative_store import NormativeStore


def _cmd_version() -> int:
    manifest_version = "unknown"
    try:
        manifest_path = NormativeStore.resolve_contract(Path.cwd(), "CONTRACT_MANIFEST.json")
        if manifest_path.is_file():
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_version = data.get("manifest_version", "unknown")
    except Exception:
        pass
    print(f"pdl-taskmaster {__version__} (protocol specification: {__protocol_version__}, manifest: {manifest_version})")
    return 0


def _cmd_init(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="pdlt init",
        description="Initialize normative contracts and standard clauses (ADR-0008).",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--global",
        "-g",
        dest="is_global",
        action="store_true",
        default=True,
        help="seed centralized user store (~/.pdlt/versions/v2/contracts) [default]",
    )
    group.add_argument(
        "--local",
        "-l",
        dest="is_local",
        action="store_true",
        help="seed local repository contracts directory (./contracts)",
    )
    parser.add_argument(
        "--version-tag",
        default=NormativeStore.DEFAULT_VERSION,
        help=f"protocol version namespace (default: {NormativeStore.DEFAULT_VERSION})",
    )
    args = parser.parse_args(argv)

    if args.is_local:
        target = Path.cwd() / "contracts"
        print(f"[init] Seeding local contracts into {target}...")
        NormativeStore.seed_directory(target)
        print(f"[init] Success: local contracts initialized at {target}")
    else:
        print(f"[init] Seeding centralized store for protocol {args.version_tag}...")
        seeded = NormativeStore.seed_store(
            repo_root=Path.cwd(),
            version=args.version_tag,
        )
        print(f"[init] Success: centralized store seeded at {seeded}")
    return 0


def _cmd_verify(argv: list[str]) -> int:
    from pdl_taskmaster.verify.verify_repl_baseline import main as verify_main

    # Forward to verify_repl_baseline
    return verify_main()


def _cmd_viewer(argv: list[str]) -> int:
    from pdl_taskmaster.tools.viewer_server import main as viewer_main

    return viewer_main(argv)


def _main_impl(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        from pdl_taskmaster.host.repl import main as repl_main

        return repl_main()

    subcmd = argv[0].lower()
    if subcmd in {"version", "--version", "-v"}:
        return _cmd_version()
    if subcmd == "init":
        return _cmd_init(argv[1:])
    if subcmd == "verify":
        return _cmd_verify(argv[1:])
    if subcmd in {"viewer", "ui", "dashboard"}:
        return _cmd_viewer(argv[1:])

    # Default: route all other invocations to REPL
    from pdl_taskmaster.host.repl import main as repl_main

    return repl_main()


def main(argv: list[str] | None = None) -> int:
    try:
        return _main_impl(argv)
    except KeyboardInterrupt:
        print("\n[session terminated by user]", file=sys.stderr, flush=True)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

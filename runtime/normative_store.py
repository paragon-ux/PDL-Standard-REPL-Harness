"""Normative Store & Protocol Version Resolver (ADR-0008).

Separates the immutable normative standards, contracts, and schemas (the Brain)
from ephemeral runtime workspaces and test runs (the Hands & Feet).
Resolves protocol assets from a centralized, version-namespaced store at
`~/.pdlt/versions/<version>/`, with graceful fallback to repository contracts.
"""
from __future__ import annotations

from pathlib import Path
import json
import os
import shutil


class NormativeStoreError(RuntimeError):
    pass


class NormativeStore:
    DEFAULT_VERSION = "v2"

    @classmethod
    def get_default_store_root(cls) -> Path:
        env_root = os.environ.get("PDLT_STORE_ROOT")
        if env_root:
            return Path(env_root).resolve()
        return Path.home() / ".pdlt"

    @classmethod
    def resolve_version(cls, repo_root: str | Path | None = None) -> str:
        """Resolve pinned protocol version from .pdlt-version or pdlt.json."""
        if repo_root is not None:
            root = Path(repo_root).resolve()
            pin_file = root / ".pdlt-version"
            if pin_file.is_file():
                v = pin_file.read_text(encoding="utf-8").strip()
                if v:
                    return v
            cfg_file = root / "pdlt.json"
            if cfg_file.is_file():
                try:
                    data = json.loads(cfg_file.read_text(encoding="utf-8"))
                    v = data.get("version")
                    if isinstance(v, str) and v.strip():
                        return v.strip()
                except Exception:
                    pass
        return cls.DEFAULT_VERSION

    @classmethod
    def resolve_standards_root(
        cls,
        repo_root: str | Path,
        version: str | None = None,
        store_root: str | Path | None = None,
    ) -> Path:
        """Resolve directory containing CONTRACT_MANIFEST.json and standards.

        Checks store_root / 'versions' / version / 'contracts'.
        If not found or uninitialized, falls back to repo_root / 'contracts'.
        """
        env_standards = os.environ.get("PDLT_STANDARDS_PATH")
        if env_standards:
            p = Path(env_standards).resolve()
            if p.is_dir():
                return p

        repo_path = Path(repo_root).resolve()
        v = version or cls.resolve_version(repo_path)
        base = Path(store_root).resolve() if store_root else cls.get_default_store_root()
        candidate = base / "versions" / v / "contracts"

        if candidate.is_dir() and (candidate / "CONTRACT_MANIFEST.json").is_file():
            return candidate

        fallback = repo_path / "contracts"
        if fallback.is_dir() and (fallback / "CONTRACT_MANIFEST.json").is_file():
            return fallback

        return fallback

    @classmethod
    def resolve_contract(
        cls,
        repo_root: str | Path,
        contract_name: str,
        version: str | None = None,
        store_root: str | Path | None = None,
    ) -> Path:
        """Resolve a specific contract file (e.g. EXECUTION_CONTRACT.json)."""
        standards_root = cls.resolve_standards_root(repo_root, version, store_root)
        target = standards_root / contract_name
        if target.is_file():
            return target
        fallback = Path(repo_root).resolve() / "contracts" / contract_name
        return fallback

    @classmethod
    def seed_store(
        cls,
        repo_root: str | Path,
        version: str = "v2",
        store_root: str | Path | None = None,
    ) -> Path:
        """Seed the centralized ~/.pdlt store from the current repository contracts."""
        repo_path = Path(repo_root).resolve()
        base = Path(store_root).resolve() if store_root else cls.get_default_store_root()
        target_dir = base / "versions" / version / "contracts"
        target_dir.mkdir(parents=True, exist_ok=True)
        source_dir = repo_path / "contracts"
        if not source_dir.is_dir():
            raise NormativeStoreError(f"source contracts directory missing: {source_dir}")

        for item in source_dir.iterdir():
            dest = target_dir / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        return target_dir

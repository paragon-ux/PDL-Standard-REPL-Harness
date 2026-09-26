"""Normative Store & Protocol Version Resolver (ADR-0008).

Formal 4-Tier Precedence Order for Normative Standards:
1. Priority 1 (Explicit Environment Override): `PDLT_STANDARDS_PATH` environment variable.
2. Priority 2 (Local Repository Override): `<repo_root>/contracts/` (if containing `CONTRACT_MANIFEST.json`).
3. Priority 3 (User Normative Store): `~/.pdlt/versions/<version>/contracts/` (ADR-0008 content-addressed store).
4. Priority 4 (Bundled Canonical Fallback): `pdl_taskmaster.contracts` package data (via `importlib.resources`).
"""
from __future__ import annotations

import importlib.resources
import json
import os
from pathlib import Path
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
    def get_bundled_contracts_path(cls) -> Path | None:
        """Resolve path to package-bundled contracts data directory."""
        try:
            bundled = importlib.resources.files("pdl_taskmaster").joinpath("contracts")
            p = Path(str(bundled))
            if p.is_dir() and (p / "CONTRACT_MANIFEST.json").is_file():
                return p
        except Exception:
            pass
        return None

    @classmethod
    def resolve_standards_root(
        cls,
        repo_root: str | Path,
        version: str | None = None,
        store_root: str | Path | None = None,
    ) -> Path:
        """Resolve directory containing CONTRACT_MANIFEST.json and standards.

        Strict 4-Tier Precedence:
        1. PDLT_STANDARDS_PATH env var
        2. Local <repo_root>/contracts/ (if present and valid)
        3. ~/.pdlt/versions/<version>/contracts/ (if seeded)
        4. Bundled package data in pdl_taskmaster.contracts
        """
        # Tier 1: Explicit environment variable override
        env_standards = os.environ.get("PDLT_STANDARDS_PATH")
        if env_standards:
            p = Path(env_standards).resolve()
            if p.is_dir() and (p / "CONTRACT_MANIFEST.json").is_file():
                return p

        # Tier 2: Local repository contracts directory
        repo_path = Path(repo_root).resolve()
        local_candidate = repo_path / "contracts"
        if local_candidate.is_dir() and (local_candidate / "CONTRACT_MANIFEST.json").is_file():
            return local_candidate

        # Tier 3: Centralized ~/.pdlt store
        v = version or cls.resolve_version(repo_path)
        base = Path(store_root).resolve() if store_root else cls.get_default_store_root()
        user_candidate = base / "versions" / v / "contracts"
        if user_candidate.is_dir() and (user_candidate / "CONTRACT_MANIFEST.json").is_file():
            return user_candidate

        # Tier 4: Bundled package data
        bundled = cls.get_bundled_contracts_path()
        if bundled is not None:
            return bundled

        return local_candidate

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
    def seed_directory(cls, target_dir: Path, source_dir: Path | None = None) -> Path:
        """Copy contract files into target directory from local source or bundled data."""
        target_dir = Path(target_dir).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        src = source_dir
        if src is None or not (src / "CONTRACT_MANIFEST.json").is_file():
            src = cls.get_bundled_contracts_path()
        if src is None or not src.is_dir():
            raise NormativeStoreError("cannot seed contracts: no valid local or bundled source found")

        for item in src.iterdir():
            dest = target_dir / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        return target_dir

    @classmethod
    def seed_store(
        cls,
        repo_root: str | Path,
        version: str = "v2",
        store_root: str | Path | None = None,
    ) -> Path:
        """Seed the centralized ~/.pdlt store from the current repository contracts or bundled data."""
        repo_path = Path(repo_root).resolve()
        base = Path(store_root).resolve() if store_root else cls.get_default_store_root()
        target_dir = base / "versions" / version / "contracts"
        local_src = repo_path / "contracts" if (repo_path / "contracts").is_dir() else None
        return cls.seed_directory(target_dir, source_dir=local_src)

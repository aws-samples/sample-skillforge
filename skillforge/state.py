"""Persistent, non-secret installation choices used by `skillforge update`."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from . import model

SCHEMA_VERSION = 2
DEFAULT_RECEIPT = Path(".skillforge") / "install.json"
HOSTS = ("kiro", "all")
INSTALL_MODES = ("symlink", "copy")


@dataclass(frozen=True)
class InstallReceipt:
    persona: str
    verticals: tuple[str, ...]
    host: str
    install_mode: str
    out: str
    marketplace: str
    installed_version: str
    kiro_skills_dir: str
    kiro_agents_dir: str
    kiro_mcp_config: str
    codex_agents_dir: str
    codex_config: str
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "persona": self.persona,
            "verticals": list(self.verticals),
            "host": self.host,
            "install_mode": self.install_mode,
            "out": self.out,
            "marketplace": self.marketplace,
            "installed_version": self.installed_version,
            "kiro": {
                "skills_dir": self.kiro_skills_dir,
                "agents_dir": self.kiro_agents_dir,
                "mcp_config": self.kiro_mcp_config,
            },
            "codex": {
                "agents_dir": self.codex_agents_dir,
                "config": self.codex_config,
            },
        }

    @classmethod
    def from_dict(cls, data: object, source: Path) -> "InstallReceipt":
        if not isinstance(data, dict):
            raise model.ModelError(f"{source} must contain a JSON object")
        source_version = data.get("schema_version")
        if source_version not in (1, SCHEMA_VERSION):
            raise model.ModelError(
                f"{source}: schema_version={source_version!r}; "
                f"expected 1 or {SCHEMA_VERSION}")

        persona = data.get("persona")
        verticals = data.get("verticals")
        host = data.get("host")
        install_mode = data.get("install_mode")
        out = data.get("out")
        marketplace = data.get("marketplace")
        installed_version = data.get("installed_version")
        kiro = data.get("kiro")
        codex = data.get("codex")

        if not isinstance(persona, str) or not model.SLUG.match(persona):
            raise model.ModelError(f"{source}: persona must be a lowercase kebab-case string")
        if not isinstance(verticals, list) or any(
                not isinstance(value, str) or not model.SLUG.match(value)
                for value in verticals):
            raise model.ModelError(f"{source}: verticals must be kebab-case strings")
        if len(verticals) != len(set(verticals)):
            raise model.ModelError(f"{source}: verticals contains duplicates")
        if host not in HOSTS:
            raise model.ModelError(f"{source}: host={host!r} must be one of {HOSTS}")
        if install_mode not in INSTALL_MODES:
            raise model.ModelError(
                f"{source}: install_mode={install_mode!r} must be one of {INSTALL_MODES}")
        for label, value in (
            ("out", out),
            ("marketplace", marketplace),
            ("installed_version", installed_version),
        ):
            if not isinstance(value, str) or not value.strip():
                raise model.ModelError(f"{source}: {label} must be a non-empty string")
        if not isinstance(kiro, dict):
            raise model.ModelError(f"{source}: kiro must be an object")

        skills_dir = kiro.get("skills_dir")
        agents_dir = kiro.get("agents_dir")
        mcp_config = kiro.get("mcp_config")
        if source_version == 1 and agents_dir is None and isinstance(skills_dir, str):
            if PureWindowsPath(skills_dir).is_absolute() and not Path(skills_dir).is_absolute():
                agents_dir = str(PureWindowsPath(skills_dir).parent / "agents")
            else:
                agents_dir = str(Path(skills_dir).parent / "agents")
        for label, value in (
            ("skills_dir", skills_dir),
            ("agents_dir", agents_dir),
            ("mcp_config", mcp_config),
        ):
            if not isinstance(value, str) or not (
                    Path(value).is_absolute() or PureWindowsPath(value).is_absolute()):
                raise model.ModelError(f"{source}: kiro.{label} must be an absolute path")

        if source_version == 1 and codex is None:
            home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
            codex = {
                "agents_dir": str(home / "agents"),
                "config": str(home / "config.toml"),
            }
        if not isinstance(codex, dict):
            raise model.ModelError(f"{source}: codex must be an object")
        codex_agents = codex.get("agents_dir")
        codex_config = codex.get("config")
        for label, value in (
            ("agents_dir", codex_agents),
            ("config", codex_config),
        ):
            if not isinstance(value, str) or not (
                    Path(value).is_absolute() or PureWindowsPath(value).is_absolute()):
                raise model.ModelError(f"{source}: codex.{label} must be an absolute path")

        return cls(
            persona=persona,
            verticals=tuple(verticals),
            host=host,
            install_mode=install_mode,
            out=out,
            marketplace=marketplace,
            installed_version=installed_version,
            kiro_skills_dir=skills_dir,
            kiro_agents_dir=agents_dir,
            kiro_mcp_config=mcp_config,
            codex_agents_dir=codex_agents,
            codex_config=codex_config,
        )


def receipt_path(root: Path, configured: str | Path | None = None) -> Path:
    candidate = Path(configured).expanduser() if configured else DEFAULT_RECEIPT
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def load(path: Path) -> InstallReceipt:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise model.ModelError(
            f"{path} not found. Run `python3 -m skillforge install ...` once to record a selection.")
    except (OSError, ValueError) as exc:
        raise model.ModelError(f"{path} is not valid readable JSON: {exc}")
    return InstallReceipt.from_dict(data, path)


def write(path: Path, receipt: InstallReceipt) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(receipt.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def remove(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def project_version(root: Path) -> str:
    path = root / "skillforge.json"
    if not path.is_file():
        return "0.0.0"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise model.ModelError(f"{path} is not valid readable JSON: {exc}")
    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        raise model.ModelError(f"{path}: version must be a non-empty string")
    return version

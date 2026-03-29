"""Package version helpers for prefactor-langchain."""

from __future__ import annotations

import tomllib
from importlib import metadata
from pathlib import Path

PACKAGE_NAME = "prefactor-langchain"
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def resolve_package_version(distribution_name: str, package_root: Path) -> str:
    """Return the installed package version with a source-tree fallback."""
    try:
        return metadata.version(distribution_name)
    except metadata.PackageNotFoundError:
        pyproject_path = package_root / "pyproject.toml"
        try:
            with pyproject_path.open("rb") as pyproject_file:
                project = tomllib.load(pyproject_file).get("project", {})
        except FileNotFoundError:
            return "0.0.0"
        return str(project.get("version", "0.0.0"))


PACKAGE_VERSION = resolve_package_version(PACKAGE_NAME, _PACKAGE_ROOT)

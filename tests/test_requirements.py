"""``requirements.txt`` (for hosts that expect it, PRD 9.4) stays in step with pyproject.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _requirements() -> list[str]:
    lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def test_requirements_match_runtime_dependencies() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert sorted(_requirements()) == sorted(project["dependencies"])


def test_requirements_have_no_dev_tools() -> None:
    names = {r.split(">")[0].split("=")[0].split("<")[0].lower() for r in _requirements()}
    assert not names & {"pytest", "ruff", "hypothesis", "pytest-xdist"}

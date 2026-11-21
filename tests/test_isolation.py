"""Package boundary check (PRD 4.7): the engine never touches synthetic data or truth files."""

import ast
from pathlib import Path

import tieout

FORBIDDEN_MODULES = {"synthetic", "evaluation"}
TRUTH_PATH = "data/truth"


def _violations(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names = [node.module or ""]
        else:
            names = []
        found += [f"{path}: imports {n}" for n in names if n.split(".")[0] in FORBIDDEN_MODULES]
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and TRUTH_PATH in node.value
        ):
            found.append(f"{path}: string literal mentions {TRUTH_PATH}")
    return found


def test_tieout_does_not_reach_synthetic_or_truth() -> None:
    root = Path(tieout.__file__).parent
    problems = [v for py in sorted(root.rglob("*.py")) for v in _violations(py)]
    assert not problems, "\n".join(problems)

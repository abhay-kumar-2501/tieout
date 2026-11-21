import ast
import csv
from pathlib import Path

import numpy as np

import synthetic
from synthetic.abbreviations import ABBREVIATIONS
from synthetic.config import COMPANIES
from synthetic.names import NameFactory, denylist, is_denied

ENGINE_ABBREVIATIONS = (
    Path(__file__).resolve().parents[2] / "tieout" / "reference" / "abbreviations.csv"
)


def test_denylist_has_at_least_200_names():
    assert len(set(denylist())) >= 200


def test_denylist_screen_catches_real_names():
    for name in (
        "Grainger Industrial Supply",
        "FASTENAL CO",
        "Timken Bearing Inc",
        "S K F",
        "mcmaster carr",
    ):
        assert is_denied(name), name
    assert not is_denied("Corvane Fastening Inc")


def test_generated_names_pass_the_screen(small):
    vendors = {v.record.entity.name for c in COMPANIES for v in small.vendors[c]}
    vendors |= {p.name for p in small.world.parents}
    makers = {m.name for m in small.world.manufacturers}
    assert vendors and makers
    assert not [n for n in sorted(vendors | makers) if is_denied(n)]


def test_name_factory_stems_are_unique():
    factory = NameFactory(np.random.default_rng(0))
    stems = [factory.stem() for _ in range(2000)]
    assert len(set(s.lower() for s in stems)) == len(stems)


def test_synthetic_never_imports_engine_or_evaluation():
    root = Path(synthetic.__file__).parent
    problems = []
    for path in sorted(root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            problems += [
                f"{path.name}: {n}" for n in names if n.split(".")[0] in {"tieout", "evaluation"}
            ]
    assert not problems


def test_abbreviations_overlap_engine_dictionary_by_about_80_percent():
    with ENGINE_ABBREVIATIONS.open(encoding="utf-8", newline="") as handle:
        engine = {(r["abbr"].upper(), r["expansion"].upper()) for r in csv.DictReader(handle)}
    ours = set(ABBREVIATIONS)
    overlap = len(ours & engine) / len(ours)
    assert 0.75 <= overlap <= 0.85, overlap

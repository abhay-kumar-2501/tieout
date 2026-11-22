"""Build the extra sample mergers and the sample manifest ``data/samples.json``.

The first sample is the held-out demo seed (4, default profile), built by the
earlier steps of ``make demo`` into ``data/demo/``; the accuracy scorecard on
the landing page and in the README is measured on it alone. Each extra sample is
a new seed (never used for tuning) generated with a named profile from
``synthetic/profiles.py``, run end to end through the engine exactly as the demo
is, and scored against its own hidden truth with the evaluation code. Its
results, scorecard and sensitivity curves go to ``data/samples/<id>/``; its
generated inputs and truth go to ``data/seeds/<id>/`` (not committed: generation
is byte-identical per seed and profile).

Run: ``python scripts/make_samples.py [--only ID ...] [--manifest-only]``
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MANIFEST = ROOT / "data" / "samples.json"
REPORT_DATE = "2026-01-15"

#: The samples, in display order. ``title`` is a neutral description; the label adds the
#: combined in-scope spend read from the results, so it is true by construction.
SAMPLES: tuple[dict[str, Any], ...] = (
    {
        "id": "demo",
        "seed": 4,
        "profile": "default",
        "scale": 1.0,
        "title": "Two mid-size manufacturers",
        "dir": "data/demo",
    },
    {
        "id": "bolt_on",
        "seed": 5,
        "profile": "bolt_on",
        "scale": 0.6,
        "title": "Small bolt-on acquisition",
        "dir": "data/samples/bolt_on",
    },
    {
        "id": "messy_data",
        "seed": 6,
        "profile": "messy",
        "scale": 0.5,
        "title": "Merger with messy master data",
        "dir": "data/samples/messy_data",
    },
    {
        "id": "high_overlap",
        "seed": 7,
        "profile": "high_overlap",
        "scale": 0.6,
        "title": "Two firms with overlapping suppliers",
        "dir": "data/samples/high_overlap",
    },
)
TUNING_SEEDS_USED = {1, 2, 3}


def label(title: str, spend: float) -> str:
    return f"{title}, ${spend / 1e6:,.0f}M combined spend"


def build_sample(sample: dict[str, Any]) -> dict[str, float | None]:
    """Generate, score and run one extra sample; returns the tool's metrics on its own truth."""
    from evaluation.evaluate import SeedTruth, baseline_metrics, tool_metrics
    from evaluation.scorecard import build_scorecard, read_scorecard, write_scorecard
    from evaluation.seeds import SeedFiles
    from evaluation.sensitivity import threshold_sensitivity, write_sensitivity
    from synthetic.generate import generate, write
    from synthetic.profiles import profile_config
    from tieout.pipeline import PipelineInputs, run_pipeline

    seed = sample["seed"]
    assert seed not in TUNING_SEEDS_USED and seed != 4, f"seed {seed} is reserved"
    inputs = ROOT / "data" / "seeds" / sample["id"]
    files = SeedFiles(seed, inputs, inputs / "truth")
    dataset = generate(seed, scale=sample["scale"], config=profile_config(sample["profile"]))
    write(dataset, files.inputs, files.truth)

    def run(scorecard: dict | None = None, sensitivity: dict | None = None):
        return run_pipeline(
            PipelineInputs(
                acquirer=files.acquirer,
                target=files.target,
                category_map=files.category_map,
                vendor_parents=files.vendor_parents,
                as_of=REPORT_DATE,
                scenario="demo",
                scorecard=scorecard,
                sensitivity=sensitivity,
            )
        )

    first = run()
    truth = SeedTruth.load(files.truth)
    tool, baseline = tool_metrics(first, truth), baseline_metrics(first, truth)
    # The tuning-seed rows are the demo scorecard's: same thresholds, same tuning seeds.
    demo = read_scorecard(ROOT / "data" / "demo" / "scorecard.json")
    tuning = [int(s) for s in demo["tuning_seeds"]]
    scorecard = build_scorecard(
        tuning_seeds=tuning,
        held_out_seed=seed,
        tool_tuning={s: demo["tool"]["tuning"][str(s)] for s in tuning},
        tool_held_out=tool,
        baseline_tuning={s: demo["baseline"]["tuning"][str(s)] for s in tuning},
        baseline_held_out=baseline,
    )
    scorecard["thresholds"] = demo.get("thresholds", {})
    scorecard["sample"] = {"id": sample["id"], "profile": sample["profile"]}
    sensitivity = threshold_sensitivity(first)

    out = ROOT / sample["dir"]
    write_scorecard(scorecard, out / "scorecard.json")
    write_sensitivity(sensitivity, out / "sensitivity.json")
    final = run(scorecard, sensitivity)
    shutil.rmtree(out / "results", ignore_errors=True)
    final.save(out / "results")
    return tool


def manifest() -> dict[str, Any]:
    """The manifest the app and the landing-page generator read."""
    rows = []
    for sample in SAMPLES:
        results = ROOT / sample["dir"] / "results" / "results.json"
        meta = json.loads(results.read_text(encoding="utf-8"))["meta"]
        spend = float(meta["in_scope_spend"]["total"])
        rows.append(
            {
                "id": sample["id"],
                "label": label(sample["title"], spend),
                "title": sample["title"],
                "seed": sample["seed"],
                "profile": sample["profile"],
                "scale": sample["scale"],
                "results": f"{sample['dir']}/results",
                "scorecard": f"{sample['dir']}/scorecard.json",
            }
        )
    return {"held_out_seed": SAMPLES[0]["seed"], "samples": rows}


def write_manifest(path: Path = MANIFEST) -> None:
    path.write_text(json.dumps(manifest(), indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="*", help="sample ids to build (default: all extras)")
    parser.add_argument("--manifest-only", action="store_true", help="only rewrite the manifest")
    args = parser.parse_args(argv)
    if not args.manifest_only:
        for sample in SAMPLES[1:]:
            if args.only and sample["id"] not in args.only:
                continue
            metrics = build_sample(sample)
            shown = ", ".join(f"{k} {v:.3f}" for k, v in metrics.items() if v is not None)
            print(f"{sample['id']} (seed {sample['seed']}, {sample['profile']}): {shown}")
    write_manifest()
    print(f"Wrote {MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

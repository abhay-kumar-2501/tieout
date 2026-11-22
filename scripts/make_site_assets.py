"""Write the landing page's sample outputs and figures to ``site/`` (PRD 7.3, 9.2, 9.4).

Run by ``make demo`` after the sample results are written. It reads the sample
manifest (``data/samples.json``), each sample's committed results and the
held-out scorecard, and writes, per sample, the bridge image, the sample
workbook and the sample deck (all in the clean-team view), then regenerates
``site/data.js`` from the same files. The first sample (the held-out demo seed)
keeps the original paths under ``site/assets/``; the others go to
``site/assets/samples/<id>/``. It never writes to ``data/``.

Run: ``python scripts/make_site_assets.py [--manifest FILE] [--scorecard FILE] [--site DIR]``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_JS_HEADER = (
    "// Regenerated from data/samples.json, each sample's results.json and "
    "data/demo/scorecard.json.\n"
)
ASSET_NAMES = {
    "bridge": "bridge.png",
    "workbook": "tieout_workbook.xlsx",
    "deck": "tieout_deck.pptx",
}


def asset_paths(sample_id: str, first: bool) -> dict[str, str]:
    """Site-relative paths of one sample's three downloads."""
    folder = "assets/" if first else f"assets/samples/{sample_id}/"
    return {key: folder + name for key, name in ASSET_NAMES.items()}


def load_manifest(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["samples"]


def sample_object(sample: dict[str, Any], results_json: dict, first: bool) -> dict:
    """One sample's figures, as the landing page reads them."""
    totals = results_json["totals"]
    lever1 = totals["lever1"]
    return {
        "id": sample["id"],
        "label": sample["label"],
        "naive": lever1["naive"],
        "defensible_recurring": totals["recurring"],
        "lever1": {
            "defensible": lever1["bridge"]["defensible"],
            "steps": [lever1["bridge_raw"][f"step_{i}"] for i in range(1, 8)],
        },
        "assets": asset_paths(sample["id"], first),
    }


def scorecard_object(scorecard: dict) -> dict:
    """The held-out scorecard, the same for every sample."""
    metrics = {}
    for key, value in scorecard["tool"]["held_out"].items():
        target = scorecard.get("targets", {}).get(key)
        metrics[key] = {
            "tool": value,
            "baseline": scorecard["baseline"]["held_out"][key],
            "target": target["bound"] if target else None,
            "direction": target["direction"] if target else None,
        }
    return {"held_out_seed": scorecard["held_out_seed"], "metrics": metrics}


def data_js_object(samples: list[tuple[dict, dict]], scorecard: dict) -> dict:
    """``samples`` pairs each manifest row with its ``results.json``."""
    currency = samples[0][1]["meta"].get("currency", "USD")
    return {
        "currency": currency,
        "samples": [sample_object(s, r, i == 0) for i, (s, r) in enumerate(samples)],
        "scorecard": scorecard_object(scorecard),
    }


def data_js_text(samples: list[tuple[dict, dict]], scorecard: dict) -> str:
    """The text of ``site/data.js``."""
    body = json.dumps(data_js_object(samples, scorecard), indent=2)
    return f"{DATA_JS_HEADER}const TIEOUT = {body};\n"


def read_samples(manifest: Path, root: Path = ROOT) -> list[tuple[dict, dict]]:
    rows = []
    for sample in load_manifest(manifest):
        path = root / sample["results"] / "results.json"
        rows.append((sample, json.loads(path.read_text(encoding="utf-8"))))
    return rows


def write_site_assets(manifest: Path, scorecard_path: Path, site: Path) -> dict[str, int]:
    """Write every sample's three assets and ``data.js`` under ``site``; returns sizes in bytes."""
    from tieout.export.charts import bridge_png
    from tieout.export.deck import build_deck
    from tieout.export.workbook import build_workbook
    from tieout.results import Results

    builders = {"bridge": bridge_png, "workbook": build_workbook, "deck": build_deck}
    samples = read_samples(manifest)
    sizes: dict[str, int] = {}
    for i, (sample, _) in enumerate(samples):
        results = Results.load(ROOT / sample["results"])
        for key, rel in asset_paths(sample["id"], i == 0).items():
            data = builders[key](results, "clean")
            path = site / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            sizes[rel] = len(data)
    scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    text = data_js_text(samples, scorecard)
    (site / "data.js").write_text(text, encoding="utf-8")
    return sizes | {"data.js": len(text.encode())}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=ROOT / "data" / "samples.json")
    parser.add_argument("--scorecard", type=Path, default=ROOT / "data" / "demo" / "scorecard.json")
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    args = parser.parse_args(argv)
    for name, size in write_site_assets(args.manifest, args.scorecard, args.site).items():
        print(f"site/{name}: {size / 1_000_000:.2f} MB")


if __name__ == "__main__":
    main()

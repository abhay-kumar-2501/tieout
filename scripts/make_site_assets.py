"""Write the landing page's sample outputs and figures to ``site/`` (PRD 7.3, 9.2, 9.4).

Run by ``make demo`` after the demo results are written. It reads the committed
demo results and scorecard and writes, under ``site/assets/``, the bridge image,
the sample workbook and the sample deck (all in the clean-team view), and
regenerates ``site/data.js`` from the same files. It never writes to
``data/demo/``.

Run: ``python scripts/make_site_assets.py [--results DIR] [--scorecard FILE] [--site DIR]``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_JS_HEADER = (
    "// Regenerated from data/demo/results/results.json and data/demo/scorecard.json.\n"
)
ASSETS = ("bridge.png", "tieout_workbook.xlsx", "tieout_deck.pptx")


def data_js_object(results_json: dict, scorecard: dict) -> dict:
    """The figures the landing page shows, in the order ``site/data.js`` has always had."""
    totals = results_json["totals"]
    lever1 = totals["lever1"]
    metrics = {}
    for key, value in scorecard["tool"]["held_out"].items():
        target = scorecard.get("targets", {}).get(key)
        metrics[key] = {
            "tool": value,
            "baseline": scorecard["baseline"]["held_out"][key],
            "target": target["bound"] if target else None,
            "direction": target["direction"] if target else None,
        }
    return {
        "currency": results_json["meta"].get("currency", "USD"),
        "naive": lever1["naive"],
        "defensible_recurring": totals["recurring"],
        "lever1": {
            "defensible": lever1["bridge"]["defensible"],
            "steps": [lever1["bridge_raw"][f"step_{i}"] for i in range(1, 8)],
        },
        "scorecard": {"held_out_seed": scorecard["held_out_seed"], "metrics": metrics},
    }


def data_js_text(results_json: dict, scorecard: dict) -> str:
    """The text of ``site/data.js``."""
    body = json.dumps(data_js_object(results_json, scorecard), indent=2)
    return f"{DATA_JS_HEADER}const TIEOUT = {body};\n"


def write_site_assets(results_dir: Path, scorecard_path: Path, site: Path) -> dict[str, int]:
    """Write the three assets and ``data.js`` under ``site``; returns file sizes in bytes."""
    from tieout.export.charts import bridge_png
    from tieout.export.deck import build_deck
    from tieout.export.workbook import build_workbook
    from tieout.results import Results

    results = Results.load(results_dir)
    assets = site / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    files = {
        "bridge.png": bridge_png(results, "clean"),
        "tieout_workbook.xlsx": build_workbook(results, "clean"),
        "tieout_deck.pptx": build_deck(results, "clean"),
    }
    for name, data in files.items():
        (assets / name).write_bytes(data)
    results_json = json.loads((results_dir / "results.json").read_text(encoding="utf-8"))
    scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    text = data_js_text(results_json, scorecard)
    (site / "data.js").write_text(text, encoding="utf-8")
    return {name: len(data) for name, data in files.items()} | {"data.js": len(text.encode())}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=ROOT / "data" / "demo" / "results")
    parser.add_argument("--scorecard", type=Path, default=ROOT / "data" / "demo" / "scorecard.json")
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    args = parser.parse_args(argv)
    for name, size in write_site_assets(args.results, args.scorecard, args.site).items():
        print(f"site/{'assets/' if name in ASSETS else ''}{name}: {size / 1_000_000:.2f} MB")


if __name__ == "__main__":
    main()

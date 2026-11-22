.PHONY: install lint format test demo samples site-assets

PYTHON ?= python
SEED4 := data/seeds/seed_4

install:
	pip install -e ".[dev]"

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

test:
	pytest

# Generate the held-out seed (sample 1, the demo dataset), score it, precompute the
# threshold sensitivity, run the engine on it and save the demo results with both
# embedded; then build the extra sample mergers and the landing page's sample outputs.
demo:
	"$(PYTHON)" -m synthetic --seed 4 --out $(SEED4) --truth-dir data/truth/seed_4
	cp $(SEED4)/vendor_parents.csv $(SEED4)/category_map.csv data/demo/
	"$(PYTHON)" -m evaluation score
	"$(PYTHON)" -m evaluation sensitivity
	rm -rf data/demo/results
	"$(PYTHON)" -m tieout run $(SEED4)/acquirer.csv $(SEED4)/target.csv --out data/demo \
		--category-map data/demo/category_map.csv --vendor-parents data/demo/vendor_parents.csv \
		--as-of 2026-01-15 --scenario demo --scorecard data/demo/scorecard.json \
		--sensitivity data/demo/sensitivity.json --no-exports
	$(MAKE) samples site-assets PYTHON="$(PYTHON)"

# The extra sample mergers (new seeds with named generator profiles), each run end to
# end and scored against its own truth, and the manifest data/samples.json. Reads
# data/demo/, so run it after the demo steps above.
samples:
	"$(PYTHON)" scripts/make_samples.py

# Every sample's bridge image, workbook and deck under site/assets/, and site/data.js.
site-assets:
	"$(PYTHON)" scripts/make_site_assets.py

.PHONY: install lint format test demo

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

# Generate the held-out seed (the demo dataset), run the engine on it and score it.
demo:
	$(PYTHON) -m synthetic --seed 4 --out $(SEED4) --truth-dir data/truth/seed_4
	cp $(SEED4)/vendor_parents.csv $(SEED4)/category_map.csv data/demo/
	$(PYTHON) -m tieout run $(SEED4)/acquirer.csv $(SEED4)/target.csv --out data/demo \
		--category-map data/demo/category_map.csv --vendor-parents data/demo/vendor_parents.csv \
		--as-of 2026-01-15
	$(PYTHON) -m evaluation score

# Architecture and module contracts

The product requirements are in [PRD.md](PRD.md). This file fixes the
interfaces between modules so they can be built and tested independently.
Section numbers (for example "PRD 4.3") refer to the PRD.

## Pipeline

```
load files ─► validate, FX, annualise ─► map categories, convert units ─► lines
lines ─► vendor records ─► match_vendors ─► vendor_map, vendor pairs
lines ─► item records   ─► match_items   ─► item_map, item pairs
lines + maps + assumptions ─► synergy (levers, bridge, risk, phasing) ─► Results
Results ─► app screens, workbook, deck   (one calculation, three surfaces)
```

Matching is expensive and cached; `recompute(results, assumptions)` re-runs
only the arithmetic.

## Package boundaries

| Package | May import | Must not import |
|---|---|---|
| `tieout/` | standard library, third-party libraries | `synthetic`, `evaluation`, `app`; no string literal containing `data/truth` |
| `synthetic/` | standard library, third-party libraries | `tieout`, `evaluation` |
| `evaluation/` | `tieout`, `synthetic` (to regenerate seeds) | `app` |
| `app/` | `tieout` | `synthetic`, `evaluation` |

## Identifiers

| Id | Format | Example |
|---|---|---|
| `vendor_key` | `{company}:{vendor_id}` | `acquirer:V00123` |
| `item_key` | `item_code`, or `MPN:{mpn_norm}\|{manufacturer_norm}` when `item_code` is blank | `FA-10023` |
| `item_record_id` | `{company}:{item_key}` | `target:FA-10023` |
| `line_id` | `{company}:{source_row}` | `acquirer:412` |
| `legal_entity_id` | `LE` + zero-padded integer, assigned in sorted `vendor_key` order of each cluster's smallest member | `LE00042` |
| `parent_id` | `P:` + normalised parent name when from the parent table, else the `legal_entity_id` | |
| `canonical_item_id` | `CI` + zero-padded integer, assigned in sorted order of each item's smallest `item_record_id` | `CI000317` |
| `pair_id` | PRD 4.5: `{type}\|{company}:{key}\|{company}:{key}`, sides sorted | |

`company` is always `acquirer` or `target`.

## Data frames

Column lists are the contract; modules may add columns but not rename these.

### `lines`

One row per input line that survived blocking validation and falls inside the
12-month window.

- Every PRD 3.1 column **as received** (text columns as strings, blanks as
  `None`).
- Added at load: `company`, `source_file`, `source_row` (1-based file row,
  header = row 1), `line_id`.
- Added by validation: `amount` (annualised `line_amount` in reporting
  currency), `unit_price_rc` (reporting currency per recorded `uom`),
  `quantity_ann` (annualised quantity), `price_comparable` (bool),
  `price_exclusion` (reason or `None`).
- Added by normalisation: `l1_code`, `l2_code` (`None` when unmapped),
  `family`, `uom_dimension`, `category_type`, `base_unit`, `base_factor`
  (base units per recorded unit; NaN when unconverted), `conv_status`
  (`confirmed` / `parsed` / `unconverted` / `none` for lines with no item),
  `qty_base` (annualised base-unit quantity), `price_base` (reporting currency
  per base unit), `vendor_key`, `item_key` (`None` when the line has neither
  item code nor MPN).
- Added after matching: `legal_entity_id`, `parent_id`, `canonical_item_id`.

### `vendor_records` (input to vendor matching)

`vendor_key`, `company`, `vendor_id`, `vendor_name`, `vendor_tax_id`,
`vendor_country`, `spend`. One row per `vendor_key`; the name is the most
frequent on its lines.

### `vendor_map`

`vendor_key`, `company`, `vendor_id`, `vendor_name`, `name_normalised`,
`legal_entity_id`, `parent_id`, `stage` (`V1` / `V2` / `V3` / `V4` / `human` /
`none`), `score`, `tier` (`A` / `B` / `None` for singletons).

### `item_records` (input to item matching)

`item_record_id`, `company`, `item_key`, `item_code`, `mpn`, `manufacturer`,
`description`, `l2_code`, `family`, `spend`. Only records with a mapped
`l2_code`.

### `item_map`

`item_record_id`, `company`, `item_key`, `canonical_item_id`, `partner_id`
(the matched record on the other side, or `None`), `stage` (`I1` / `I3` /
`human` / `none`), `score`, `tier`, `attributes` (JSON text of parsed critical
attributes).

### `pairs` (vendor and item candidates; also the cached pair scores)

`pair_id`, `type` (PRD 4.5 queue types), `key_a`, `key_b`, `score`, `stage`,
`tier`, `evidence` (plain-language text), `status` (`auto` / `pending` /
`approved` / `rejected` / `deferred` / `vetoed`).

### Review decisions

PRD 4.5 file format: `pair_id`, `type`, `decision`, `pack_qty`, `note`,
`decided_at`.

## Function contracts

```python
# tieout/ingest
load_file(path_or_buffer, company, mapping=None) -> pd.DataFrame            # raw, PRD 3.1 names
prepare(acq, tgt, *, fx, taxonomy, category_map=None, period_end=None,
        aggregated=False, reporting_currency="USD") -> Prepared             # .lines, .data_quality, .meta

# tieout/match
build_vendor_records(lines) -> pd.DataFrame
match_vendors(records, parents=None, *, auto_threshold=92.0, review_threshold=75.0,
              decisions=None, cached_pairs=None) -> VendorMatch             # .vendor_map, .pairs
build_item_records(lines) -> pd.DataFrame
match_items(records, *, auto_cosine=0.80, review_cosine=0.60,
            decisions=None, cached_pairs=None) -> ItemMatch                 # .item_map, .pairs

# tieout/pipeline.py
run_pipeline(inputs, assumptions=None, decisions=None) -> Results
recompute(results, assumptions) -> Results                                  # arithmetic only
apply_decisions(results, decisions) -> Results                              # re-assembly + arithmetic
```

When `cached_pairs` is given, pair scoring is skipped and only clustering /
one-to-one assembly re-runs (PRD 4.5).

`Results` is the frozen dataclass described in PRD 9.2 and lives in
`tieout/results.py`.

## Conventions

- Deterministic: every sort is stable with explicit tie-break keys; no
  dependence on input row order or hash seeds.
- No pickle; frames persist as Parquet. Uploaded data is never logged or
  written to disk.
- Defaults that the PRD calls assumptions live in one place
  (`tieout/assumptions.py`), not scattered as literals.
- Tests live under `tests/<package>/` and use small inline fixtures; anything
  that needs the full demo dataset is marked `@pytest.mark.slow`.
- Choices the PRD leaves open are recorded in `BUILD_NOTES.md`.

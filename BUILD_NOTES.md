# Build notes

Decisions and shortfalls recorded while building Tie-Out.

## Foundations

- `Results` holds `meta`, `assumptions`, `totals`, `trace` and `scorecard` as plain JSON in `results.json`; frames are Parquet. `scorecard` is `None` or a dictionary.
- `Results.empty()` uses zero-column data frames; real column sets arrive with the modules that fill them.
- `DEFAULTS` in `tieout/assumptions.py` is a nested dictionary. Probability triples are `{"low", "base", "high"}` mappings; reference bands are `{"low", "high"}` mappings holding fractions (0.01 means 1%).
- Capture probabilities, discounts, caps, ramp values and other shares are validated to lie in [0, 1]; reference bands need 0 <= low <= high. Days, months and dollar defaults are not range-checked.
- `merge_overrides` deep-merges user overrides over the defaults and does not validate; callers run `validate` on the merged result.
- The CLI returns exit code 2 when an input file is missing (the PRD's blocking-error code), and 1 while the pipeline is not wired in.

# Tie-Out — Product Requirements Document

**A clean-team workbench for procurement synergy sizing in mergers**

| | |
|---|---|
| Project name | Tie-Out (package and repository name `tieout`) |
| Document status | Draft v1.0 for build |
| Product type | Open-source showcase project, single developer, free hosting |
| Primary audience | M&A and operations consulting professionals, procurement integration leads, recruiters |

**How to read this document.** Priorities are marked **P0** (the product is not credible without it), **P1** (expected in the first public release) and **P2** (stretch). Every numeric default in this document is an *assumption the user can change*, not an industry benchmark, unless a source is cited next to it.

**For the builder.** This document is written to be built from without asking questions. Where a rule is stated in two places, the more specific statement governs. Tasks that only a person can do are listed in 11.1 and are not build requirements. If something is still undecided, choose the simplest option consistent with 4.1 and 6.1, record the choice in `BUILD_NOTES.md`, and continue.

---

## 1. Problem statement and value proposition

### 1.1 The real problem

When two companies agree to merge, the deal model contains a procurement synergy number. That number is first set top-down during diligence, then has to be rebuilt bottom-up from both companies' purchasing data before anyone will commit to it. The bottom-up work is tedious and error-prone:

- The two companies run different ERP systems with different vendor masters, item masters, category taxonomies and units of measure.
- The same supplier appears under many names, and the same physical item under unrelated item codes.
- The first-pass answer ("pay the lower of the two prices on everything") is almost always too big. Much of the apparent price gap comes from unit-of-measure errors, freight terms, specification differences, contract lock-ins and wrong matches.

The hard part is not finding a large number. It is getting from the naive number to one a CFO will sign, and being able to show the working.

### 1.2 Timing and legal context (why this is a clean-team tool)

Between signing and close the two companies are still independent, often competitors, and supplier prices are among the most competitively sensitive data they hold. Exchanging that data improperly before close can breach competition law, and can form part of what regulators call "gun-jumping" (acting as one company before the deal is cleared and closed). In practice the detailed comparison is done by a **clean team**: a restricted group, often outside advisers, who may see both parties' data and who pass only aggregated or masked results to the integration office until the deal closes. What leaves the clean team is normally cleared by antitrust counsel first.

Tie-Out is framed as the clean team's workbench for the period **between signing and close**, with outputs that remain useful for Day-1 negotiation planning. It is not a "post-Day-1 spreadsheet cleaner".

> Tie-Out does not provide legal advice. Its masked view (section 6.9) is a presentation mode, not an access control.

### 1.3 What already exists (stated honestly)

This workflow is not new, and the product does not claim to be.

- **Consulting firms** run it with proprietary tooling and benchmark libraries (for example BCG/Inverto, Bain, McKinsey Spendscape, Efficio).
- **Spend-analytics vendors** sell classification, supplier resolution and savings tracking (for example Sievo, SpendHQ, Coupa, Jaggaer, GEP, Tamr, Creactives).
- **General tools** (Excel Power Query fuzzy merge, Alteryx, OpenRefine, Splink) cover the matching step alone.

What these do not offer publicly is an open, inspectable implementation in which every matching rule, every formula and every dollar can be audited. That is the gap Tie-Out fills, and the reason it exists as a showcase: it demonstrates judgement about *where naive synergy maths goes wrong*, not novelty of workflow.

### 1.4 Value proposition

> Tie-Out takes two messy purchasing extracts and produces a synergy estimate that is smaller than the naive one, expressed as a range, measured for accuracy, and traceable from every dollar back to the source rows.

Four promises, each backed by a feature:

| Promise | Feature |
|---|---|
| The number is defensible | Naive-to-defensible bridge (5.2) |
| The matching is measured, not asserted | Accuracy scorecard against hidden ground truth (4.7) |
| Every dollar ties out | Click-through traceability (6.6) and a formula-live workbook (7.1) |
| The tool knows its limits | "What this analysis cannot see" (6.10) on screen, in the deck and in the workbook |

### 1.5 Non-goals

- No live ERP connectors; input is file upload only.
- No contract text analysis, rebate agreements or supplier financial data.
- No multi-user accounts, permissions or persistence between sessions.
- No item-level analysis of spend that has neither an item code nor an MPN, typically services (it is sized and reported, then handled at vendor and category level only).
- Not a replacement for category-manager judgement; it prioritises where to look.

---

## 2. Personas and user flows

### 2.1 Personas

| Persona | Context | Needs | Success looks like |
|---|---|---|---|
| **The reviewer** (consulting partner, PE operating partner, recruiter) | Arrives from a link, has two minutes, has seen many dashboards | To judge quickly whether the builder understands the work | Sees the naive-versus-defensible bridge in the first screen and clicks further out of curiosity |
| **The clean-team analyst** | Has two extracts and a deadline | Fast triage of uncertain matches, confidence that nothing silly inflates the number | Clears the review queue in minutes and exports a workbook a manager can audit |
| **The integration lead** | Must not see supplier-level prices before close | A committed range, a phased plan, a list of risks | Reads the masked summary and the deck without needing the tool |
| **The technical reviewer** | Reads the repository | Evidence of evaluation, tests and sound design choices | Finds the scorecard, the baseline comparison and the tie-out tests |

### 2.2 Flow A — demo mode (P0)

The demo must give a result before it asks for anything.

1. **Landing page** (static, loads instantly): one-sentence pitch, the bridge chart as an image, a 90-second video, downloadable sample deck and workbook, and an "Open the live demo" button.
2. **Overview screen** opens with precomputed results for the fictional merger. No upload, no spinner, no configuration.
3. The first screen poses one question: *"The naive synergy figure is $X. The defensible range is $Y–$Z. Why?"*
4. Each screen ends with a single "next question" link that leads deeper (section 6.3). The reviewer can also jump freely using the navigation.
5. An optional guided tour: a "Take the 2-minute tour" button on the Overview opens a dialog with five steps, one per signature moment (section 6.2), each with a short text, a small image and a "Go there" link. It never starts automatically.

### 2.3 Flow B — custom upload (P1)

1. **Upload** two files (CSV or XLSX), one per company.
2. **Map columns**: the tool suggests a mapping from the user's headers to the schema; the user confirms or corrects. Required fields are marked.
3. **Validate**: a data-quality report lists blocking errors and non-blocking warnings with row counts and dollar value affected.
4. **Map categories**: each company's native categories are mapped to the common taxonomy; suggestions are editable.
5. **Run matching**: staged progress with real counts at each stage.
6. **Review queue**: triage uncertain vendor and item matches (section 6.5). Synergy figures update as decisions are made.
7. **Explore and adjust**: synergies, risk, roadmap, assumptions.
8. **Export**: workbook and deck.

Steps 1–6 live on the **Data** and **Matching** screens. The Data screen has a "Use your own data" button that switches the session to upload mode and shows a five-step stepper (Upload → Map columns → Validate → Map categories → Run). "Back to demo" restores the precomputed results.

- **Column suggestions:** exact match against a synonym list per field (`tieout/reference/column_synonyms.json`, authored by the builder), then `token_sort_ratio` ≥ 80 against the schema names.
- **Category suggestions:** score = Jaccard overlap between an L2's keyword set and the tokens of the native label plus its 20 highest-spend item descriptions. The top L2 is suggested if its score is ≥ 0.3; otherwise the category is left unmapped.
- **Limits:** 250,000 rows and 50 MB per file, with a clear message when exceeded.

A privacy notice sits on the upload step: *the public demo is not a place for real deal data; run the tool locally for that.* Uploaded data is held in session memory only and is never written to disk or logged: no disk-persisted caches, exports built in memory, and file names and contents never passed to logging.

---

## 3. Data schema

### 3.1 Input: purchasing lines

One file per company. One row per purchase-order line or invoice line. Pre-aggregated annual rows are also accepted in **aggregated mode** (`--aggregated` on the command line, a checkbox at upload): one row per vendor, item and site, with `quantity` holding the annual volume. In that mode `doc_date` is optional, no 12-month window or scaling is applied, the three-line benchmark test (5.2) is skipped, observed days-to-pay are unavailable, and the outputs say so.

| Column | Type | Required | Notes |
|---|---|---|---|
| `site` | text | yes | Plant, business unit or location |
| `doc_date` | date | yes (optional in aggregated mode) | PO date or invoice date; used for the 12-month window |
| `vendor_id` | text | yes | Company's own vendor number |
| `vendor_name` | text | yes | As stored in the vendor master |
| `vendor_tax_id` | text | no | Often missing; compared only within the same country |
| `vendor_country` | text (ISO 3166-1 alpha-2) | no | Upper-cased; anything that is not two letters is treated as blank |
| `item_code` | text | no | Blank for services and free-text purchases |
| `item_description` | text | yes | |
| `mpn` | text | no | Manufacturer part number |
| `manufacturer` | text | no | |
| `category_native` | text | yes | The company's own category label or code |
| `uom` | text | yes if `item_code` or `mpn` present | Unit of measure as recorded; upper-cased and trimmed before lookup |
| `pack_qty` | number | no | Base units per pack, when `uom` is a pack unit; ignored otherwise |
| `quantity` | number | yes | Negative for returns and credits |
| `unit_price` | number | yes | In `currency`, per `uom` |
| `line_amount` | number | yes | Expected to equal `quantity × unit_price` |
| `currency` | text (ISO 4217) | yes | |
| `payment_terms_days` | integer | no | Stated terms. If neither this nor `payment_date` is present in a file, lever 3 is switched off with a message |
| `payment_date` | date | no | Enables observed days-to-pay |
| `contract_id` | text | no | Carried through for traceability; not used in calculations |
| `contract_end_date` | date | no | Enables contract-aware phasing |
| `incoterm` | text | no | Used to flag freight-driven price gaps |
| `spend_type` | `direct` / `indirect` | no | Display and filtering only |
| `po_number` | text | no | Carried through for traceability |
| `po_line` | text | no | Carried through for traceability |

`company` (`acquirer` / `target`) and `source_row` (file row number) are added at load.

### 3.2 Optional reference files

| File | Purpose |
|---|---|
| `vendor_parents.csv` | Columns `key_type` (`name` or `tax_id`), `key`, `country` (optional), `parent_name`. Supplies corporate-hierarchy links that no string comparison can find. Name keys are compared after V0 normalisation (4.3), exact match |
| `category_map.csv` | Columns `company`, `category_native`, `l2_code`. Maps each company's categories to the common taxonomy |
| `fx_rates.csv` | Columns `currency`, `rate`, where amount × rate = reporting currency. Fixed rates; the tool never fetches live rates |
| `category_settings.csv` | Columns `l2_code`, `criticality`, `cap`, `d`, `pi1_same_low`, `pi1_same_base`, `pi1_same_high`, `pi1_switch_low`, `pi1_switch_base`, `pi1_switch_high`, `pi2_low`, `pi2_base`, `pi2_high`. A blank cell means "use the default" |

The reporting currency is an assumption, default USD. If no FX file is supplied, the shipped `tieout/reference/fx_rates.csv` is used (USD 1.00, CAD 0.73, EUR 1.08, GBP 1.27, labelled illustrative).

### 3.3 Validation rules

| Rule | Severity | Handling |
|---|---|---|
| Required column missing | Blocking | Cannot proceed |
| Unparseable date, number or currency | Blocking when more than 1% of that file's rows are affected, otherwise warning | Affected rows excluded and listed |
| `abs(line_amount − quantity × unit_price)` is greater than `max(0.01, 1% × abs(line_amount))` | Warning | `line_amount` is trusted for spend; the row is excluded from price comparison |
| `unit_price` ≤ 0 with positive quantity | Warning | Excluded from price comparison |
| Negative quantity | Info | Netted by summing quantity and amount within the same buying group and item |
| Currency missing from the FX table | Warning; blocking when more than 1% of that file's rows are affected | Affected rows excluded and listed |
| No `contract_end_date` anywhere | Info | Phasing falls back to the global ramp (5.6) |
| No `payment_date` anywhere | Info | Payment-terms lever uses stated terms and is labelled as such |
| Duplicate rows (identical on all fields) | Warning | Kept; count and value reported |

**Annualisation.** The window is the 12 calendar months ending at `period_end` (a month; default: the earlier of the two files' latest `doc_date` months). Lines outside the window are ignored and counted. Each file's scaling factor is 12 ÷ (the number of window months in which that file has at least one line); a factor above 1 is flagged on every output.

**In-scope spend** is the annualised `line_amount`, in reporting currency, of all rows not excluded by a blocking rule, including unmapped spend and spend without item codes. **Addressable spend** is in-scope spend in L2 categories where both companies have spend above zero.

### 3.4 Common category taxonomy

The two companies never share a taxonomy, so mapping is an explicit step, not an input assumption.

- The common taxonomy is the shipped, editable file `tieout/reference/taxonomy.csv` with exactly 12 L1 categories × 5 L2 categories = 60 rows.
- Columns: `l1_code`, `l1_name`, `l2_code`, `l2_name`, `keywords` (semicolon-separated), `family`, `uom_dimension`, `category_type`, `criticality`.
  - `family` ∈ {fasteners, bearings, pvf, electrical, ppe, abrasives, generic} selects the attribute parser (4.4).
  - `uom_dimension` ∈ {count, length, mass, volume, time} is the base dimension for the category (3.5).
  - `category_type` ∈ {commodity, engineered, mro, indirect} selects the default consolidation discount (5.3).
  - `criticality` ∈ {critical, standard, non_critical} selects the default concentration cap (5.5). Default `standard`; at least 6 L2 rows are `critical` and at least 10 `non_critical`.
- The 12 L1 categories are: Raw materials & metals; Fasteners & hardware; Bearings & power transmission; Pipe, valves & fittings; Electrical & automation; Abrasives & cutting tools; Safety & PPE; Packaging; Chemicals & lubricants; MRO general & facilities; Logistics & freight; Professional & IT services. The builder authors the 60 L2 rows. The last two L1 categories are `indirect` with `uom_dimension = time` and carry no item codes.
- Suggestions for mapping native categories are described in 2.3.
- Unmapped spend is reported by dollar value. Items in unmapped categories cannot be matched and are excluded from all levers.

### 3.5 Units of measure

**Fixed-factor units** are converted deterministically:

| Unit | Base | Factor |
|---|---|---|
| `EA`, `PC`, `UN` | each | 1 |
| `PR` | each | 2 (not applied in the `ppe` family, where a pair is usually the selling unit) |
| `DZ` | each | 12 |
| `GS`, `GRO` | each | 144 |
| `C` | each | 100 |
| `FT` | metre | 0.3048 |
| `IN` | metre | 0.0254 |
| `LB` | kilogram | 0.45359237 |
| `GAL` (US) | litre | 3.785411784 |
| `YD` | metre | 0.9144 |
| `MTR` | metre | 1 |
| `CM` | metre | 0.01 |
| `MM` | metre | 0.001 |
| `KG` | kilogram | 1 |
| `G`, `GM` | kilogram | 0.001 |
| `OZ` | kilogram | 0.028349523125 |
| `T`, `MT` | kilogram | 1000 |
| `L`, `LT` | litre | 1 |
| `ML` | litre | 0.001 |
| `HR` | hour | 1 |

Lines in a fixed-factor unit, or already in a base unit, have conversion status `confirmed`.

`M` and `GR` are ambiguous and are resolved by the category's `uom_dimension`: `M` is 1 metre if the dimension is length and 1,000 each if it is count; `GR` is 0.001 kilogram if the dimension is mass and 144 each if it is count. In any other dimension the line is `unconverted` and goes to review. An unrecognised unit is `unconverted`. If the two companies' base dimensions differ for a matched item, the item is excluded from price comparison and listed.

**Pack units** (`BX`, `CS`, `PK`, `BG`, `RL`, `DR`, `PL`) need an item-specific pack quantity, expressed in the category's base unit, resolved in this order:

1. `pack_qty` column: conversion status `confirmed`.
2. Parsed from the description using the patterns below: status `parsed`.
3. Otherwise: status `unconverted`. The line still counts as spend but is **excluded from price comparison**.

The description patterns are exactly these, case-insensitive, first match wins, where `N` is an integer from 2 to 10000. Nothing else is parsed.

```
(BOX|BX|CASE|CS|PACK|PK|PKG|BAG|BG|ROLL|RL)\s*(OF\s*)?N
N\s*/\s*(BX|CS|PK|BG|RL)
(BX|CS|PK|BG|RL)\s*/\s*N
N\s*(PER|PR)\s*(BOX|CASE|PACK|BAG)
N\s*(PC|PCS|EA|CT)\s*/?\s*(BX|CS|PK|BG)
```

**Suspected unit errors.** After item matching, compute for each matched item the ratio `r` = higher ÷ lower of the two companies' volume-weighted prices. It is computed on converted prices where both sides converted, and on recorded prices where either side is `unconverted` (for detection and display only). The pair is flagged when:

- (a) `r` is within ±3% (inclusive) of a factor in {2, 4, 5, 6, 8, 10, 12, 20, 24, 25, 48, 50, 100, 144, 1000} and either side's conversion status is not `confirmed`; or
- (b) `r` ≥ 3.0, whatever the conversion status.

Flagged pairs are excluded from savings and sent to the review queue. When (a) applies the message is "This {r:.1f}× price gap looks like a pack of {factor}, not a saving"; for (b) alone, "This {r:.1f}× gap is too large to be a price difference; check units".

---

## 4. Entity resolution

### 4.1 Design principles

1. **Deterministic evidence first.** Identifiers and exact matches decide. A similarity score alone only proposes; it becomes an automatic match only with the guards in 4.3 (vendors) or the attribute agreement in 4.4 (items).
2. **A wrong match is worse than a missed match**, because a wrong item match converts directly into false savings. The defaults favour precision.
3. **No transitive chaining.** A matches B and B matches C does not imply A matches C.
4. **Every match carries its evidence**: which stage made it, on what fields, with what score.
5. **Accuracy is measured** against ground truth the matcher has never seen (4.7).

**Why not a probabilistic linkage library such as Splink?** Those libraries are strongest when records have several independent fields to compare. Vendor records here often have little beyond a name and a sometimes-missing tax ID, and reviewers of a synergy case want to read the rule that merged two vendors. Tie-Out therefore uses transparent staged rules, and benchmarks them against a naive fuzzy baseline (4.7). A Splink comparison is a P2 stretch item.

### 4.2 Confidence tiers

| Tier | Meaning | Treatment in savings |
|---|---|---|
| **A** | Deterministic evidence or human approval | Included |
| **B** | Automatic match on similarity that passed the guards (vendors) or has corroborating attributes (items) | Included; savings from tier B are shown separately |
| **C** | Candidate awaiting review | Excluded from the range; shown as "upside pending review" |

An opportunity's tier is its item-match tier; the vendor-link tier is shown as a second attribute. Vendor links at tier C are treated as different vendors in every calculation.

### 4.3 Vendor matching

All vendor stages run over the union of both companies' vendor records (record key: company + `vendor_id`).

**V0. Normalise**, in this order:

1. Unicode NFKC, case-fold, strip accents.
2. Split "doing business as" names (`dba`, `d/b/a`, `t/a`) into separate aliases.
3. Move branch markers into a separate field: a trailing `- <words>`, `#<digits>`, or `(plant|site|branch|store|dc|whse) <alphanumerics>`.
4. `&` → `and`, remove punctuation, collapse whitespace, drop a leading "the".
5. Remove legal-form tokens **from the end of the name only**, repeatedly: inc, incorporated, corp, corporation, co, company, llc, ltd, limited, lp, llp, plc, gmbh, ag, sa, sas, srl, bv, nv, pty, ab, oy, kk.

The original name is always kept.

**V1. Tax ID.** Tax IDs are normalised to upper-case alphanumerics and compared only when both records have a country and the countries are equal; otherwise the tax ID is neither evidence nor veto. Same tax ID → merge, tier A. Two *different* tax IDs → **veto** on automatic merge. A veto applies to whole clusters: a record cannot join a cluster containing any member it is vetoed against, at any stage. Vetoed pairs with an exact normalised name or a fuzzy score ≥ 92 enter the review queue as type `vendor_sibling` (4.5).

**V2. Exact normalised name** → merge, tier A, unless vetoed. If a group of records with the same normalised name contains two or more distinct tax IDs in one country, the group is split by tax ID; records in that group without a tax ID are not merged automatically and go to review against each.

**V3. Parent table.** Any alias or tax ID listed in `vendor_parents.csv` is linked to its parent, tier A. Two identifiers are kept for every vendor: `legal_entity_id` (assigned by V1, V2 and V4) and `parent_id` (the V3 parent if listed, otherwise the legal entity). Price and payment-terms comparisons and concentration risk run at parent level; the audit trail keeps the legal entity.

**V4. Fuzzy candidates.**

- *Blocking.* Compare only pairs that share a rare token (a token appearing in fewer than 1% of the distinct normalised names of both companies combined) or the same first four characters after normalisation.
- *Score.* `score = 0.6 × token_sort_ratio + 0.4 × (100 × Jaro-Winkler similarity)`, using RapidFuzz (`rapidfuzz.fuzz.token_sort_ratio`, `rapidfuzz.distance.JaroWinkler.normalized_similarity`). `token_set_ratio` is deliberately not used for scoring, because it returns 100 whenever one name's tokens are a subset of the other's.
- *Guards.*
  - Generic tokens are removed before scoring, and the score is computed on what remains. The list is the shipped file `tieout/reference/generic_tokens.txt`: industrial, industries, supply, supplies, services, service, national, american, international, global, group, solutions, products, enterprises, holdings, systems, technologies, associates, partners, distribution, distributors, trading, usa, north, america.
  - If either name has fewer than two tokens left, or fewer than six characters excluding spaces, after generic-token removal, the score is capped at 91 (review at most, never automatic).
  - Descriptor tokens are the shipped file `tieout/reference/descriptor_tokens.txt`: logistics, freight, fasteners, bearings, electric, electrical, steel, metals, packaging, chemical, chemicals, tools, tooling, safety, hydraulics, pneumatics, plastics, rubber, valves, pumps, welding, abrasives, lubricants, staffing, consulting, software. They are not generic and are not removed. If both names contain descriptor tokens and the two sets are disjoint ("Apex Logistics" / "Apex Fasteners"), the score is capped at 74 (no match). If only one name has a descriptor token ("Apex" / "Apex Logistics"), the score is capped at 91.
- *Thresholds (starting defaults, tuned as in 4.7).* `score ≥ 92` → automatic, tier B, subject to V5. `75 ≤ score < 92` → review queue, tier C. Below 75 → no match.

**V5. Clustering.** Clusters start as the legal entities left after V1 and V2. Fuzzy pairs are processed in descending score order, ties broken by the lexical order of the pair's record keys. A pair scoring ≥ 92 is merged automatically only if the joining record also scores ≥ 75 against every *distinct normalised name* in the cluster that joined through V2 or V4 (names attached by tax ID or as a "doing business as" alias are not tested), and no veto exists against any member. Otherwise the pair goes to review as tier C. Parent links (V3) never take part in clustering. This prevents chains from growing into one oversized vendor, and makes the result independent of input order.

### 4.4 Item matching

Items are matched only across companies, only within the same common L2 category, and only for lines with an item code or MPN.

**Item records.** An item record's key is (company, `item_code`), or (company, normalised MPN, normalised manufacturer) when `item_code` is blank. Its description is the most frequent description on its lines, ties going to the longest.

**One-to-one matching.** Candidates are taken in the order I1, then I3 automatic, then I3 review, and within each by descending score, ties by record key. A record already matched at tier A or B takes no further automatic match; later candidates involving it become tier C. A canonical item is therefore one acquirer record, one target record, or one matched pair. Approving a tier C pair when either side already has a tier A or B partner is blocked with a message naming the partner. (Known simplification: two item codes for the same good inside one company are not merged.)

**I0. Normalise.** Upper-case, expand the abbreviation dictionary `tieout/reference/abbreviations.csv` (columns `abbr`, `expansion`; whole-token matches only; at least 80 entries authored by the builder, such as `BRG` → `BEARING`, `SS` → `STAINLESS STEEL`, `HX` → `HEX`), standardise separators in dimensions (`M8X40`, `M8 x 40`, `M8-40` → `M8X40`).

**I1. Manufacturer part number.** Same normalised MPN (alphanumerics only, upper-case, at least five characters including a digit) and compatible manufacturer → match, tier A. Manufacturers are compatible when they are equal after V0 normalisation, or either is blank, or their `token_sort_ratio` is ≥ 90. An MPN-like token extracted from a description rather than from the `mpn` column (pattern `[A-Z0-9][A-Z0-9\-/\.]{4,}`, containing both a letter and a digit and not matching a dimension pattern) counts only as a candidate for I3.

**I2. Attribute agreement.** Category-family parsers extract critical attributes:

| Family | Critical attributes |
|---|---|
| Fasteners | Thread, length, head type, material, grade, finish |
| Bearings | Full designation including suffixes |
| Pipe, valves, fittings | Nominal size, pressure class, material, end connection |
| Electrical | Voltage, current rating, poles, enclosure rating |
| Gloves and PPE | Type, material, size |
| Abrasives and cutting tools | Diameter, grit or geometry, bore |

The parser is chosen by the category's `family` (3.4). For the `generic` family the parser extracts every numeric-and-unit token, and each such token counts as one critical attribute. Pack-quantity tokens already parsed under 3.5 (the `12` in `BOX OF 12`) are removed first, so a pack difference is handled as a unit conversion and not mistaken for a different item.

**Veto rules.**

- Parser families: a **conflict** is a critical attribute extracted on both sides with different values. An attribute missing on one side is not a conflict. Any conflict is a hard veto, whatever the text similarity.
- Generic family: if the two sets of numeric-and-unit tokens are identical there is no conflict. If one set is a strict subset of the other, the pair can only go to review (tier C). If neither contains the other, it is a hard veto.
- A veto removes I3 candidates. An I1 match from the `mpn` column that has a conflict is demoted to tier C with the evidence "same MPN, conflicting attributes"; it is not deleted.

This is what keeps `M8X40` away from `M8X45`, and `6204-2RS` away from `6204-ZZ`.

**I3. Text similarity for candidates only.** TF-IDF on character n-grams (`TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))`) with cosine similarity. The vectoriser is fitted once on all normalised descriptions of both companies; pairs are scored only within the same L2. Thresholds are inclusive.

- Cosine ≥ 0.80, no veto, no subset-only case, and at least two critical attributes extracted on both sides and agreeing → automatic, tier B.
- Cosine ≥ 0.60 and no veto → review, tier C.
- Otherwise no match.

Text similarity never creates a match on its own.

### 4.5 Human review

Each candidate presents both records side by side with differences highlighted, the evidence for and against, and the annual dollars at stake. Decisions are `approve`, `reject` or `defer`, are recorded with a timestamp and optional note, and can be exported and re-imported so a review is not lost between sessions. Approved pairs become tier A. Rejected pairs are never proposed again.

**Queue item types and what Approve means:**

| Type | Approve | Reject |
|---|---|---|
| `vendor_match` | Merge into one legal entity (tier A) | Never proposed again |
| `vendor_sibling` | Keep separate legal entities under one common `parent_id` | Stay unrelated |
| `item_match` | Match (tier A) | Never proposed again |
| `unit_flag` | "This is a real price gap": the flag is cleared. For an unconverted pack the reviewer may instead enter a pack quantity, which sets the status to `confirmed` and re-runs the comparison | The pair stays out of savings |
| `incoterm` | "The terms are comparable" | The pair stays out of savings |

- Pair id: `{type}|{company}:{key}|{company}:{key}`, with the two sides sorted.
- Decisions file (CSV): `pair_id`, `type`, `decision`, `pack_qty`, `note`, `decided_at` (ISO 8601, UTC).
- A decision re-runs clustering and canonical-item assembly from cached pair scores, then the savings arithmetic; pair scoring is not re-run. Target under 2 seconds on the demo data.
- "Upside pending review" is the lever-1 base net saving that pending items would add if all were approved and passed every other filter.
- The demo opens with the queue undecided.

### 4.6 Spend without item codes

Lines with no item code and no MPN (typically services) are reported as **"not item-addressable"** with their dollar value and share of spend. They take part in vendor matching, the category-level consolidation lever and the payment-terms lever, never in price harmonisation.

### 4.7 Accuracy scorecard (P0)

The demo dataset is synthetic, which invites the objection that the tool simply finds what its author planted. The design answers this directly.

- **Separation.** The data generator writes truth files to `data/truth/seed_{n}/`:
  - `truth_vendor_map.csv`: `company`, `vendor_id`, `true_legal_entity`, `true_parent`
  - `truth_item_map.csv`: `company`, `item_key`, `true_item_id`
  - `truth_savings.csv`: `true_item_id`, `cause`, `true_gross_gap_usd`, `is_unit_trap`, `is_distractor`

  The isolation test has two parts: a scan of the syntax tree fails the build if any module under `tieout/` imports `synthetic` or `evaluation`, or contains a string literal with `data/truth`; and the pipeline is run with `data/truth` renamed away and must succeed. The scorecard is computed only by `evaluation/` and saved as `data/demo/scorecard.json`, which the app and exports read as an optional input.
- **Tuning versus reporting.** Seeds 1, 2 and 3 are for tuning. Seed 4 is held out and is also the demo dataset. `evaluation/tune.py` grid-searches the vendor automatic threshold from 85 to 97 in steps of 1 and the item automatic cosine from 0.70 to 0.90 in steps of 0.02, choosing the lowest values whose mean precision on seeds 1–3 is at least the target plus 0.005. The result is written to `tieout/reference/thresholds.toml`. The review thresholds stay at 75 and 0.60. Both sets of figures are published.
- **Metrics.**

| Metric | Definition |
|---|---|
| Pairwise precision | Correct matched pairs ÷ all matched pairs |
| Pairwise recall | Correct matched pairs ÷ all true pairs |
| Planted-savings recall | Dollars of true savings the tool found ÷ dollars of true savings planted |
| False-savings rate | Dollars of reported savings resting on wrong matches ÷ dollars of reported savings |
| Unit-error catch rate | Planted unit traps flagged ÷ planted unit traps |

Precise definitions: matched pairs are tier A and B only, before any human decision. Vendor pairs are all unordered pairs of vendor records sharing a `legal_entity_id` (true pairs: sharing `true_legal_entity`); parent links come from the supplied parent table and are not scored. Item pairs are cross-company pairs sharing a canonical item. Planted-savings recall = Σ min(tool gross gap, true gross gap) over truly matched items ÷ Σ true gross gap. False-savings rate = Σ tool gross gap on canonical items whose pair is not in truth ÷ Σ tool gross gap (both before capture probability). A unit trap is caught when bridge step 1 removes the item.

- **Targets on the held-out seed** (acceptance criteria, not claims): vendor precision ≥ 0.98 and recall ≥ 0.90; item precision ≥ 0.97 and recall ≥ 0.80; false-savings rate ≤ 2%; unit-error catch rate ≥ 0.95. Planted-savings recall is reported without a gate.
- **If a gate cannot be met.** If the held-out gate still fails after three cycles of tuning and fixing, the builder marks the gate test as an expected failure, publishes the actual figures on the scorecard, records the shortfall in `BUILD_NOTES.md`, and continues. The generator's difficulty is never reduced to pass the gate.
- **Baseline comparison.** The same data is run through the naive design: vendors by `token_set_ratio` ≥ 85 on lower-cased names over all pairs with connected-component clustering; items by word-level `TfidfVectorizer()` cosine ≥ 0.80 within L2, many-to-many, with no attribute veto; lever 1 then run with all bridge filters on. Both scorecards are shown side by side, with the false savings the naive design would have reported.
- **Sensitivity.** A chart of the base-case synergy figure with two lines: the vendor automatic threshold from 80 to 98 in steps of 2, and the item automatic cosine from 0.60 to 0.95 in steps of 0.05, each varied alone. It is precomputed for the demo, stored in `data/demo/sensitivity.json`, and hidden for uploaded data.
- **Real data (P2).** A run on a public purchasing dataset with supplier names, item descriptions and unit prices (candidate: the State of California purchase order data published on data.ca.gov), treating two departments as the two parties. There is no ground truth, so precision is estimated from a manually labelled random sample of 200 matches and reported with that caveat. That dataset has no unit-of-measure, part-number or item-code fields, so it can exercise vendor matching, description matching and price dispersion only, not unit conversion or part-number matching. For that run a hash of the normalised description stands in for `item_code`. Its licence must be confirmed before use. The whole real-data run is deferred to the human owner (11.1).

---

## 5. Synergy models

### 5.1 Structure

All prices are in the reporting currency per base unit. Baseline spend is the trailing-12-month in-scope spend of both companies.

Three levers, applied **in sequence on a declining baseline** so that no dollar is counted twice:

1. **Price harmonisation** (recurring, P&L) — P0
2. **Volume consolidation** (recurring, P&L) — P1
3. **Payment-terms harmonisation** (one-time, cash) — P1

Recurring savings and one-time cash are never added together, on any screen or export.

**Defensible range.** Everywhere in this document and the product, "the defensible range" means the total recurring run-rate saving (lever 1 + lever 2), from the low case to the high case.

**Opportunity.** The unit of analysis, prioritisation and traceability:

| Lever | One opportunity per | Id |
|---|---|---|
| 1 | (canonical item, change type), where change type is `same_vendor` or `switch`, aggregating all buying groups of that item with that change type | `L1:{canonical_item_id}:{change}` |
| 2 | L2 category | `L2:{l2_code}` |
| 3 | Parent vendor | `L3:{parent_id}` |

**Input validation.** Every probability triple must satisfy 0 ≤ low ≤ base ≤ high ≤ 1, and every discount and cap must lie in [0, 1]; the loader and the Assumptions screen reject anything else. Lookup order for a per-category value: `category_settings.csv` → the Assumptions screen's global value → the default in this document.

**Close date.** An assumption, default the first day of the month after the data window ends. Month 1 of year 1 is the close month. The planning horizon and all phasing are measured from it.

Every lever produces **low, base and high** values from per-category capture probabilities. Default probabilities are illustrative assumptions and are labelled as such wherever they appear.

### 5.2 Lever 1 — price harmonisation, with the naive-to-defensible bridge

**Eligible items:** matched across companies at tier A or B, unit conversion `confirmed` or `parsed`, no suspected unit error, no incoterm mismatch, at least one priced line on each side. Incoterm mismatch is tested per group against the benchmark holder using each side's dominant incoterm by spend; a blank on either side means "not assessed", not a mismatch.

For canonical item *k* and buying group *g* (company, site, parent vendor):

- `p[k,g]` = Σ line amount ÷ Σ base-unit quantity over the group's price-comparable lines, after netting credits
- `q[k,g]` = annualised base-unit quantity over the group's lines with a `confirmed` or `parsed` conversion

**Benchmark price.** `p*[k]` is the lowest `p[k,g]` among qualifying groups: those holding at least 10% (inclusive) of the item's combined annual quantity and having at least three purchase lines (the line test is skipped in aggregated mode). This excludes one-off spot buys.

- The **benchmark holder** is the company of that group. Ties on price go to the group with the larger quantity, then to the acquirer.
- **Fallback.** If no group qualifies, the holder is the company with the lower company-level volume-weighted price for the item, and `p*[k]` is that price.

**Merger synergy versus internal variance.** Every group belonging to the holder company is **internal variance**: its gap could have been captured without the deal, so it is reported separately and excluded from the synergy total. Every group of the other company with `p[k,g] > p*[k]` is merger synergy in full. (Known simplification: no part of the other company's gap is reclassified as internal, even if a sister site already pays close to the benchmark.)

**Change type.** A group is `same_vendor` when its parent vendor is the benchmark-holding group's parent vendor (in the fallback case: when its parent vendor also supplies the item to the holder company). Otherwise it is `switch`.

**Naive figure** (shown only for contrast):

```
Naive = Σ_k Σ_g ( p[k,g] − min_h p[k,h] ) × q[k,g]
```

computed on *all* matches including tier C (each record using only its single best candidate), with no unit-error, incoterm or contract filter, comparing unconverted pack units at their recorded price, and counting gaps inside one company as well as between the two. It uses the same validated rows as lever 1: rows excluded from price comparison under 3.3, and items with net quantity ≤ 0, are in neither figure. This is what a plain "best of both" formula would report.

**Bridge from naive to defensible.** Each step is a bar on the bridge chart and a filterable list of the items it removed:

| Step | Removes |
|---|---|
| 1. Unit-of-measure errors | Suspected unit errors and unconverted pack units |
| 2. Unverified matches | Tier C pairs (moved to "upside pending review") |
| 3. Spot-price benchmark | Difference between using the absolute minimum price and `p*[k]` |
| 4. Internal variance | Gaps against a benchmark held by the same company |
| 5. Non-comparable terms | Pairs where incoterms differ (when present); held for review, not counted |
| 6. Contract lock-in | Gap on volume under contract beyond the planning horizon (default 36 months) |
| 7. Capture probability | The share of the remaining gap not expected to be won in negotiation |

**Bridge computation.** Lever 1 is implemented as one function `lever1(filters, case)` with seven switchable filters in the order of the table. `F_0` is the figure with every filter off and every probability at 1, which is the naive figure. `F_i` is the figure with filters 1 to *i* on. Step *i* = `F_(i−1) − F_i`. A dollar is therefore attributed to the first step that removes it, and the steps sum exactly to `F_0 − F_7`. If a step comes out negative it is set to zero and the difference is added to the next step. Steps 1–6 are the same in every case; step 7 uses the base-case probabilities.

**Bridge chart.** The seven removal steps end on a bar "Defensible price harmonisation (lever 1)". One additive bar "+ Volume consolidation (lever 2)" follows, ending on "Defensible run-rate saving", with the low–high range marked on that final bar.

**Gross addressable gap:**

```
G1[k,g] = max(0, p[k,g] − p*[k]) × q[k,g] × a[k,g]
```

This is computed for each group *g* whose benchmark is held by the other company. `a[k,g]` is the share of the group's quantity on lines whose `contract_end_date` is blank or on or before the close date plus the planning horizon (default 36 months), a value from 0 to 1. If no contract dates are supplied, `a = 1` and the output states that contract lock-in was not assessed.

**Net saving:**

```
N1[k] = Σ_g G1[k,g] × π1[k,g]
```

`π1[k,g]` depends on the group's change type. The defaults below can be overridden per category:

| Situation | Low | Base | High |
|---|---|---|---|
| `same_vendor`: the same parent vendor supplies both companies at different prices | 0.50 | 0.70 | 0.85 |
| `switch`: different vendors (capturing the gap needs a switch or a competitive threat) | 0.20 | 0.40 | 0.60 |

*Worked example.* The acquirer buys 10,000 units at $4.20 and the target buys 4,000 units at $3.60 from the same parent vendor. The target holds 4,000 ÷ 14,000 = 28.6% of volume, so it qualifies as benchmark: `p* = 3.60`. Gross gap = (4.20 − 3.60) × 10,000 = **$6,000**. Net: low $3,000, base $4,200, high $5,100.

### 5.3 Lever 2 — volume consolidation

A category qualifies only if **both companies have spend in it** and it has at least two parent vendors. For each qualifying L2 category *c*:

1. **Preferred vendor.** One per category in this release. Default: the parent vendor with the largest combined spend; the user can choose another. (Choosing two is P2.)
2. **How much moves.** Let `C` = category spend, `P` = the preferred vendor's current spend, and `M` = the other vendors' spend, excluding lines that belong to a lever-1 `switch` opportunity. The moved fraction is `f = clamp((cap × C − P) ÷ M, 0, 1)`, applied pro rata to every non-preferred vendor's eligible spend. The cap is from 5.5. If the preferred vendor is already at or above the cap, `f = 0` and nothing moves.
3. **Base.** If `f = 0`, `B2[c] = 0`. Otherwise `B2[c] = P_eligible + f × M − L1`, where `P_eligible` is the preferred vendor's spend excluding lines in lever-1 `switch` opportunities, and `L1` is the lever-1 net saving, in the same case, on `P_eligible` and on the moved fraction of `M`.
   - Spend whose lever-1 saving already assumes a vendor switch is excluded, so the same change is not paid for twice.
   - Lever-1 savings travel with the spend when it moves.
   - The low, base and high lever-1 savings are each deducted in their own case.
4. **Saving.** `N2[c] = B2[c] × d[c] × π2[c]`

`d[c]` is the expected price improvement from the larger volume. It is a per-category assumption whose default comes from the category's `category_type` (3.4):

| Category type | `d` default |
|---|---|
| `commodity`: index-priced commodities and raw materials | 0% |
| `engineered`: engineered or specified direct materials | 2% |
| `mro`: maintenance supplies, packaging, consumables | 4% |
| `indirect`: indirect goods and services | 3% |

`π2` defaults: low 0.40, base 0.60, high 0.80.

*Worked example.* Post-move spend with the preferred vendor, after excluding items with a switch-based lever-1 saving, is $2,000,000, of which lever 1 has already taken $40,000. `B2 = $1,960,000`. With `d = 3%` and `π2 = 0.60`: 1,960,000 × 0.03 × 0.60 = **$35,280**.

### 5.4 Lever 3 — payment terms (cash, one-time)

Here a group *g* is (company, parent vendor); only tier A and B vendor links count. For each parent vendor supplying both companies on terms that differ by at least one day:

- `T[g]` = current days for group *g*, spend-weighted. Observed days-to-pay (`payment_date − doc_date`) are used only when both companies have `payment_date` on at least 80% of their spend with that vendor; otherwise stated terms are used for both, and labelled as such. If either company has neither, the vendor is excluded and listed.
- `T*` = `min(max(T[acquirer], T[target]), maximum)`, where the maximum is user-set (default 90 days). Some jurisdictions restrict payment terms by law; the maximum is the user's responsibility.
- `S[g]` = the group's annual spend, minus spend moved away under lever 2, minus the group's lever-1 savings and its pro-rata share (by spend) of each category's lever-2 saving, all in the same case. Spend moved *in* under lever 2 is excluded: it is treated as paid on the preferred vendor's existing terms and creates no lever-3 opportunity of its own.

```
ΔCash = Σ_g max(0, T* − T[g]) ÷ 365 × S[g] × π3
```

`π3` defaults: low 0.30, base 0.50, high 0.70.

A memo line shows the annual financing value, `ΔCash × cost of capital` (default 8%), for the base case with the low–high range. It is a financing benefit and is **excluded from EBITDA savings**. The screen also states the tension plainly: suppliers may seek to recover longer terms through price, which works against lever 1.

*Worked example.* $1,200,000 of annual spend moves from 30 to 60 days: (60 − 30) ÷ 365 × 1,200,000 = **$98,630** before capture probability, $49,315 at the base 0.50.

### 5.5 Risk guardrails

**Concentration cap.** Each category has a criticality setting and a cap on the share any one parent vendor may hold after consolidation.

| Criticality | Default cap |
|---|---|
| Critical (production stops without it) | 60% |
| Standard | 75% |
| Non-critical | 90% |

Caps are user-set per category; the defaults are starting points with no claim to universality. Where a cap limits consolidation, the saving given up is reported as **"savings forgone to protect supply resilience"**, so the trade-off is visible in dollars. Savings forgone = lever-2 base saving with the cap set to 100%, minus lever-2 base saving at the current cap.

**Concentration index.** The Herfindahl-Hirschman index, `HHI = Σ_i (100 × s_i)²` over parent-vendor shares `s_i` of category spend, is shown before and after consolidation. Shares are fractions, so the index runs from 0 to 10,000; "after" uses post-move spend before savings.

**Sole-source flag.** Any canonical item bought by both companies (tier A or B) from one parent vendor only, and any L2 category that would have one parent vendor after consolidation, is flagged.

### 5.6 Phasing, one-time costs and net value

**Contract-aware phasing (when contract end dates exist).**

- *Available month* of an opportunity = the month after the latest in-horizon contract end among its lines, counted from the close month (0 if it has no contracted lines).
- *Start month* = available month + lead time: 3 months for lever-1 `same_vendor` and for lever 3; 6 months for lever-1 `switch` and for lever 2.
- Realised saving in a quarter = run-rate × (months active in the quarter ÷ 12). Yearly figures are the sum of quarters.
- Lever-3 cash is shown once, in the quarter of its start month, on its own row.
- Opportunities whose start month is beyond month 36 count towards run-rate but contribute nothing to the three-year figure, and are listed.

**Global ramp (fallback, used when no contract dates are supplied).** Year 1: 40%, year 2: 85%, year 3: 100% of run-rate. Each quarter is one quarter of its year's figure.

**One-time costs.** One *switch event* is counted per (company, L2 category, destination parent vendor) that receives spend from a lever-1 `switch` opportunity or a lever-2 move. Cost per event = a fixed $25,000 (qualification and onboarding) + 1% of the annual spend moved, multiplied by the opportunity's capture probability in each case, and incurred in the start quarter. Same-vendor renegotiations carry no switching cost.

**Net three-year value** = Σ realised savings over years 1–3 − one-time costs, computed for the low, base and high cases. One-time costs are shown on their own line and never inside the run-rate waterfall.

*Worked example.* Run-rate $10.0M on the global ramp gives $4.0M + $8.5M + $10.0M = $22.5M. With $1.5M of one-time costs the three-year net is **$21.0M**.

### 5.7 Prioritisation

Each opportunity gets a **complexity score** from 1 to 5, the weighted average of:

| Factor | Weight | 1 (easy) → 5 (hard) |
|---|---|---|
| Contract lock-in | 30% | Expired or none → more than 24 months remaining |
| Change required | 25% | Same vendor, new price → new vendor needing qualification |
| Category criticality | 20% | Non-critical → critical |
| Sites affected | 10% | One → many |
| Match confidence | 15% | Tier A with MPN → tier B on text and attributes |

Each factor is scored on the integers 1–5:

| Factor | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Contract lock-in (available month) | 0, or no contract data | 1–6 | 7–12 | 13–24 | over 24 |
| Change required | Same vendor, new price | Terms change | Consolidation to a vendor the company already uses | Re-tender | New vendor |
| Category criticality | Non-critical | — | Standard | — | Critical |
| Sites affected | 1 | 2 | 3–4 | 5–9 | 10 or more |
| Match confidence | Tier A by MPN, tax ID or exact name | Tier A by human approval | — | — | Tier B |

For lever-2 and lever-3 opportunities, match confidence uses the vendor-link tier.

Waves follow from what the data says, not from a fixed template. The first rule that matches applies:

1. **Wave 3 (beyond 12 months):** available month greater than 12.
2. **Wave 1 (start within 100 days of close):** lever-1 `same_vendor` or lever 3, available month ≤ 3, and complexity ≤ 2.5.
3. **Wave 2 (months 4–12):** everything else, which is mainly vendor consolidation and re-tenders.

### 5.8 Reconciliation to a top-down reference band

The base-case run-rate saving is shown two ways, each next to a user-set reference band:

- as a percentage of **total** combined in-scope spend (default band 1–3%);
- as a percentage of **addressable** spend, meaning spend in categories where the two companies overlap (default band 3–10%).

Both default bands are this document's assumptions, not benchmarks. Published rules of thumb vary widely with industry, with how much the two companies' purchasing overlaps, and with whether they are quoted on total or addressable spend, so the bands are a sanity check and not a target. The bands are inclusive. If the bottom-up figure falls outside a band, the screen says so and lists the three opportunities with the largest base saving.

### 5.9 Invariants (enforced by tests)

All money is 64-bit floating point. In this document "exactly" means the absolute difference is at most $0.01 at total level, and "to the dollar" means equal after rounding to whole dollars.

- No saving is negative; no lever exceeds its own base.
- Low ≤ base ≤ high for every lever-1 opportunity, for the lever-1 total, and for the total recurring saving (lever 1 + lever 2), given valid inputs (5.1). Lever 2 alone and lever 3 alone are computed on a base that shrinks as earlier levers save more, so they are labelled by case and are **not** required to be ordered.
- The sum of spend in the unified spend cube equals the baseline, and baseline − Σ lever-1 opportunities − Σ lever-2 opportunities = net run-rate spend, in each case.
- Each dollar of spend contributes to at most one lever-1 opportunity.
- Recurring and one-time amounts never appear in the same sum.
- The bridge ties out exactly: naive figure − the sum of the seven bridge steps = lever-1 base net saving. Equivalently, with every capture probability at 1 and every bridge filter off (including using the absolute minimum price in place of `p*[k]`), lever 1 equals the naive figure.

---

## 6. Experience design

This section is the product's first impression and carries equal weight with the analytics.

### 6.1 Experience principles

1. **Answer first.** The first screen shows a result, never a form.
2. **One question per screen.** Each screen has a headline written as a finding, one main chart, and supporting detail below.
3. **Earn the next click.** Each screen ends with the question it raises and a link to where it is answered.
4. **Every number is a door.** Any dollar figure can be clicked to see what it is made of, down to source rows.
5. **Calm, not flashy.** Generous spacing, a warm neutral background, one accent colour, no gauges, no gradients, no animation beyond short fades.
6. **Honest by design.** Ranges over point estimates, assumptions visible, limits stated.
7. **Never lose the user's work.** Review decisions and assumption changes persist for the session and can be exported.

### 6.2 Signature moments

The five things a professional should remember after two minutes:

| # | Moment | Where |
|---|---|---|
| 1 | **The bridge.** The naive figure shrinks step by step to a defensible range, and each step is clickable | Overview, Synergies |
| 2 | **The scorecard.** Matching accuracy measured against hidden truth, next to what the naive method would have got wrong | Matching |
| 3 | **The tie-out.** Click a bar, see the opportunities, click one, see both companies' source rows side by side | Everywhere |
| 4 | **The price of resilience.** Move the concentration cap and watch the saving forgone | Risk & roadmap |
| 5 | **The unit trap.** "This 12.0× price gap is a box of 12, not a saving" | Matching, bridge step 1 |

### 6.3 Information architecture

Top navigation, left to right, following the analytical story:

| Screen | Headline question | Ends with |
|---|---|---|
| **Overview** | What is the answer, and how sure are we? | "Why is it so much smaller than the naive figure?" → Synergies |
| **Data** | What did we receive and what state is it in? | "How were two vendor lists made one?" → Matching |
| **Matching** (includes the review queue and the scorecard) | Which vendors and items are the same, and how do we know? | "What is that worth?" → Synergies |
| **Synergies** | Where does the saving come from, and what did we refuse to count? | "What could go wrong?" → Risk & roadmap |
| **Risk & roadmap** | What do we give up for resilience, and what happens when? | "What are we assuming?" → Assumptions |
| **Assumptions** | Which inputs drive the answer? | "Take it with you" → Export |
| **Export** | Workbook and deck | — |
| **Method & limits** | How it works and what it cannot see | — |

A header rendered above every page shows the scenario name, the view mode (clean team or integration office, switched with a segmented control), and the headline range, so the user always sees the effect of a change. It need not stay fixed while scrolling. The Export screen's footer links to Method & limits.

### 6.4 Overview screen

- **Headline** in the serif display face, generated from the data: *"$8–12M of run-rate savings is defensible; the naive figure of $31M is not."* (Figures illustrative.)
- **Three figures** in a row, each with a one-line explanation and a range: run-rate P&L saving, one-time cash release, one-time cost. Recurring and one-time are visually separated by a divider and a label.
- **Bridge chart** (naive → defensible), the main visual.
- **Confidence strip**: share of the base case resting on tier A versus tier B matches, and the dollar value pending review.
- **Three "worth a look" cards**, always these: the largest lever-1 opportunity by base saving; the unit trap with the largest naive gap removed; and the L2 category with the largest savings forgone.
- Next-question link.

### 6.5 Review queue

Designed for speed and for judgement.

- One candidate at a time in focus, with the queue visible on the left, sorted by dollars at stake.
- Two record cards side by side: acquirer left, target right, each with a 4 px top border in its entity colour and the company name in `ink`. Differing tokens are highlighted; identifiers are set in the monospace face so that a one-character difference is visible.
- An **evidence panel**: what supports the match, what argues against it, and the stage that proposed it.
- A **stake line**: "Approving adds $184k to the gross gap" (illustrative).
- Three large buttons: Approve (A), Reject (R), Defer (D), with those keyboard shortcuts. If button shortcuts are unavailable in the installed framework version, the buttons ship without them; no custom JavaScript.
- A progress bar with the dollar value cleared, and an "approve all above score X" bulk action that applies to one queue type at a time, uses that type's own score scale, and shows its dollar effect before it is confirmed.
- Undo for the last decision (Z).

### 6.6 Traceability

Every headline figure has a "Show working" control next to it, and every chart bar and table row can be selected, to open a panel listing its components. The chain is always:

`total → lever → category → opportunity → canonical item or vendor → source rows`

Source rows are shown exactly as received, with file name and row number, next to their normalised form. A "copy as table" block of tab-separated text, with a copy button, supports pasting into a working paper.

### 6.7 Assumptions

- All adjustable inputs live on one screen, grouped by lever, with defaults, current values and a "reset" per group. The concentration cap is also adjustable in place on the Risk & roadmap screen; both controls edit the same value, and that slider recalculates on release.
- Changed values are marked, and a summary line reads "4 assumptions changed from default".
- A tornado chart ranks assumptions by their effect on the base total recurring saving, top 12 shown. Each assumption with a low/base/high triple is moved to its low and high values; any other is moved ±25% (caps ±10 percentage points, horizon ±12 months).
- A scenario is a named copy of the assumptions. "Central (defaults)" always exists; "Conservative" and "Stretch" are shipped presets that set every base probability to its low or high value. Scenarios can be saved for the session and compared in a table of totals.
- Recalculation after an assumption change takes under half a second on the demo data, because matching results are cached and only the arithmetic re-runs.

### 6.8 Charts

| Chart | Purpose | Notes |
|---|---|---|
| Bridge (naive → defensible) | Signature chart | Vertical bars running left to right along the x-axis; each bar selectable |
| Synergy waterfall | Baseline → lever 1 → lever 2 → net run-rate spend | Recurring only; low–high range marked on the total |
| Spend Pareto | Vendor fragmentation before and after matching | Bars for spend, line for cumulative share, 80% marker |
| Price dispersion | Per-item price by buying group | Dot plot; benchmark price marked |
| Prioritisation matrix | Saving against complexity, coloured by wave | Bubble size = spend; labels for the top ten only |
| Phasing | Realised savings by quarter, by wave | Stacked area; one-time costs as separate bars. (The deck shows years, for legibility) |
| Concentration | Vendor share by category, before and after, with cap line | Horizontal stacked bars |
| Threshold sensitivity | Base case against the vendor and item match thresholds | Two lines with the current settings marked (4.7) |
| Tornado | Effect of each assumption | Sorted by magnitude |

Chart rules: direct labels in preference to legends; axis titles in plain words; no dual axes except the Pareto; hover text gives the exact figure and the count of items behind it; every chart has a one-sentence text summary as a caption directly beneath it and a "view as table" toggle that swaps the chart for its data.

### 6.9 View modes

- **Clean-team view:** full detail, including vendor names and unit prices.
- **Integration-office view:** vendor names replaced by codes (`Vendor 017`, numbered by descending combined spend and fixed for the run), unit prices hidden, results aggregated to category level, any category with fewer than three parent vendors merged into "Other". The review queue, source rows, price dispersion chart and matching detail tables are hidden; the scorecard stays. A banner states which view is active, and exports carry the same mode.

This is a presentation mode to show understanding of clean-team practice. It is not a security control, and the interface says so.

### 6.10 "What this analysis cannot see"

A fixed panel on the Method & limits screen, repeated in the deck and workbook:

- Rebates, credits and off-invoice discounts
- Specification, quality and lead-time differences between apparently identical items
- Freight and delivery terms, unless incoterms are supplied
- Contract clauses such as minimum volumes, exclusivity and change of control
- Index-linked prices caught at different dates
- Supplier capacity and willingness to serve the combined volume
- Services and other spend with neither an item code nor an MPN, beyond vendor and category totals
- Corporate parent links not supplied in the parent table

### 6.11 Visual design

**Colour.** A warm paper background with dark ink text and a single teal accent, chosen to feel like a well-made report and to stay comfortable over a long session. Contrast ratios below are computed against the paper background using the WCAG 2.x formula; text needs at least 4.5:1 and graphical marks at least 3:1.

| Token | Hex | Use | Contrast on paper |
|---|---|---|---|
| `paper` | `#FAF8F4` | Page background | — |
| `surface` | `#FFFFFF` | Cards, tables | — |
| `ink` | `#16202E` | Body text, headlines | 15.5 |
| `muted` | `#5B6676` | Secondary text, axis labels | 5.5 |
| `border` | `#E3DED4` | Dividers, card outlines (decorative) | 1.3 |
| `control` | `#8A8478` | Input and button outlines | 3.5 |
| `teal` | `#0F6E63` | Primary accent, links, confirmed and tied-out states | 5.8 |
| `teal-tint` | `#E3F0EE` | Selected rows, confirmed backgrounds | — |
| `amber` | `#A64B05` | Needs review | 5.4 |
| `amber-tint` | `#FBEBD3` | Review backgrounds | — |
| `red` | `#B3372F` | Risk, veto, cost | 5.6 |
| `red-tint` | `#F8E1DE` | Risk backgrounds | — |
| `acquirer` | `#27457A` | Acquirer data in charts and cards | 8.9 |
| `target` | `#B8642A` | Target data in charts and cards (marks only, not text) | 4.0 |

Ink on each tint exceeds 13:1. White text on `teal` is 6.1:1 and on `acquirer` 9.5:1. Text on a tint is always `ink`; the status colours are used on tints only for icons and borders.

Rules:

- The acquirer is always navy and the target always copper, on every screen and export. This blue and orange pair remains distinguishable under the common forms of colour-blindness.
- The status colours (teal, amber, red) are close to each other in lightness and are **not** reliably distinguishable by colour alone, least of all teal against red for red-green colour-blindness. Colour therefore never carries meaning alone: every tier, wave and state also has a text label and an icon or pattern.
- Copper is close to amber, so entity colours and status colours are never used as competing series in the same chart.
- Confidence tiers use one hue at three strengths (solid teal, hatched teal, outlined), not three hues.
- Waves use `ink`, `muted` and `control` (dark to light), each with its wave number as a direct label.
- Labels are never placed inside copper marks.
- Red is reserved for risk and cost. Savings are teal, never green-for-good.
- Light theme only in the first release; a dark theme is P2.

**Typography.** The IBM Plex family (open licence), loaded as web fonts.

| Role | Face | Size / weight |
|---|---|---|
| Finding headlines | IBM Plex Serif | 28–32 px, semibold |
| Section headings | IBM Plex Sans | 18–20 px, semibold |
| Body and controls | IBM Plex Sans | 15–16 px, regular; line height 1.5 |
| Captions, axis labels | IBM Plex Sans | 12–13 px |
| Identifiers (part numbers, item codes, tax IDs) | IBM Plex Mono | 13–14 px |
| Figures in tables | IBM Plex Sans with tabular numerals | right-aligned (applies to HTML-rendered tables and figure cards; interactive data grids use the theme font as it is) |

The serif headline gives the reading feel of a consulting report. The monospace face has a dotted zero and clearly different `1`, `l` and `I`, which matters because two part numbers can differ by one character.

Exports cannot embed fonts, so the deck and workbook use faces present on Windows and macOS: Georgia for slide titles and Arial for everything else.

**Layout.** Maximum content width 1,200 px; an 8 px spacing scale; cards with a 1 px border, 8 px radius and no drop shadows; one main chart per screen at full width, supporting charts in a two-column grid that stacks below 900 px.

**Numbers.** Headline figures as a range with one shared unit, each end rounded to the nearest $1M when the upper end is $10M or more and to the nearest $0.1M otherwise (`$8–12M`); tables to the nearest thousand; unit prices to four decimals; percentages to one decimal; negative values with a minus sign, never brackets on screen (brackets in the workbook, following finance convention).

### 6.12 Words

- Headlines state findings, not topics: "Three vendors hold 61% of fastener spend", not "Vendor concentration".
- Plain verbs on buttons: Approve, Reject, Export workbook.
- Every assumption has a one-line explanation in ordinary language and says which way it moves the answer.
- Errors say what happened, what was affected in rows and dollars, and what to do.
- "Illustrative — synthetic data" appears in the header in demo mode, in the footer of every exported slide and in cell A1 of every workbook tab.

### 6.13 States

| State | Behaviour |
|---|---|
| First load (demo) | Precomputed results render immediately; no spinner |
| Matching in progress | Staged progress with real counts: "2,480 vendor records → 1,930 after normalisation → 1,610 after matching" (illustrative) |
| Empty review queue | "Nothing left to review" with the value cleared and a link to Synergies |
| No overlap found | Explains that the two files share no matched vendors or items, shows the nearest misses (the ten highest-scoring vendor pairs and ten item pairs below the review thresholds), and suggests checking the category map |
| Validation failure | Blocking errors first, each with a fix; warnings collapsed below |
| Missing optional data | The affected feature shows what it would need: "Add contract end dates to enable contract-aware phasing" |

### 6.14 Accessibility and performance

- WCAG 2.1 AA contrast for text and controls; visible focus outlines; logical tab order.
- Charts have text summaries and table alternatives.
- Demo first render under 3 seconds once the app is awake; assumption changes under 0.5 seconds; full matching on the demo data under 30 seconds. The last two are tested on the engine (`recompute(results, assumptions)` and the full pipeline on seed 4), asserting twice those bounds to avoid flaky tests. First render is not machine-tested.
- Usable from 1,280 px wide down to a tablet; on a phone the landing page and Overview are readable, and deeper screens show a "best on a larger screen" note (an element revealed by a CSS media query at widths up to 700 px).

---

## 7. Exports

One calculation produces every number. The screen, the workbook and the deck read from the same results object, and a test confirms they agree to the dollar.

### 7.1 Workbook (P0)

The workbook is the primary deliverable, because it is what a practitioner will actually audit.

Written with **XlsxWriter**. It does not calculate formulas itself, but it lets the engine write its own computed result next to each formula (the `value` argument of `write_formula`; without it the stored result is 0). The engine passes a result for every formula, so figures display correctly in file previews and in viewers that do not recalculate. A build test opens the file in headless LibreOffice with recalculation on load forced on (its default for this format is not to recalculate; the setting is `OOXMLRecalcMode` under `/org.openoffice.Office.Calc/Formula/Load`, to be confirmed at M0), converts it, reads both files, and asserts that each recalculated value is within 1e-6 × max(1, |stored value|) of the stored one. The test is skipped with a visible reason, never failed, when LibreOffice is not installed; the builder does not try to install it.

| Tab | Contents |
|---|---|
| `README` | Scope, date, view mode, data caveats, how to read the file, "what this analysis cannot see" |
| `Summary` | Headline range, levers, cash, one-time cost, phasing. Every figure is a formula over the detail tabs |
| `Assumptions` | Every adjustable input in a named cell. Changing an arithmetic assumption (capture probabilities, discounts, ramp, cost of capital, switching costs) recalculates the workbook. Settings that change which rows qualify (match thresholds, benchmark volume test, concentration caps, close date, planning horizon) are recorded here as fixed values and need a re-run in the tool |
| `Bridge` | Naive-to-defensible steps as formulas over `Bridge_Detail` |
| `Bridge_Detail` | One row per item, buying group and bridge step: naive gap and amount removed |
| `Category_Settings` | One row per L2 category with its effective cap, discount and probabilities, as input cells |
| `Opportunities` | One row per opportunity: lever, category, item or vendor, gap, probabilities, low / base / high, wave, complexity |
| `Spend_Cube` | Unified lines: company, site, parent vendor, legal entity, category L1/L2, canonical item, base-unit quantity, price, spend |
| `Price_Variance` | Per matched item: each buying group's price, benchmark price, gap; internal variance listed separately |
| `Payment_Terms` | Per shared vendor: current and target days, spend, cash release |
| `Risk` | Per category: vendor shares and concentration index before and after, cap, savings forgone, sole-source flags |
| `Phasing` | Realised savings by quarter and wave, one-time costs, three-year net value |
| `Vendor_Map` | Every source vendor → legal entity → parent, with stage, score and tier |
| `Item_Map` | Every source item → canonical item, with stage, attributes, score and tier |
| `Review_Log` | Human decisions with timestamps and notes |
| `Scorecard` | Accuracy metrics and the baseline comparison (demo data only) |
| `Data_Quality` | Validation findings with row counts and dollar values |

Requirements:

- Summary and Bridge figures are live `SUMIFS` / `SUMPRODUCT` formulas referencing the detail tabs and the named assumption cells.
- Detail tabs are Excel tables with frozen headers and filters.
- Input cells are visually distinct from formula cells (blue font for inputs, black for formulas, following financial-modelling convention).
- A check cell on `Summary` confirms that totals tie to the detail tabs: `=IF(ABS(diff)<0.5,"OK",diff)`.
- How the formulas are built:
  - `Bridge` steps 1–6 are `SUMIFS` over `Bridge_Detail` by step number; step 7 = (gross after step 6) − Σ lever-1 base saving on `Opportunities`.
  - `Opportunities` holds the gross gap as a value and low / base / high as formulas (gap × a lookup into `Category_Settings`). Lever-2 rows hold post-move spend as a value and deduct lever-1 savings with `SUMIFS`. Lever-3 rows deduct with `SUMIFS` by parent vendor.
  - `Phasing` multiplies run-rate by stored months-active values, or by the named ramp cells when the global ramp is in use.
  - Formulas use A1 ranges bounded to the data rows, and defined names; not structured table references.
  - Every formula is written with the engine's value as its stored result, including formula cells inside tables.
- **Integration-office (masked) workbook.**
  - Omitted tabs: `Price_Variance`, `Vendor_Map`, `Item_Map`, `Review_Log`, `Bridge_Detail`, `Payment_Terms`.
  - `Spend_Cube` is aggregated to company × L2 category, spend only.
  - `Opportunities` is aggregated to lever × L2 category.
  - Bridge step amounts are written per L2 category in a `Bridge_By_Category` tab, and the `Bridge` and `Summary` formulas sum the aggregated tabs.
  - `Risk` shows vendor codes. Codes appear only there, in the concentration chart and in the Pareto.
  - L2 categories with fewer than three parent vendors are summed into "Other" in every masked table and chart.

### 7.2 Deck (P1)

Eight slides, 16:9, generated with **python-pptx**.

| # | Slide | Content |
|---|---|---|
| 1 | Title and scope | Companies, period, in-scope spend, view mode, synthetic-data label |
| 2 | Executive summary | Finding headline with the range; three supporting points; cash and one-time cost stated separately |
| 3 | Baseline and fragmentation | Combined spend by category and company; Pareto; vendor count before and after matching |
| 4 | From naive to defensible | The bridge |
| 5 | Savings by lever | Waterfall of recurring savings; cash release as a separate callout |
| 6 | Priorities and timing | Prioritisation matrix, top five negotiation targets, realised savings by year and wave as stacked columns |
| 7 | Risks, assumptions and limits | Concentration findings, savings forgone for resilience, key assumptions, what the analysis cannot see |
| 8 | Data and matching audit | Volumes processed, match tiers, review decisions, accuracy scorecard (the scorecard is omitted for uploaded data) |

Requirements:

- **Finding headlines** are generated from the data with templated sentences and numeric guards, at most 120 characters. If the naive figure is not above the top of the defensible range, the template is "The naive figure of {N} holds up: {L}–{H} is defensible". If a value is zero or missing, its sentence is omitted.
- **Construction.** Set the slide size to 13.333 × 7.5 inches (the library's default template is 4:3). Use only the blank layout and add text boxes, so that no empty placeholder remains. Page numbers are written as literal text. Tier hatching uses pattern fills. Slide 6 has the matrix on the left and stacked columns by year on the right; the top five targets are a five-row table if it fits at 12 pt or larger, and are always in the speaker notes.
- **Charts are native PowerPoint charts wherever the library supports the type**, so a consultant can restyle them and open the underlying data. The waterfall and bridge are stacked bars with an invisible base series, with the low–high range written as a label because the library has no interface for error bars. Any chart it cannot build natively, which means any chart combining two types such as the Pareto's bars and line, is rendered with matplotlib as a high-resolution image.
- No browser-based image export is used, which avoids a dependency on a headless Chrome on the host.
- Layout: title top-left, one message per slide, source line and page number in the footer, consistent margins, the palette from 6.11, no clip art.
- Every figure on a slide carries a footnote reference to its workbook tab.

### 7.3 Static images

All static images (the landing page's bridge image, README images, the deck's Pareto) are rendered by matplotlib chart functions in `tieout/export/charts.py`, never exported from the interactive charts.

### 7.4 Other exports

- Review decisions as CSV (re-importable). **P1**
- Any chart as PNG and any table as CSV from its own menu. **P2**

---

## 8. Demo dataset

### 8.1 The fictional merger

Two fictional mid-market industrial manufacturers with a combined revenue of about $1.2B and combined in-scope external spend of about $520M: an acquirer with about $340M and a target with about $180M. Company, vendor and manufacturer names are all invented, so that no real supplier appears to have real prices. They are produced by a syllable-based name generator and screened against `synthetic/denylist.txt`, a builder-authored list of at least 200 well-known industrial and distribution company names. A final human check is listed in 11.1.

Scale: roughly 60,000 purchase lines dated 2025-01-01 to 2025-12-31, about 2,500 vendor records and about 9,000 item records across both companies. Acquirer: about 38,000 lines, 1,500 vendors, 5,500 items, 8 sites. Target: about 22,000 lines, 1,000 vendors, 3,500 items, 5 sites. The demo's report date is fixed at 2026-01-15.

### 8.2 Generation method

1. **Build the true world first**: parent vendors and their legal entities, true items with full attributes and a true base-unit cost, contracts with end dates, category criticality.
2. **Render each company's view** through its own "ERP style": naming conventions, field-length truncation, abbreviation habits, native taxonomy, unit preferences.
3. **Apply noise models**, each documented with its rate:

| Noise | Example |
|---|---|
| Vendor aliases and legal-form variants | "Corvane Fastening Inc" / "CORVANE FASTNG" |
| Typos | Transpositions, dropped and doubled letters |
| Truncation | Names cut at a fixed field length |
| Missing tax IDs | About 30% |
| Parent links with no name similarity | A distributor and its online subsidiary |
| Pack-unit differences | Box of 12 against each |
| Different item codes and description styles | Same MPN, unrelated codes |
| Currency | USD with some CAD and EUR |

4. **Plant distractors** that a careless matcher will get wrong:
   - near-identical items that differ in one attribute;
   - unrelated vendors with similar names;
   - price gaps explained by freight terms;
   - unit traps;
   - spot buys at unrepresentative prices.
5. **Plant true savings** with known causes and values, and write the truth files.

**Default rates** (all documented in the generator and adjustable there):

- Vendors: 25% of parent vendors are shared between the companies; alias or legal-form variant on 40% of shared vendors; typo on 8% of names; the target company's names truncated at 30 characters; tax ID missing on 30% of records; country present on all records; parent links with no name similarity for 5% of parents, all listed in a generated `data/demo/vendor_parents.csv` (an input, not truth).
- Items: truly shared items are about 35% of each company's item records; MPN present on 60% of shared items; a pack-unit difference on 12% of shared items, of which half state the pack size in the description, a quarter in `pack_qty`, and a quarter nowhere.
- Commercial: contracts on 40% of item spend, with end dates spread from 6 months before to 48 months after the close date; payment terms on all lines and payment dates on 90%; incoterms on 70%; currency 85% USD, 10% CAD, 5% EUR.
- Distractors: 300 near-identical item pairs differing in one attribute; 60 unrelated vendor pairs with similar names; 40 freight-term price gaps; at least 60 unit traps; spot buys on 3% of items.
- The generator's abbreviation habits come from its own list in `synthetic/`, which overlaps the engine's abbreviation dictionary by about 80%, so the matcher is not handed the answer key.
- The demo also ships a generated `category_map.csv`.

### 8.3 Design targets

- The naive lever-1 figure lands at roughly 5–7% of in-scope spend.
- The defensible base case (lever 1 + lever 2) lands at roughly 1.5–2.5% of in-scope spend, and lever 1 alone at roughly 1.0–2.0%.
- About 35% of spend has neither an item code nor an MPN.
- At least one category where the concentration cap visibly limits consolidation.
- At least one large, memorable unit trap.

These are targets for the generator, to be confirmed by running it; they are not results. A test asserts the wider bounds of 4–8% (naive) and 1–3% (defensible base) on seed 4. If it fails, the builder adjusts the generator's price-gap scale and unit-trap count, never the engine.

---

## 9. Architecture

### 9.1 Stack

| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3.11+ | |
| Data | pandas, NumPy | |
| Schema validation | pandera | Declarative checks with row-level error reports (`import pandera.pandas as pa`; validate with `lazy=True` and read the failure cases). The 1% severity rule and dollar-value figures are custom code on top |
| Fuzzy matching | RapidFuzz | Fast, permissive licence |
| Text similarity | scikit-learn TF-IDF | No model download, small memory footprint |
| Interface | Streamlit | Fastest route to a working, themed analytical app for one developer |
| Charts | Plotly | Point-selection events for drill-down |
| Workbook | XlsxWriter | Stores formula results; native tables, names, formats |
| Deck | python-pptx, matplotlib | Native charts where possible |
| Tests | pytest, Hypothesis | Property tests for the invariants in 5.9 |
| Lint and format | Ruff | |
| Storage of results | Parquet via pyarrow | No pickle |
| Reading exports in tests | openpyxl | Read-only use |

Not used, deliberately: sentence-embedding models (large, and embeddings blur exactly the one-digit differences that matter here); browser-based chart export.

**Packaging.** `pyproject.toml` with lower bounds: streamlit ≥ 1.52, plotly ≥ 5.22, rapidfuzz ≥ 3.6, scikit-learn ≥ 1.4, pandera ≥ 0.24, xlsxwriter ≥ 3.2, python-pptx ≥ 1.0, pandas ≥ 2.2, plus pyarrow, openpyxl, matplotlib, hypothesis, pytest and ruff. A generated `requirements.txt` serves the host. Licence: MIT. The IBM Plex font files are committed under `app/static/fonts/` with their licence text and loaded through the theme's font-face configuration; no external font service.

### 9.2 Structure

```
tieout/
  __main__.py    command-line entry point
  ingest/        loading, column mapping, validation, FX, annualisation
  normalise/     vendor names, item descriptions, units, taxonomy
  match/         vendor stages, item stages, clustering, review state
  synergy/       levers, bridge, risk, phasing, prioritisation
  export/        workbook, deck, charts (matplotlib)
  reference/     taxonomy.csv, abbreviations.csv, generic_tokens.txt,
                 descriptor_tokens.txt, column_synonyms.json,
                 fx_rates.csv, thresholds.toml
  results.py     the single results object every surface reads
synthetic/       generator, name denylist, truth writer (never imported by tieout/)
evaluation/      scorecard, tuning, baseline matcher, sensitivity
app/             main.py, pages, components, theme, static/fonts
site/            static landing page, assets, config.js
tests/
data/demo/       generated demo files, precomputed results, scorecard.json
data/truth/      truth files per seed (read only by evaluation/)
HUMAN_TODO.md    tasks for the human owner (11.1)
BUILD_NOTES.md   decisions and shortfalls recorded during the build
```

The engine (`tieout/`) has no dependency on the interface and can be run from the command line:

```
python -m tieout run ACQ TGT --out DIR [--mapping map.json] [--category-map F]
    [--vendor-parents F] [--fx F] [--category-settings F] [--assumptions F.toml]
    [--review-decisions F.csv] [--period-end YYYY-MM] [--as-of YYYY-MM-DD]
    [--aggregated] [--view clean|masked] [--no-exports]
```

- Without `--mapping`, the file headers must equal the schema names.
- Without `--category-map`, the top suggestion with a score ≥ 0.3 is accepted and the rest left unmapped.
- Tier C candidates stay pending.
- It writes `DIR/results/`, `DIR/tieout_workbook.xlsx` and `DIR/tieout_deck.pptx`.
- Exit code 0 on success, 2 on a blocking validation error (the report is printed).

Other entry points: `python -m synthetic --seed N --out DIR`; `python -m evaluation tune|score|baseline|sensitivity`; and `make demo`, which generates seed 4, runs it, scores it, and copies the results and sample exports to `data/demo/` and `site/assets/`. Local run: `pip install -e .` then `streamlit run app/main.py`.

**The results object.** `Results` is a frozen dataclass holding:

- `meta`: scenario, view mode, seed, period, reporting currency, report date, flags for switched-off features
- `assumptions`: a dictionary
- data frames `lines`, `vendor_map`, `item_map`, `review_queue`, `review_log`, `price_groups`, `bridge_detail` (one row per item × group × step, with amount)
- data frames `opportunities` (id, lever, L2, entity, change type, gap, low / base / high, wave, complexity, start month), `category_risk`, `payment_terms`, `phasing`, `data_quality`
- `totals`: by lever and case
- `trace`: parent id → child ids, down to source rows
- `scorecard`: optional

`Results.save(dir)` writes one Parquet file per data frame plus `results.json`; `Results.load(dir)` reads them. Demo results live in `data/demo/results/`. Pages take every displayed figure from view functions in `tieout/results.py`, which is what the tie-out tests compare with the workbook and the deck.

### 9.3 Interface implementation notes

- Requires Streamlit 1.52 or later, for chart selection events, custom theme fonts and button keyboard shortcuts.
- Drill-down uses Plotly selection events (the user selects a bar or point; the app re-runs with that selection).
- Matching and savings are computed separately, so assumption changes re-run only the arithmetic. Shared caches (`st.cache_data`, `st.cache_resource`) are used only for the committed demo results, because they are shared across visitors; results from uploaded data live in `st.session_state` only.
- Navigation uses `st.navigation` with the pages along the top.
- "Every number is a door": each headline figure has an adjacent "Show working" button that opens an `st.dialog` trace panel; tables use `st.dataframe(on_select="rerun", selection_mode="single-row")`; charts use `st.plotly_chart(on_select="rerun")`.
- The bridge and waterfall are built from bar traces with a transparent base series, not the waterfall trace type, so that bar selection works.
- Trace logic lives in `tieout/` and is tested there. Interface tests use `streamlit.testing.v1.AppTest` only to assert that every page renders without an exception.
- Upload limit: `server.maxUploadSize = 50`.
- Review decisions are stored in session state keyed by a stable pair identifier, never by row position.
- Grouped inputs are submitted as forms so that a half-edited set of assumptions does not trigger recalculation. The one exception is the concentration-cap slider on Risk & roadmap, which sits outside any form.
- The theme (colours and fonts in 6.11) is set in the Streamlit theme configuration, with a small stylesheet for cards and typography where the theme options do not reach.

### 9.4 Hosting

- The landing page is static and always loads instantly.
- The app runs on a free tier. Free hosts put idle apps to sleep (Streamlit Community Cloud does so after 12 hours without traffic), so a first visitor may wait while it wakes; the landing page therefore carries the video, screenshots and downloadable sample outputs, and never depends on the app being awake.
- Demo results are precomputed and committed, so a woken app shows the Overview without running matching.
- Deployment itself is done by the human owner (11.1). The builder ensures `requirements.txt` and `app/main.py` are where a host expects them. The landing page reads the demo address from `site/config.js` (`DEMO_URL = "#"`), and its button reads "Live demo coming soon" while the value is `#`. The video block is present but commented out, with the bridge image in its place.
- The repository README leads with the outputs (bridge image, scorecard, sample workbook and deck), then how to run locally in two commands.

---

## 10. Edge cases and test criteria

### 10.1 Edge cases

| Case | Expected behaviour |
|---|---|
| Box of 12 against each, pack size in description | Converted, status `parsed`; included |
| Pack unit with no pack size anywhere | Counted as spend; excluded from price comparison; listed |
| Price ratio near a pack factor without confirmed conversion | Flagged as suspected unit error; excluded; in review queue |
| Missing tax ID on one or both sides | Falls through to name stages; no penalty |
| Different tax IDs, near-identical names | Not merged automatically; offered as possible siblings |
| Same name, different countries | Not merged on tax ID; name stages apply |
| One vendor name is a subset of another ("Apex" / "Apex Logistics") | No automatic match |
| Items differing in one numeric token | Vetoed |
| Item bought by only one company | No lever-1 opportunity; still in the cube |
| Lowest price is a spot buy | Fails the volume or line-count test; next qualifying group used |
| Buying group already below the benchmark | Contributes zero, never a negative saving |
| Category with no overlapping vendors or items | Levers 1 and 3 report zero with an explanation; lever 2 still applies if both companies buy in the category; no error |
| No overlap anywhere | "No overlap found" state |
| Single vendor in a category | Sole-source flag; no consolidation saving |
| Consolidation would exceed the cap | Move limited; forgone saving reported |
| Vendor on identical terms at both companies | No lever-3 opportunity |
| Credits and returns | Netted; an item with net quantity ≤ 0 is excluded from price comparison |
| Mixed currencies | Converted with the fixed table; missing rate blocks those rows |
| Less than 12 months of data | Scaled and flagged everywhere |
| Very large upload | Rejected above 250,000 rows or 50 MB per file, with a clear message |

### 10.2 Test criteria

- **Unit tests** for every normalisation rule, unit conversion, matching stage and formula, including the worked examples in section 5, which must reproduce to the dollar.
- **Property tests** for the invariants in 5.9, run on the `synergy/` arithmetic over generated matched tables (not on the matching pipeline), with no deadline and 100 examples each.
- **Scorecard gate:** the build fails if held-out accuracy falls below the targets in 4.7.
- **Isolation test:** engine code cannot import the generator or read truth files.
- **Tie-out tests:** screen totals, workbook `Summary` and deck figures are equal; workbook formulas equal their stored values after recalculation.
- **Export tests (automated):** the workbook loads in openpyxl and the deck in python-pptx without error; every XML part parses; no cell contains `#REF!`, `#NAME?` or `#VALUE!`; every slide has a headline within the length limit; no shape text matches `Click to add` or `{{`. Opening both files in Excel and PowerPoint without a repair prompt is a human check (11.1).
- **Golden-file test:** a fixed seed and report date produce identical `totals` and `opportunities` across runs, within 1e-6, excluding decision timestamps and file metadata. All sorts are stable with explicit tie-break keys.
- **Usability check before release (human, 11.1):** at least four of five people unfamiliar with the project can state the defensible range and one reason the naive figure is wrong after two minutes on the Overview.

---

## 11. Roadmap

Scope is the main delivery risk for a single developer, so the milestones are ordered to make every stopping point presentable.

| Milestone | Delivers | Exit criteria |
|---|---|---|
| **M0. Foundations** | Repository, packaging, design tokens and theme, reference files, results object, command-line skeleton, `HUMAN_TODO.md`, `BUILD_NOTES.md` | An empty themed app renders and the test suite passes |
| **M1. Data and matching** (P0) | Generator with truth files, ingestion and validation, units, vendor and item matching, pairwise scorecard, baseline matcher | Vendor and item precision and recall targets met on seed 4 (or handled as in 4.7); isolation test passing |
| **M2. Lever 1 and the core experience** (P0) | Price harmonisation, bridge, traceability, sensitivity chart, dollar-weighted scorecard metrics, the Overview, Data, Matching (with review queue), Synergies, Export and Method & limits screens, workbook | False-savings and unit-trap targets met; bridge invariant test passing; for every figure in `totals`, `trace` resolves to source rows whose amounts re-sum to it within $0.01; workbook check cell is `OK` |
| **M3. Remaining levers and risk** (P1) | Volume consolidation, payment terms, concentration, phasing, prioritisation, the Risk & roadmap and Assumptions screens, scenarios | All 5.9 tests pass; a test shows that lowering one category's cap from 90% to 60% strictly increases savings forgone on the demo data |
| **M4. Deck, custom upload and launch materials** (P1) | Deck, guided tour, column mapping and custom upload, view modes, landing page, README | All automated export tests pass; the landing page builds; `HUMAN_TODO.md` is complete |
| **M5. Stretch** (P2) | Splink comparison, dark theme, per-chart exports, two preferred vendors per category | — |

**Until M3, P1 content is absent, not zero.** At M2 the workbook omits `Payment_Terms`, `Risk` and `Phasing`; the Overview shows "Cash release — added with lever 3" and "One-time cost — added with phasing" as muted placeholders; the third "worth a look" card is the largest internal-variance item; the bridge has no lever-2 bar and the headline uses lever 1 only; next-question links to screens not yet built are hidden.

After M2 the project is already a credible, narrow showcase: measured matching, one fully traceable lever and an auditable workbook.

### 11.1 Deferred to the human owner

These are not build requirements. The builder creates `HUMAN_TODO.md` listing each one:

1. Record the 90-second video for the landing page.
2. Deploy the app and the landing page, and set the demo address.
3. Run the two-minute usability check with five people.
4. Arrange review by two practitioners.
5. Check the name "Tie-Out" and the generated company and vendor names for trademark or real-company collisions.
6. Open the workbook and the deck in Excel and PowerPoint and confirm there is no repair prompt.
7. Take app screenshots for the README, if the builder has no browser.
8. The P2 run on public purchasing data, including confirming its licence and labelling a sample.

---

## 12. Success measures

| Measure | Target |
|---|---|
| Time for a first-time visitor to see the headline finding (human) | Under 10 seconds: the landing page itself shows the headline finding and the bridge image |
| Two-minute comprehension (10.2; human, after the build) | Four of five test users |
| Held-out matching accuracy | Meets 4.7 |
| False-savings rate | ≤ 2% |
| Workbook tie-out check | `OK` on every export |
| Practitioner review (human, after the build) | At least two people who have done this work review it before launch; their objections are logged and answered in the README |

---

## Appendix A. How independent critique changed the design

Three independent reviewers were asked to argue that the project should not go ahead: one on whether it already exists, one as a merger-procurement practitioner, one on whether a simpler way exists and whether the approach would work. **None found a deal-breaker.** Their serious objections, and where each is answered:

| Objection | Response |
|---|---|
| Consulting firms and spend-analytics vendors already do this | Acknowledged in 1.3. Positioned as an open, auditable demonstration of judgement, not a novel product |
| The premise had the timing wrong and ignored antitrust limits on sharing prices | Reframed as a clean-team tool between signing and close (1.2); masked view (6.9) |
| "Pay the lowest price on everything" overstates savings | Qualified benchmark price, bridge, addressability and capture probabilities (5.2) |
| The levers double count, and cash was mixed with P&L | Sequential declining baseline (5.1, 5.3); cash reported separately (5.4); invariants (5.9) |
| Discount and ramp percentages were invented constants | All are labelled, per-category, user-set assumptions with ranges; reconciled to a top-down band (5.8) |
| The input schema was too clean | Line-level schema with dates, currency, contracts and MPN (3.1); taxonomy mapping (3.4); spend without item codes (4.6) |
| Text similarity will match parts that differ by one digit | Attribute and numeric-token veto; similarity alone never matches (4.4) |
| Unit conversion cannot be done from the original columns | Pack-quantity resolution with status, and the unit-error detector (3.5) |
| A flat fuzzy threshold with chaining merges unrelated vendors | Tax-ID match and veto, guards, no transitive chaining, parent table (4.3) |
| The demo finds what its author planted | Hidden truth, held-out seed, published scorecard and baseline comparison; public-data run as stretch (4.7) |
| Free matching tools make a bespoke matcher redundant | Matching kept simple and transparent; effort concentrated on savings logic, traceability and deliverables (4.1) |
| Too much scope for one person | P0/P1/P2 priorities and a roadmap presentable after M2 (11) |
| Chart export, formula values and heavy models would break on free hosting | Native deck charts, XlsxWriter, no embeddings (7, 9.1) |
| A sleeping free-tier app spoils the first impression | Static landing page and precomputed demo (2.2, 9.4) |
| An auto-generated deck with a point estimate looks naive | Workbook is the primary deliverable; the deck shows ranges, assumptions and limits (7) |

## Appendix B. Glossary

| Term | Meaning |
|---|---|
| Clean team | A restricted group permitted to see both parties' sensitive data before a deal closes |
| Gun-jumping | Co-ordinating or exchanging sensitive information between merging parties before they are allowed to |
| Spend cube | Purchasing data organised by vendor, category and business unit |
| MPN | Manufacturer part number |
| Parent vendor | The ultimate corporate owner of one or more legal-entity suppliers |
| Run-rate saving | The annual saving once fully implemented |
| Days-to-pay | How long a company actually takes to pay a supplier, as opposed to the stated terms |
| Incoterm | A standard trade term stating who pays for freight and where risk passes; it changes what a unit price includes |
| MRO | Maintenance, repair and operations supplies |
| HHI | Herfindahl-Hirschman index, a measure of concentration |
| Tie-out | Confirming that a reported number agrees with its underlying detail |

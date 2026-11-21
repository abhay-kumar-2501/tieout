# Human to-do

Tasks left to the owner (PRD 11.1). Status as of 2026-11-21.

| # | Task | Status |
| --- | --- | --- |
| 1 | Record the 90-second video | Not recorded |
| 2 | Deploy the app and the landing page | Not done |
| 3 | Usability check with five people | Remains with you |
| 4 | Review by two practitioners | Remains with you |
| 5 | Check the names | Web-search screening done; register search remains |
| 6 | Open the workbook and deck in Excel and PowerPoint | See below |
| 7 | App screenshots for the README | Done |
| 8 | Public-data (P2) pass | Not attempted |

## 1. Video (not recorded)

The landing page has the video block commented out, with the bridge image in its place. Uncomment it in `site/index.html` once you have the file.

Suggested 90-second shot list, one shot per step of the in-app tour. Record the app at 1440 px wide on the demo data, clean-team view.

| Time | Page | Show | Say |
| --- | --- | --- | --- |
| 0:00-0:15 | Overview | The headline and the bridge | A plain best-of-both formula says $32M. The defensible figure is $6-13M. The bridge shows where each dollar went. Click the "Unverified matches" bar. |
| 0:15-0:35 | Matching | The accuracy scorecard | Matching is scored against hidden truth on a held-out dataset, next to a naive fuzzy match. Point at vendor precision (99.6% against 3.3%). |
| 0:35-0:55 | Synergies | Click a bar, an item, then "Show working" | Every number is a door: bar, item, then both companies' source rows side by side. |
| 0:55-1:15 | Risk & roadmap | Drag the standard concentration cap | Moving the cap changes the saving given up to protect supply. |
| 1:15-1:30 | Matching | The unit-of-measure flag (the packing tape item on the Overview "Worth a look" card) | A 36x price gap is a pack size, not a saving. Unit errors are removed first and shown. End on the "Illustrative - synthetic data" tag. |

## 2. Deploy (not done)

The repository is private and no hosting account was created, so nothing is deployed.

1. Open Streamlit Community Cloud and create an app from this repository: branch `main`, main file `app/main.py`, Python version 3.11 or later (`requires-python = ">=3.11"` in `pyproject.toml`; 3.12 works). Dependencies come from `requirements.txt`.
2. Copy the app address and set it in `site/config.js`: `const DEMO_URL = "https://<your-app>.streamlit.app";`. While it is `"#"` the landing page button reads "Live demo coming soon". Commit the change to `main`.
3. In the repository on GitHub, open the Actions tab, choose the workflow named "Deploy landing page" (file `.github/workflows/pages.yml`) and run it with "Run workflow". It runs on `workflow_dispatch` only, never on push. Under Settings > Pages, set the source to "GitHub Actions" first.
4. GitHub Pages needs a public repository or a paid plan. If the repository stays private on a free plan, make it public first or host the `site/` folder elsewhere.
5. Open the deployed landing page and check that the "Run locally" link reaches the README's Development section.

A free Streamlit app sleeps after about 12 hours without traffic; the first visitor waits while it wakes. The landing page does not depend on the app being awake.

## 3. Usability check with five people (remains with you)

One-page script for the two-minute check. Seat someone who has not seen the tool, open the live demo on the Overview, and say only: "Think aloud. I can't help, but I'm taking notes."

Tasks (about 40 seconds each):

1. "In your own words, what does the tool say the savings are, and how sure is it?" (Overview.)
2. "Find out why the naive figure is so much bigger than the defensible one, and show me one thing that was removed." (Bridge, then a bar.)
3. "Approve one uncertain match and tell me what changed." (Matching review queue; the headline range updates.)

Note for each person:

- Time to the first correct answer on each task, or "gave up".
- Where they hesitated, re-read or said "what does that mean?"; the exact words they used for a term.
- Whether they noticed "Show working", the view-mode switch and the "Illustrative - synthetic data" tag without prompting.
- What they believed the $6-13M range meant (a forecast, a floor, a target?).
- One thing they would change.

Five people is enough to see repeated problems; fix anything that two or more people hit.

## 4. Practitioner review (remains with you)

Ask two people with procurement or M&A integration experience to read the Overview, the Method & limits screen and the sample workbook. Give them the README and ask what is wrong, what is missing from "What it cannot see", and whether the bridge steps match how they would haircut a synergy case.

## 5. Names (screening done 2026-11-21)

A web-search screening was done on 2026-11-21. It is not a trademark-register search.

Findings:

- No software or company called Tie-Out or TieOut was found.
- The closest is "Financial Statement Tie Out", audit software listed on Capterra: the same generic phrase, in finance and audit.
- A pending US application for TICK & TIE (financial analysis software) and a registered TIEUT mark (Korea) exist.
- The PyPI name `tieout` is already taken. This matters only if you publish there; `tie-out` was free.
- The acquirer and the target have no names in the repository.
- Of 40 sampled synthetic vendor names, one ("Titra") exactly matches a real company (a Turkish defence and aviation firm) and 13 were near but not exact.

Remaining for you:

- Search the registers (USPTO, EUIPO) before any public launch.
- Add "Titra" to the generator's name denylist the next time the demo data is regenerated. The demo data was not regenerated in this pass.

## 6. Excel and PowerPoint open check

Not done. The build could not get access to Excel or PowerPoint on this machine, so neither file has been opened in the real applications.

What the tests do cover: both files open with openpyxl and python-pptx; every workbook formula is re-evaluated by a test evaluator and equals its stored value; the check cell reads `OK`; no shape leaves a slide and no text boxes overlap.

Remaining for the owner:

- [ ] Open `site/assets/tieout_workbook.xlsx` in Excel. Confirm there is no repair prompt, that `Summary` shows `OK` in the check cell, and that changing a value on `Assumptions` moves the figures on `Summary` while the check stays `OK`.
- [ ] Open `site/assets/tieout_deck.pptx` in PowerPoint. Confirm there is no repair prompt and page through the eight slides for clipped or overlapping text.

## 7. Screenshots (done)

The README screenshots are in `docs/screenshots/` (`overview.png`, `matching-review-queue.png`, `risk-roadmap.png`), each 1440 px wide and under 400 KB. To regenerate them, start the app and run the capture script (Google Chrome and `pip install websockets` needed):

```
streamlit run app/main.py --server.headless true --server.port 8791
python scripts/make_screenshots.py
```

The tour pictures are separate: `python scripts/make_tour_images.py`.

## 8. Public-data (P2) pass (not attempted)

Needs a licensed public purchasing dataset whose terms allow this use, and a mapping from its columns to the input schema (PRD 3.1).
Then label a sample by hand (vendor pairs and item pairs) so the scorecard can be computed on it.

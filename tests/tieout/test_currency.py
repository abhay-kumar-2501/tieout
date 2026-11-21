"""Money on screen, in charts and in the deck is written in the run's reporting currency."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest
from pptx import Presentation

from tests.conftest import small_inputs
from tieout import results as views
from tieout.export.deck import build_deck
from tieout.pipeline import run_pipeline
from tieout.reference import load_fx_rates
from tieout.results import Results
from tieout.views.common import set_currency, thousands, unit_price


@pytest.fixture(scope="module")
def eur_results(small_files: dict[str, Path]) -> Results:
    """The small dataset reported in EUR, with an FX table whose rates are into EUR."""
    usd = load_fx_rates()
    eur = pd.DataFrame({"currency": list(usd), "rate": [r / usd["EUR"] for r in usd.values()]})
    return run_pipeline(small_inputs(small_files, reporting_currency="EUR", fx=eur))


@pytest.fixture(autouse=True)
def _back_to_usd():
    yield
    set_currency("USD")


def test_formatters_use_the_sign_for_usd_and_the_code_otherwise() -> None:
    set_currency("USD")
    assert views.money_range(6e6, 13e6) == "$6–13M"
    assert thousands(184_000) == "$184k"
    set_currency("EUR")
    assert views.money_range(6e6, 13e6) == "EUR 6–13M"
    assert views.money_range(6.3e6, 9.6e6) == "EUR 6.3–9.6M"
    assert views.money(32e6) == "EUR 32M"
    assert thousands(184_000) == "EUR 184k"
    assert thousands(-12_000) == "−EUR 12k"
    assert unit_price(1.5) == "EUR 1.5000"


def test_a_run_in_eur_reads_in_eur_on_every_view(eur_results: Results) -> None:
    assert eur_results.totals["currency"] == "EUR"
    top = views.headline(eur_results)
    assert top["range_text"].startswith("EUR ") and "$" not in top["text"]
    assert "$" not in " ".join(views.bridge(eur_results)["text"])
    assert views.overview_figures(eur_results) and "$" not in str(
        views.overview_figures(eur_results)
    )
    assert "$" not in views.reconciliation_text(eur_results)


def test_the_currency_follows_the_results_in_use(
    eur_results: Results, small_results: Results
) -> None:
    assert views.headline(eur_results)["range_text"].startswith("EUR ")
    assert views.headline(small_results)["range_text"].startswith("$")


def test_the_deck_is_in_eur(eur_results: Results) -> None:
    prs = Presentation(io.BytesIO(build_deck(eur_results)))
    texts = [
        shape.text_frame.text
        for slide in prs.slides
        for shape in slide.shapes
        if shape.has_text_frame
    ]
    joined = "\n".join(texts)
    assert "EUR " in joined and "$" not in joined
    formats = [
        shape.chart.value_axis.tick_labels.number_format
        for slide in prs.slides
        for shape in slide.shapes
        if shape.has_chart and hasattr(shape.chart, "value_axis")
    ]
    assert formats and not any("$" in f for f in formats)

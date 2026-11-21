"""View functions: every displayed figure, taken from a ``Results`` (PRD 9.2).

Pure functions ``Results (+ view mode) -> plain dict / DataFrame``: no
Streamlit, no Plotly. The screens, the workbook and the deck read these, so
one calculation produces every number (PRD 7). ``view`` is ``"clean"`` or
``"masked"`` (integration office, PRD 6.9); omitted, the run's own mode is
used. ``tieout.results`` re-exports everything listed here.
"""

from tieout.views.charts import (
    concentration,
    phasing_by_quarter,
    phasing_by_year,
    price_dispersion,
    prioritisation_matrix,
    scenario_table,
    sensitivity_curves,
    spend_pareto,
    tornado_chart,
)
from tieout.views.common import (
    CLEAN,
    MASKED,
    NOT_IN_VIEW,
    Unavailable,
    money,
    money_range,
    percent,
    thousands,
    unit_price,
    vendor_codes,
)
from tieout.views.overview import (
    bridge,
    confidence_strip,
    headline,
    overview_figures,
    reconciliation_text,
    synergy_waterfall,
    worth_a_look,
)
from tieout.views.review import review_item, review_progress, review_queue_items
from tieout.views.tables import (
    CANNOT_SEE,
    data_quality_summary,
    matching_counts,
    scorecard_table,
)
from tieout.views.trace import trace_for

__all__ = [
    "CANNOT_SEE",
    "CLEAN",
    "MASKED",
    "NOT_IN_VIEW",
    "Unavailable",
    "bridge",
    "concentration",
    "confidence_strip",
    "data_quality_summary",
    "headline",
    "matching_counts",
    "money",
    "money_range",
    "overview_figures",
    "percent",
    "phasing_by_quarter",
    "phasing_by_year",
    "price_dispersion",
    "prioritisation_matrix",
    "reconciliation_text",
    "review_item",
    "review_progress",
    "review_queue_items",
    "scenario_table",
    "scorecard_table",
    "sensitivity_curves",
    "spend_pareto",
    "synergy_waterfall",
    "thousands",
    "tornado_chart",
    "trace_for",
    "unit_price",
    "vendor_codes",
    "worth_a_look",
]

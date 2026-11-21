"""Phasing, one-time costs and net three-year value (PRD 5.6).

Month 1 is the close month. With contract end dates, an opportunity's
*available month* is the month after the latest contract end among its lines
that falls between the close date and the planning horizon (0 when there is
none) and its *start month* is that plus the lead time. A recurring
opportunity saves from its start month on: in quarter ``q`` it realises
``run-rate x (months active in q) / 12``. Without contract dates the global
ramp applies instead: each quarter is a quarter of its year's ramp share.
Lever-3 cash appears once, in the quarter of the start month; one-time costs
fall in the start quarter too. Nothing after month 36 enters the three-year
figures.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from tieout.synergy.settings import CASES

__all__ = [
    "CONTRACT",
    "GLOBAL_RAMP",
    "MONTHS",
    "PHASING_COLUMNS",
    "QUARTERS",
    "build_phasing",
    "line_available_month",
    "month_index",
    "months_active",
    "net_three_year",
    "quarter_factors",
    "start_quarter",
    "switching_cost",
    "year_factors",
]

MONTHS = 36
QUARTERS = MONTHS // 3
YEARS = MONTHS // 12
CONTRACT = "contract"
GLOBAL_RAMP = "global_ramp"
PHASING_COLUMNS = ["quarter", "year", "row_type", "lever", "wave", "low", "base", "high"]


def month_index(dates: pd.DatetimeIndex, close: pd.Timestamp) -> np.ndarray:
    """Month number of each date counted from the close month (= 1); NaN for blanks."""
    months = (dates.year - close.year) * 12 + (dates.month - close.month) + 1
    return np.where(dates.isna(), np.nan, np.asarray(months, dtype=float))


def line_available_month(
    contract_end: pd.DatetimeIndex, close: pd.Timestamp, limit: pd.Timestamp
) -> np.ndarray:
    """Month after each line's contract end when it ends within [close, limit]; else 0."""
    in_horizon = np.asarray((contract_end >= close) & (contract_end <= limit), dtype=bool)
    months = month_index(contract_end, close)
    return np.where(in_horizon, np.nan_to_num(months) + 1, 0).astype(np.int64)


def months_active(start: np.ndarray, quarter: int) -> np.ndarray:
    """Months of quarter ``quarter`` (1-based) on or after the start month."""
    first = np.maximum(start, 1)
    return np.clip(3 * quarter - first + 1, 0, 3)


def quarter_factors(start: np.ndarray, method: str, ramp: Mapping[str, float]) -> np.ndarray:
    """``(n, 12)`` share of the run-rate realised in each quarter."""
    start = np.asarray(start, dtype=np.int64)
    if method == GLOBAL_RAMP:
        per_quarter = np.repeat([float(ramp[f"year{y}"]) / 4 for y in range(1, YEARS + 1)], 4)
        return np.tile(per_quarter, (len(start), 1))
    return np.column_stack([months_active(start, q) / 12 for q in range(1, QUARTERS + 1)])


def year_factors(start: np.ndarray, method: str, ramp: Mapping[str, float]) -> np.ndarray:
    """``(n, 3)`` share of the run-rate realised in each of years 1 to 3."""
    return quarter_factors(start, method, ramp).reshape(len(start), YEARS, 4).sum(axis=2)


def start_quarter(start: np.ndarray) -> np.ndarray:
    """Quarter holding the start month (month 0 counts as quarter 1)."""
    return np.maximum(-(-np.asarray(start, dtype=np.int64) // 3), 1)


def switching_cost(
    moved: np.ndarray, event_moved: np.ndarray, fixed: float, pct: float, pi: np.ndarray
) -> np.ndarray:
    """Each moved dollar's share of its switch event's cost, times capture probability.

    Event cost = ``fixed + pct x spend moved``; a part moving ``moved`` of the
    event's ``event_moved`` carries ``fixed x moved / event_moved + pct x moved``.
    """
    share = np.where(event_moved > 0, moved / np.where(event_moved > 0, event_moved, 1.0), 0.0)
    return (fixed * share + pct * moved) * pi


def net_three_year(realised: float, one_time_costs: float) -> float:
    """Realised savings over years 1 to 3 minus the one-time costs in them."""
    return realised - one_time_costs


def _rows(
    quarter: np.ndarray, row_type: str, lever: np.ndarray, wave: np.ndarray, values: np.ndarray
) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "quarter": quarter,
            "row_type": row_type,
            "lever": lever,
            "wave": wave,
            **{case: values[:, i] for i, case in enumerate(CASES)},
        }
    )
    frame = frame[frame["quarter"] <= QUARTERS]
    keys = ["quarter", "row_type", "lever", "wave"]
    return frame.groupby(keys, sort=True)[list(CASES)].sum().reset_index()


def build_phasing(
    opportunities: pd.DataFrame, costs: pd.DataFrame, method: str, ramp: Mapping[str, float]
) -> pd.DataFrame:
    """Quarter x row type x lever x wave, with low / base / high.

    ``opportunities`` needs ``lever``, ``wave``, ``start_month`` and low / base
    / high (run-rate for levers 1 and 2, cash for lever 3). ``costs`` holds the
    one-time cost per opportunity (``opportunity_id``, low / base / high).
    Row types ``saving``, ``cash`` and ``cost`` are never summed together.
    """
    values = opportunities[list(CASES)].to_numpy(dtype=float)
    recurring = (opportunities["lever"] != 3).to_numpy()
    lever = opportunities["lever"].to_numpy()
    wave = opportunities["wave"].to_numpy()
    start = opportunities["start_month"].to_numpy(dtype=np.int64)
    factors = quarter_factors(start[recurring], method, ramp)
    n_rec = int(recurring.sum())
    saving = _rows(
        np.tile(np.arange(1, QUARTERS + 1), n_rec),
        "saving",
        np.repeat(lever[recurring], QUARTERS),
        np.repeat(wave[recurring], QUARTERS),
        (values[recurring][:, None, :] * factors[:, :, None]).reshape(-1, len(CASES)),
    )
    quarter = start_quarter(start)
    cash = _rows(
        quarter[~recurring], "cash", lever[~recurring], wave[~recurring], values[~recurring]
    )
    position = pd.Index(opportunities["opportunity_id"]).get_indexer(costs["opportunity_id"])
    cost = _rows(
        quarter[position],
        "cost",
        lever[position],
        wave[position],
        costs[list(CASES)].to_numpy(dtype=float),
    )
    frame = pd.concat([saving, cash, cost], ignore_index=True)
    frame["year"] = (frame["quarter"] - 1) // 4 + 1
    order = {"saving": 0, "cash": 1, "cost": 2}
    frame = frame.sort_values(
        ["quarter", "row_type", "lever", "wave"],
        key=lambda s: s.map(order) if s.name == "row_type" else s,
        kind="mergesort",
    )
    return frame.reset_index(drop=True)[PHASING_COLUMNS]

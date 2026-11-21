import numpy as np
import pandas as pd
import pytest

from tieout.normalise.units import (
    PACK_FACTORS,
    combine_status,
    convert_units,
    flag_unit_errors,
)


def lines(*rows):
    """A minimal ``lines`` frame; each row is a dict of overrides."""
    base = {
        "uom": "EA",
        "pack_qty": np.nan,
        "item_description": "WIDGET",
        "family": "fasteners",
        "uom_dimension": "count",
        "item_key": "I1",
        "quantity_ann": 10.0,
        "unit_price_rc": 6.0,
    }
    return pd.DataFrame([{**base, **r} for r in rows])


def convert(**overrides):
    return convert_units(lines(overrides)).iloc[0]


FIXED = [
    ("EA", "each", 1),
    ("PC", "each", 1),
    ("UN", "each", 1),
    ("PR", "each", 2),
    ("DZ", "each", 12),
    ("GS", "each", 144),
    ("GRO", "each", 144),
    ("C", "each", 100),
    ("FT", "metre", 0.3048),
    ("IN", "metre", 0.0254),
    ("LB", "kilogram", 0.45359237),
    ("GAL", "litre", 3.785411784),
    ("YD", "metre", 0.9144),
    ("MTR", "metre", 1),
    ("CM", "metre", 0.01),
    ("MM", "metre", 0.001),
    ("KG", "kilogram", 1),
    ("G", "kilogram", 0.001),
    ("GM", "kilogram", 0.001),
    ("OZ", "kilogram", 0.028349523125),
    ("T", "kilogram", 1000),
    ("MT", "kilogram", 1000),
    ("L", "litre", 1),
    ("LT", "litre", 1),
    ("ML", "litre", 0.001),
    ("HR", "hour", 1),
]


@pytest.mark.parametrize(("unit", "base", "factor"), FIXED)
def test_fixed_factor_units(unit, base, factor):
    row = convert(uom=unit)
    assert (row["base_unit"], row["conv_status"]) == (base, "confirmed")
    assert row["base_factor"] == pytest.approx(factor)
    assert row["qty_base"] == pytest.approx(10 * factor)
    assert row["price_base"] == pytest.approx(6 / factor)


@pytest.mark.parametrize("unit", ["each", "metre", "meter", "kilogram", "litre", "liter", "hour"])
def test_units_already_in_a_base_unit_are_confirmed(unit):
    row = convert(uom=unit)
    assert (row["base_factor"], row["conv_status"]) == (1.0, "confirmed")


def test_units_are_trimmed_and_upper_cased():
    assert convert(uom=" dz ")["base_factor"] == 12


def test_pair_is_two_each_except_in_ppe():
    assert convert(uom="PR", family="fasteners")["base_factor"] == 2
    ppe = convert(uom="PR", family="ppe")
    assert (ppe["base_unit"], ppe["base_factor"], ppe["conv_status"]) == ("each", 1, "confirmed")
    assert ppe["price_base"] == 6
    assert convert(uom="PR", family=None)["base_factor"] == 2


@pytest.mark.parametrize(
    ("unit", "dimension", "base", "factor"),
    [
        ("M", "length", "metre", 1),
        ("M", "count", "each", 1000),
        ("GR", "mass", "kilogram", 0.001),
        ("GR", "count", "each", 144),
    ],
)
def test_ambiguous_units_resolve_by_dimension(unit, dimension, base, factor):
    row = convert(uom=unit, uom_dimension=dimension)
    assert (row["base_unit"], row["conv_status"]) == (base, "confirmed")
    assert row["base_factor"] == pytest.approx(factor)


@pytest.mark.parametrize(
    ("unit", "dimension"),
    [("M", "mass"), ("M", "volume"), ("M", "time"), ("M", None), ("GR", "length"), ("GR", None)],
)
def test_ambiguous_units_elsewhere_are_unconverted(unit, dimension):
    row = convert(uom=unit, uom_dimension=dimension)
    assert row["conv_status"] == "unconverted"
    assert row["base_unit"] is None
    assert np.isnan(row["base_factor"])
    assert np.isnan(row["qty_base"]) and np.isnan(row["price_base"])


@pytest.mark.parametrize("unit", ["BX", "CS", "PK", "BG", "RL", "DR", "PL"])
def test_pack_quantity_column_is_confirmed(unit):
    row = convert(uom=unit, pack_qty=25.0, item_description="BOX OF 12")
    assert (row["base_unit"], row["base_factor"], row["conv_status"]) == ("each", 25.0, "confirmed")
    assert row["price_base"] == pytest.approx(6 / 25)
    assert row["qty_base"] == pytest.approx(250)


def test_pack_quantity_is_parsed_from_the_description():
    row = convert(uom="CS", item_description="NITRILE GLOVE CASE OF 1000")
    assert (row["base_factor"], row["conv_status"]) == (1000, "parsed")


def test_pack_with_no_quantity_is_unconverted():
    row = convert(uom="BX", item_description="HEX BOLT M8X40")
    assert row["conv_status"] == "unconverted"
    assert row["base_unit"] is None
    assert np.isnan(row["price_base"])


def test_pack_quantity_column_wins_over_description():
    row = convert(uom="BX", pack_qty=6.0, item_description="BOX OF 12")
    assert (row["base_factor"], row["conv_status"]) == (6, "confirmed")


def test_pack_quantity_is_in_the_category_base_unit():
    row = convert(uom="RL", pack_qty=100.0, uom_dimension="length")
    assert (row["base_unit"], row["base_factor"]) == ("metre", 100)
    assert convert(uom="DR", pack_qty=200.0, uom_dimension="volume")["base_unit"] == "litre"
    assert convert(uom="BG", pack_qty=25.0, uom_dimension="mass")["base_unit"] == "kilogram"


def test_pack_in_an_unknown_category_is_unconverted():
    assert convert(uom="BX", pack_qty=10.0, uom_dimension=None)["conv_status"] == "unconverted"


def test_pack_quantity_is_ignored_for_non_pack_units():
    row = convert(uom="EA", pack_qty=12.0)
    assert (row["base_factor"], row["conv_status"]) == (1, "confirmed")


def test_unrecognised_and_blank_units_are_unconverted():
    assert convert(uom="FURLONG")["conv_status"] == "unconverted"
    assert convert(uom=None)["conv_status"] == "unconverted"


def test_lines_without_an_item_have_status_none():
    row = convert(item_key=None, uom="EA")
    assert row["conv_status"] == "none"
    assert row["base_unit"] is None
    assert np.isnan(row["base_factor"])


def test_input_is_not_modified_and_columns_are_added():
    frame = lines({"uom": "DZ"})
    out = convert_units(frame)
    assert "base_unit" not in frame
    assert list(out.columns[-5:]) == [
        "base_unit",
        "base_factor",
        "conv_status",
        "qty_base",
        "price_base",
    ]


def test_mixed_frame_is_converted_row_by_row():
    out = convert_units(
        lines(
            {"uom": "EA"},
            {"uom": "BX", "item_description": "BX OF 10"},
            {"uom": "M", "uom_dimension": "length"},
            {"uom": "BX"},
        )
    )
    assert out["conv_status"].tolist() == ["confirmed", "parsed", "confirmed", "unconverted"]
    assert out["base_factor"].fillna(0).tolist() == [1, 10, 1, 0]


# ---- suspected unit errors ------------------------------------------------


def items(*rows):
    base = {
        "price_a": 1.0,
        "price_b": 1.0,
        "recorded_a": 1.0,
        "recorded_b": 1.0,
        "status_a": "confirmed",
        "status_b": "confirmed",
    }
    return pd.DataFrame([{**base, **r} for r in rows])


def flag(ratio, status_a="parsed", status_b="confirmed"):
    out = flag_unit_errors(
        items(
            {
                "price_a": ratio,
                "recorded_a": ratio,
                "status_a": status_a,
                "status_b": status_b,
            }
        )
    )
    return out.iloc[0]


@pytest.mark.parametrize("factor", PACK_FACTORS)
def test_rule_a_flags_each_pack_factor(factor):
    row = flag(float(factor))
    assert row["flagged"]
    assert (row["rule"], row["factor"]) == ("a", factor)


@pytest.mark.parametrize(
    ("ratio", "rule", "factor"),
    [
        (2.06, "a", 2),  # +3% inclusive
        (1.94, "a", 2),  # -3% inclusive
        (2.0601, None, None),
        (1.9399, None, None),
        (12.36, "a", 12),
        (11.64, "a", 12),
        (12.37, "b", None),  # outside 3% of 12, but at least 3.0
        (11.63, "b", None),
    ],
)
def test_rule_a_tolerance_is_three_percent_inclusive(ratio, rule, factor):
    row = flag(ratio)
    assert row["rule"] == rule
    assert row["flagged"] == (rule is not None)
    assert (row["factor"] == factor) if factor else np.isnan(row["factor"])


def test_rule_a_needs_a_side_that_is_not_confirmed():
    assert not flag(2.0, "confirmed", "confirmed")["flagged"]
    assert flag(2.0, "confirmed", "parsed")["flagged"]
    assert flag(2.0, "unconverted", "confirmed")["flagged"]


def test_rule_a_message():
    row = flag(12.0)
    assert row["message"] == "This 12.0× price gap looks like a pack of 12, not a saving"
    assert row["rule"] == "a"


def test_rule_b_boundary_at_three():
    row = flag(3.0, "confirmed", "confirmed")
    assert row["flagged"] and row["rule"] == "b"
    assert row["message"] == "This 3.0× gap is too large to be a price difference; check units"
    assert not flag(2.99, "confirmed", "confirmed")["flagged"]


def test_rule_b_applies_whatever_the_status():
    for status in ("confirmed", "parsed", "unconverted"):
        assert flag(7.3, status, status)["flagged"]


def test_rule_a_message_wins_when_both_apply():
    row = flag(10.0, "parsed", "confirmed")
    assert row["rule"] == "a"
    assert "pack of 10" in row["message"]


def test_rule_b_alone_when_status_confirmed_and_near_factor():
    assert flag(10.0, "confirmed", "confirmed")["rule"] == "b"


def test_ratio_is_higher_over_lower_in_either_direction():
    out = flag_unit_errors(items({"price_a": 1.0, "price_b": 12.0, "status_a": "parsed"}))
    assert out.loc[0, "ratio"] == pytest.approx(12.0)
    assert out.loc[0, "flagged"]


def test_unconverted_side_switches_to_recorded_prices():
    row = flag_unit_errors(
        items(
            {
                "price_a": np.nan,
                "price_b": 1.0,
                "recorded_a": 24.0,
                "recorded_b": 1.0,
                "status_a": "unconverted",
            }
        )
    ).iloc[0]
    assert row["ratio"] == pytest.approx(24.0)
    assert row["factor"] == 24


def test_converted_prices_are_used_when_both_sides_converted():
    row = flag_unit_errors(
        items(
            {
                "price_a": 1.1,
                "price_b": 1.0,
                "recorded_a": 13.2,
                "recorded_b": 1.0,
                "status_a": "parsed",
            }
        )
    ).iloc[0]
    assert row["ratio"] == pytest.approx(1.1)
    assert not row["flagged"]


def test_nearest_factor_is_chosen_where_tolerances_overlap():
    assert flag(24.4)["factor"] == 24
    assert flag(24.6)["factor"] == 25


def test_invalid_prices_are_not_flagged():
    out = flag_unit_errors(
        items({"price_a": 0.0}, {"price_a": np.nan}, {"price_a": -5.0}, {"price_b": 0.0})
    )
    assert not out["flagged"].any()
    assert out["ratio"].isna().all()
    assert (out["message"] == "").all()


def test_output_shape_and_index_follow_the_input():
    frame = items({"price_a": 12.0, "status_a": "parsed"}, {"price_a": 1.01})
    frame.index = [5, 9]
    out = flag_unit_errors(frame)
    assert list(out.index) == [5, 9]
    assert list(out.columns) == ["ratio", "factor", "rule", "flagged", "message"]
    assert out["flagged"].tolist() == [True, False]
    assert out["rule"].tolist() == ["a", None]


def test_combine_status_takes_the_worst():
    assert combine_status(pd.Series(["confirmed", "parsed"])) == "parsed"
    assert combine_status(pd.Series(["confirmed", "unconverted", "parsed"])) == "unconverted"
    assert combine_status(pd.Series(["confirmed", "none"])) == "confirmed"
    assert combine_status(pd.Series(["none"])) == "none"

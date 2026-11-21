"""Critical-attribute parsers and veto rules (PRD 4.4, I2).

Each family has the same item written in two ERP styles (must agree, no
conflict) and near-miss pairs differing in exactly one attribute (must conflict).
"""

import pytest

from tieout.match.attributes import (
    bare_numbers,
    compare,
    numeric_tokens,
    parse_description,
)


def _cmp(a: str, b: str, family: str):
    return compare(parse_description(a, family), parse_description(b, family), family)


def _assert_same(a: str, b: str, family: str, min_agree: int = 1) -> None:
    pa, pb = parse_description(a, family), parse_description(b, family)
    result = compare(pa, pb, family)
    assert not result.conflicts, (pa, pb, result.conflicts)
    assert len(result.agreements) >= min_agree, (pa, pb)


def _assert_conflict(a: str, b: str, family: str, key: str) -> None:
    pa, pb = parse_description(a, family), parse_description(b, family)
    result = compare(pa, pb, family)
    assert result.veto, (pa, pb)
    assert key in {k for k, _, _ in result.conflicts}, (pa, pb, result.conflicts)


# ------------------------------------------------------------------ PRD examples


def test_prd_m8x40_vs_m8x45_is_vetoed() -> None:
    result = _cmp("HHCS M8X40 8.8 ZP", "HHCS M8X45 8.8 ZP", "fasteners")
    assert result.veto
    assert ("length", "40MM", "45MM") in result.conflicts


def test_prd_6204_2rs_vs_6204_zz_is_vetoed() -> None:
    result = _cmp("BRG 6204-2RS", "BRG 6204-ZZ", "bearings")
    assert result.veto
    assert ("seal", "2RS", "ZZ") in result.conflicts


@pytest.mark.parametrize(
    ("family", "boxed", "each"),
    [
        ("fasteners", "HHCS M8X40 8.8 ZP BOX OF 100", "HHCS M8X40 8.8 ZP"),
        ("generic", "HYD OIL ISO 46 1 GAL CASE OF 12", "HYD OIL ISO 46 1 GAL"),
        ("generic", "CABLE TIE 8IN 50LB 100/BX", "CABLE TIE 8IN 50LB"),
        ("ppe", "GLV NTR DISP 4MIL LG BX/100", "NITRILE EXAM GLOVE LARGE 4 MIL"),
        ("abrasives", "FLAP DISC 4-1/2 X 7/8 60 GRIT PK OF 10", "FLAP DISC 4-1/2 X 7/8 60 GRIT"),
    ],
)
def test_box_of_n_against_each_is_not_a_conflict(family: str, boxed: str, each: str) -> None:
    result = _cmp(boxed, each, family)
    assert not result.veto
    assert not result.subset_only


# ------------------------------------------------------------------- fasteners

FASTENER_SAME = [
    ("HHCS M8 x 40 8.8 ZP", "HEX HD CAP SCREW M8-40 CL 8.8 ZINC PLT"),
    ("HEX CAP SCREW 1/4-20 X 1 GR5 ZINC", 'HHCS 1/4"-20 x 1" GRADE 5 ZP'),
    (
        "SHCS M8-1.25X40 ALY STL BLK OX 12.9",
        "SOCKET HEAD CAP SCREW M8 X 1.25 X 40MM ALLOY STEEL BLACK OXIDE CL12.9",
    ),
    ("3/8 FLAT WASHER SS 18-8", "FLAT WASHER 3/8IN 18-8 STAINLESS"),
    ("HEX NUT M10 A2-70 BOX OF 100", "NUT HX M10 SS A2-70"),
    ("#10-24 X 3/4 PAN HEAD PHILLIPS MACHINE SCREW 18-8 SS", "MACH SCR PAN PHL 10-24X3/4 SS 18-8"),
    ("CARRIAGE BOLT 3/8-16 X 2 HDG", "BOLT CARR 3/8IN-16 X 2IN HOT DIP GALV"),
    ("SOCKET SET SCREW M6X10 CUP POINT BLK", "SHSS M6 X 10MM BLACK OXIDE"),
    ("THREADED ROD 1/2-13 X 6FT ZINC", "ALL THREAD ROD 1/2IN-13 X 72IN ZP"),
    ("FLANGE BOLT M10-1.5X30 10.9 ZINC FLAKE", "HEX FLANGE SCREW M10 X 1.5 X 30 CLASS 10.9 GEOMET"),
]


@pytest.mark.parametrize(("a", "b"), FASTENER_SAME)
def test_fastener_styles_agree(a: str, b: str) -> None:
    _assert_same(a, b, "fasteners", min_agree=2)
    assert _cmp(a, b, "fasteners").auto_eligible


@pytest.mark.parametrize(
    ("a", "b", "key"),
    [
        ("HHCS M8X40 8.8 ZP", "HHCS M8X45 8.8 ZP", "length"),
        ("HHCS M8X40 8.8 ZP", "HHCS M10X40 8.8 ZP", "thread"),
        ("HHCS 1/4-20 X 1 GR5", "HHCS 1/4-28 X 1 GR5", "pitch"),
        ("HHCS M8X40 8.8 ZP", "HHCS M8X40 10.9 ZP", "grade"),
        ("HHCS 1/2-13 X 2 GR5 ZP", "HHCS 1/2-13 X 2 GR5 HDG", "finish"),
        ("HEX NUT M8 SS", "HEX NUT M8 BRASS", "material"),
        ("SHCS M6X20 ALLOY", "BHCS M6X20 ALLOY", "head"),
        ("3/8 FLAT WASHER ZP", "1/2 FLAT WASHER ZP", "thread"),
        ("HHCS 1/2-13 X 1-1/2 GR5", "HHCS 1/2-13 X 1-3/4 GR5", "length"),
    ],
)
def test_fastener_near_misses_conflict(a: str, b: str, key: str) -> None:
    _assert_conflict(a, b, "fasteners", key)


def test_fastener_canonical_values() -> None:
    parsed = parse_description('HHCS 1/2"-13 x 1-1/2" GR 5 ZP STL', "fasteners")
    assert parsed["thread"] == "0.5"
    assert parsed["pitch"] == "13"
    assert parsed["length"] == "1.5IN"
    assert parsed["grade"] == "GR5"
    assert parsed["material"] == "STEEL"


# -------------------------------------------------------------------- bearings

BEARING_SAME = [
    ("BRG BALL 6204-2RS", "6204 2RS1 DEEP GROOVE BALL BEARING"),
    ("BEARING 6204 ZZ C3", "6204-2Z/C3 BALL BRG"),
    ("6205-2RS1/C3 SKF", "BALL BEARING 6205 2RS C3"),
    ("6304ZZ", "BEARING 6304-ZZ"),
    ("22210E SPHERICAL ROLLER BRG", "BRG SPHRCL ROLR 22210 E"),
    ("UCP205-16 PILLOW BLOCK", "PLWBLK BRG UCP205-16"),
    ("6000-2RSH", "6000 LLU BEARING"),
    ("NU206 CYL ROLLER BRG", "CYLINDRICAL ROLLER BEARING NU206"),
    ("30205 TAPERED ROLLER BEARING", "BRG TPR ROLR 30205"),
]


@pytest.mark.parametrize(("a", "b"), BEARING_SAME)
def test_bearing_styles_agree(a: str, b: str) -> None:
    _assert_same(a, b, "bearings")


def test_bearing_suffix_renderings_compare_equal() -> None:
    assert parse_description("6204-2RS", "bearings") == parse_description("6204 2RS", "bearings")
    assert parse_description("6204-2RS1/C3", "bearings") == {
        "designation": "6204",
        "seal": "2RS",
        "clearance": "C3",
    }
    assert _cmp("6204-2RS1/C3", "BRG 6204 2RS C3", "bearings").auto_eligible


@pytest.mark.parametrize(
    ("a", "b", "key"),
    [
        ("BRG 6204-2RS", "BRG 6204-ZZ", "seal"),
        ("BRG 6204-2RS", "BRG 6205-2RS", "designation"),
        ("BRG 6204-2RS C3", "BRG 6204-2RS", "clearance"),
        ("BRG 6204", "BRG 6204-2RS", "seal"),
        ("22210E BRG", "22210CC BRG", "suffix"),
        ("6204-2RS C3", "6204-2RS C4", "clearance"),
        ("BEARING 6204 RS", "BEARING 6204 2RS", "seal"),
        ("UCP205-16", "UCP205-12", "suffix"),
    ],
)
def test_bearing_near_misses_conflict(a: str, b: str, key: str) -> None:
    _assert_conflict(a, b, "bearings", key)


# ------------------------------------------------------------------------- pvf

PVF_SAME = [
    ('BALL VLV 1/2" FNPT SS316 1000 WOG', "1/2IN BALL VALVE 316 STAINLESS FEMALE NPT 1000 PSI"),
    ("ELBOW 90 DEG 1-1/2 SCH 40 BW CS", "90 ELL 1-1/2IN SCHEDULE 40 BUTT WELD CARBON STEEL"),
    ("PIPE NIPPLE 1/2 X 3 GALV", "NIPL 1/2IN X 3IN GALVANIZED STEEL"),
    ("REDUCER 2 X 1 SW 3000# A105", "RDCR 2IN X 1IN SOCKET WELD CLASS 3000 FORGED STEEL"),
    ('GATE VALVE 2" 150# FLGD RF CS', "VLV GATE 2IN CL150 FLANGED CARBON STEEL"),
    ("PVC PIPE 2IN SCH80 PLAIN END", 'PIPE PVC SCHEDULE 80 2" PE'),
    ("COUPLING 3/4 FNPT 150# MALLEABLE IRON", "CPLG 3/4IN THREADED CLASS 150 MALLEABLE"),
    ("BUTTERFLY VALVE 4IN LUG DUCTILE IRON 200 PSI", 'BFLY VLV 4" LUG DUCTILE 200PSI CWP'),
    (
        "FLANGE WELD NECK 3IN 300# RF SCH40 A105",
        '3" WN FLG CL300 RAISED FACE SCHEDULE 40 CARBON STEEL',
    ),
]


@pytest.mark.parametrize(("a", "b"), PVF_SAME)
def test_pvf_styles_agree(a: str, b: str) -> None:
    _assert_same(a, b, "pvf", min_agree=2)
    assert _cmp(a, b, "pvf").auto_eligible


@pytest.mark.parametrize(
    ("a", "b", "key"),
    [
        ("BALL VALVE 1/2IN NPT SS 1000 WOG", "BALL VALVE 3/4IN NPT SS 1000 WOG", "size"),
        ("GATE VALVE 2IN 150# FLGD CS", "GATE VALVE 2IN 300# FLGD CS", "class"),
        ("BALL VALVE 1/2IN NPT SS", "BALL VALVE 1/2IN NPT BRASS", "material"),
        ("COUPLING 1IN NPT 3000# A105", "COUPLING 1IN SW 3000# A105", "end"),
        ("PIPE 2IN SCH40 CS", "PIPE 2IN SCH80 CS", "schedule"),
        ("ELBOW 45 DEG 2IN SCH40 BW CS", "ELBOW 90 DEG 2IN SCH40 BW CS", "angle"),
        ("PIPE NIPPLE 1/2 X 3 GALV", "PIPE NIPPLE 1/2 X 4 GALV", "length"),
        ("REDUCER 2 X 1 SW 3000#", "REDUCER 2 X 3/4 SW 3000#", "size"),
    ],
)
def test_pvf_near_misses_conflict(a: str, b: str, key: str) -> None:
    _assert_conflict(a, b, "pvf", key)


def test_pvf_pressure_class_renderings() -> None:
    for text in (
        "GATE VALVE 150#",
        "GATE VALVE 150 LB",
        "GATE VALVE CLASS 150",
        "GATE VALVE CL150",
    ):
        assert parse_description(text, "pvf")["class"] == "CL150"


# ------------------------------------------------------------------ electrical

ELECTRICAL_SAME = [
    ("CONTACTOR 3P 40A 120VAC COIL", "CONTR 3 POLE 40 AMP 120V AC COIL"),
    ("MOTOR 5HP 230/460V 3PH 1800RPM TEFC", "5 HP MTR TEFC 230/460 VOLT 3 PHASE 1800 RPM"),
    ("WIRE THHN 12 AWG 600V BLK", "THHN 12GA 600 VOLT BLACK WIRE"),
    ("SJOOW 12/3 CORD 600 V", "CORD SJOOW 12AWG 3 COND 600V"),
    ("BRKR 2 POLE 20 AMP 240V", "CIRCUIT BREAKER 2P 20A 240VAC"),
    ("RELAY 24VDC 2 POLE 10A", "RLY DPDT 10 AMP 24 VDC"),
    ("VFD 10HP 480V 3PH NEMA 1", "DRIVE AC 10 HP 480 VAC THREE PHASE NEMA1"),
    ("DISCONNECT SWITCH 3P 60A 600V NEMA 3R", "SW DISC 3 POLE 60AMP 600VAC TYPE 3R"),
    ("MOTOR 1/2HP 115V 1PH ODP 1725RPM", "MTR 0.5 HP SINGLE PHASE 115 VOLT OPEN DRIP 1725 RPM"),
]


@pytest.mark.parametrize(("a", "b"), ELECTRICAL_SAME)
def test_electrical_styles_agree(a: str, b: str) -> None:
    _assert_same(a, b, "electrical", min_agree=2)
    assert _cmp(a, b, "electrical").auto_eligible


@pytest.mark.parametrize(
    ("a", "b", "key"),
    [
        ("BREAKER 2P 20A 120V", "BREAKER 2P 20A 240V", "voltage"),
        ("BREAKER 2P 20A 240V", "BREAKER 2P 30A 240V", "current"),
        ("BREAKER 2P 20A 240V", "BREAKER 3P 20A 240V", "poles"),
        ("ENCLOSURE NEMA 1 24X20", "ENCLOSURE NEMA 4X 24X20", "enclosure"),
        ("WIRE THHN 12AWG 600V", "WIRE THHN 14AWG 600V", "gauge"),
        ("MOTOR 5HP 460V 3PH TEFC", "MOTOR 7.5HP 460V 3PH TEFC", "power"),
        ("MOTOR 5HP 460V 3PH TEFC", "MOTOR 5HP 460V 3PH ODP", "enclosure"),
        ("SENSOR 24VDC IP67", "SENSOR 24VDC IP65", "enclosure"),
    ],
)
def test_electrical_near_misses_conflict(a: str, b: str, key: str) -> None:
    _assert_conflict(a, b, "electrical", key)


# ------------------------------------------------------------------------ ppe

PPE_SAME = [
    ("GLV NTR DISP 4MIL LG BX/100", "NITRILE EXAM GLOVES LARGE 4 MIL 100/BX"),
    ("GLOVE PU COATED NYLON SZ 9", "NYLON GLOVE POLYURETHANE PALM COATED SIZE 9"),
    ("GLOVE LEATHER DRIVER COWHIDE XL", "COWHIDE DRIVERS GLOVES X-LARGE"),
    ("EARPLUGS FOAM NRR 32", "EAR PLUG FOAM 32 NRR"),
    ("RESPIRATOR N95 DISPOSABLE BX/20", "DISP RESP N95 20/BX"),
    ("LATEX GLOVE MED POWDER FREE", "GLOVES LTX M PF"),
    ("CUT RESISTANT GLOVE HPPE A4 LG", "GLOVE CUT A4 HPPE LARGE"),
    ("SAFETY GLASSES CLEAR LENS", "SFTY GLSS CLEAR ANTI FOG"),
    ("VINYL GLOVE DISPOSABLE XL 100/BX", "GLV VINYL DISP X-LARGE"),
]


@pytest.mark.parametrize(("a", "b"), PPE_SAME)
def test_ppe_styles_agree(a: str, b: str) -> None:
    _assert_same(a, b, "ppe", min_agree=2)


@pytest.mark.parametrize(
    ("a", "b", "key"),
    [
        ("GLOVE NITRILE DISP LARGE", "GLOVE NITRILE DISP XL", "size"),
        ("GLOVE NITRILE DISP LARGE", "GLOVE LATEX DISP LARGE", "material"),
        ("GLOVE NITRILE DISP 4MIL L", "GLOVE NITRILE DISP 6MIL L", "thickness"),
        ("CUT GLOVE HPPE A4 L", "CUT GLOVE HPPE A2 L", "cut_level"),
        ("GLOVE PU COATED NYLON SZ 9", "GLOVE PU COATED NYLON SZ 10", "size"),
        ("GLOVE NITRILE COATED NYLON M", "GLOVE PU COATED NYLON M", "coating"),
        ("SAFETY GLASSES CLEAR", "SAFETY GLASSES GRAY", "lens"),
        ("RESPIRATOR N95", "RESPIRATOR P100", "rating"),
    ],
)
def test_ppe_near_misses_conflict(a: str, b: str, key: str) -> None:
    _assert_conflict(a, b, "ppe", key)


# ------------------------------------------------------------------ abrasives

ABRASIVE_SAME = [
    ("CUTOFF WHL 4-1/2 X .045 X 7/8 T1", "4.5IN X 0.045IN X 7/8IN CUT-OFF WHEEL TYPE 1"),
    ("FLAP DISC 4-1/2 X 7/8 60 GRIT ZIRC T29", 'ZIRCONIA FLAP DISC T29 4.5" 60G 7/8 ARBOR'),
    ("GRINDING WHEEL 100X6X22MM T27", "GRNDG WHL T27 100 X 6 X 22.0 MM"),
    ("10IN 60T CARBIDE SAW BLADE 5/8 ARBOR", 'SAW BLADE CRBD 10" 60 TOOTH 5/8IN BORE'),
    ("DRILL BIT 1/4IN HSS 135 DEG JOBBER", 'JOBBER DRL 1/4" HIGH SPEED STEEL 135DEG'),
    ("SANDING DISC 5IN P120 HOOK AND LOOP", '5" HOOK AND LOOP DISC 120 GRIT'),
    ("END MILL 1/2IN 4FL CARBIDE", "CRBD END MILL 4 FLUTE 0.5IN"),
    ("TAP 1/4-20 HSS PLUG 3FL", "HSS PLUG TAP 1/4-20 UNC 3 FLUTE"),
    ("INSERT CNMG 432 MF", "CNMG432 TURNING INSERT"),
    ("SANDING BELT 2X72 80 GRIT ZIRC", "BELT 2IN X 72IN ZIRCONIA 80G"),
]


@pytest.mark.parametrize(("a", "b"), ABRASIVE_SAME)
def test_abrasive_styles_agree(a: str, b: str) -> None:
    _assert_same(a, b, "abrasives")


@pytest.mark.parametrize(
    ("a", "b", "key"),
    [
        ("CUTOFF WHEEL 4-1/2 X .045 X 7/8", "CUTOFF WHEEL 5 X .045 X 7/8", "diameter"),
        ("FLAP DISC 4-1/2 X 7/8 60 GRIT", "FLAP DISC 4-1/2 X 7/8 80 GRIT", "grit"),
        ("GRINDING WHEEL 4-1/2 X 1/4 X 7/8", "GRINDING WHEEL 4-1/2 X 1/4 X 5/8-11", "bore"),
        ("GRINDING WHEEL 4-1/2 X 1/4 X 7/8 T27", "GRINDING WHEEL 4-1/2 X 1/4 X 7/8 T29", "type"),
        ("CUTOFF WHEEL 4-1/2 X .045 X 7/8", "CUTOFF WHEEL 4-1/2 X 1/16 X 7/8", "thickness"),
        ("SAW BLADE 10IN 60T 5/8 ARBOR", "SAW BLADE 10IN 80T 5/8 ARBOR", "teeth"),
        ("END MILL 1/2IN 4FL CARBIDE", "END MILL 1/2IN 2FL CARBIDE", "flutes"),
        ("FLAP DISC 4-1/2 X 7/8 60 GRIT ZIRC", "FLAP DISC 4-1/2 X 7/8 60 GRIT CERAMIC", "material"),
    ],
)
def test_abrasive_near_misses_conflict(a: str, b: str, key: str) -> None:
    _assert_conflict(a, b, "abrasives", key)


# -------------------------------------------------------------------- generic


def test_generic_tokens_are_canonical() -> None:
    assert numeric_tokens("ROPE 1/2IN X 600 FT") == numeric_tokens("ROPE 0.5 IN X 600FT")
    assert numeric_tokens("BOX 12X10X8IN") == numeric_tokens("BOX 12INX10INX8IN")
    assert numeric_tokens("IPA 99% 1 GALLON") == frozenset({"99%", "1GAL"})
    assert numeric_tokens("3M TAPE 2IN") == frozenset({"2IN"})


def test_generic_identical_sets_agree() -> None:
    result = _cmp("POLY ROPE 1/2IN X 600FT", "ROPE POLY 0.5 IN X 600 FT", "generic")
    assert not result.veto and not result.subset_only
    assert result.critical_agreements == 2
    assert result.auto_eligible


def test_generic_strict_subset_is_review_only() -> None:
    result = _cmp("STRETCH FILM 18IN X 1500FT 80GA", "STRETCH FILM 18IN X 1500FT", "generic")
    assert not result.veto
    assert result.subset_only
    assert not result.auto_eligible


def test_generic_other_difference_is_hard_veto() -> None:
    result = _cmp("STRETCH FILM 18IN X 1500FT 80GA", "STRETCH FILM 18IN X 1500FT 90GA", "generic")
    assert result.veto
    result = _cmp("LABEL 4X6 THERMAL", "LABEL 4X3 THERMAL", "generic")
    assert result.veto


def test_generic_no_tokens_is_identical_but_never_auto() -> None:
    result = _cmp("PAINT RED ENAMEL", "ENAMEL PAINT RED", "generic")
    assert not result.veto and not result.subset_only
    assert not result.auto_eligible


# ------------------------------------------------------------------- compare


def test_missing_attribute_is_not_a_conflict() -> None:
    result = compare({"thread": "M8", "length": "40MM"}, {"thread": "M8"}, "fasteners")
    assert not result.veto
    assert result.agreements == (("thread", "M8"),)
    assert not result.auto_eligible


def test_guard_keys_conflict_but_do_not_count() -> None:
    a = {"thread": "M8", "kind": "NUT", "style": "JAM"}
    b = {"thread": "M8", "kind": "NUT", "style": "NYLON INSERT"}
    result = compare(a, b, "fasteners")
    assert result.veto
    same = compare({"thread": "M8", "kind": "NUT"}, {"thread": "M8", "kind": "NUT"}, "fasteners")
    assert same.critical_agreements == 1
    assert not same.auto_eligible


def test_unknown_family_uses_generic_rules() -> None:
    assert compare({"1IN": "1IN"}, {"2IN": "2IN"}, None).veto
    assert compare({"1IN": "1IN"}, {"1IN": "1IN", "2IN": "2IN"}, "other").subset_only


def test_bare_numbers() -> None:
    assert bare_numbers("HYD OIL ISO 46 5GAL") == frozenset({"46"})
    assert bare_numbers("PIPE 1-1/2 X 3") == frozenset({"1.5", "3"})
    assert bare_numbers("M8X40 6204-2RS") == frozenset()

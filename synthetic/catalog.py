# ruff: noqa: E501
"""Item templates: what a true item is, per common L2 category.

Each template names a noun phrase and an ordered list of attribute roles with
value pools. A true item is a template plus one value per role. Roles hold the
critical attributes of PRD 4.4 for parser families (thread, length, grade and
finish for fasteners; the full designation for bearings; size, class, material
and end for pipe, valves and fittings; voltage, current, poles and enclosure
for electrical; type, material and size for PPE; diameter, grit and bore for
abrasives) and numeric-and-unit tokens for the generic family.
"""

from __future__ import annotations

from dataclasses import dataclass

# Formats that render differently per ERP style in parser families.
_SIZE_B = {"S": "SM", "M": "MED", "L": "LG", "XL": "XL", "2XL": "XXL", "3XL": "XXXL"}


@dataclass(frozen=True)
class Role:
    name: str
    values: tuple[str, ...]
    fmt: str = "plain"  # plain | x | inch | class | size | poles | desig
    scale: bool = False  # value position drives price


@dataclass(frozen=True)
class Template:
    l2: str
    kind: str
    noun: tuple[str, ...]
    roles: tuple[Role, ...]
    cost: float  # median USD per base unit
    weight: float = 1.0
    packs: tuple[int, ...] = ()
    scale_step: float = 0.25


def _r(name: str, values: str | tuple[str, ...], fmt: str = "plain", scale: bool = False) -> Role:
    vals = tuple(v.strip() for v in values.split("|")) if isinstance(values, str) else values
    return Role(name, vals, fmt, scale)


M_THREAD = "M4|M5|M6|M8|M10|M12|M14|M16|M20|M24"
M_LEN = "8|10|12|16|20|25|30|35|40|45|50|55|60|65|70|80|90|100|110|120|150|180|200"
I_THREAD = "#10-24|#10-32|1/4-20|5/16-18|3/8-16|7/16-14|1/2-13|5/8-11|3/4-10|7/8-9|1-8"
I_LEN = "1/2|5/8|3/4|7/8|1|1-1/4|1-1/2|1-3/4|2|2-1/4|2-1/2|2-3/4|3|3-1/2|4|4-1/2|5|6|7|8"
M_SPEC = "8.8 ZP|8.8 HDG|8.8 PLAIN|10.9 ZP|10.9 BLKOX|12.9 BLKOX|A2-70 SS|A4-80 SS"
I_SPEC = "GR5 ZP|GR5 YZN|GR5 PLAIN|GR8 YZN|GR8 ZP|GR2 ZP|GR2 HDG|18-8 SS|316 SS|GR8 PLAIN"
NPS = "1/4|3/8|1/2|3/4|1|1-1/4|1-1/2|2|2-1/2|3|4|6|8"
GLOVE_SIZE = "S|M|L|XL|2XL"

# Bearing designations built from series, bore code, seal and clearance.
_BALL = tuple(
    f"{series}{bore:02d}{seal}{clear}"
    for series in ("60", "62", "63", "68", "69")
    for bore in range(0, 17)
    for seal in ("-2RS", "-ZZ", "", "-RS", "-2Z")
    for clear in ("", " C3")
)
_ROLLER = tuple(
    [f"{s}{b:02d}" for s in ("302", "303", "322", "323", "320") for b in range(4, 21)]
    + [
        f"{s}{b:02d} {suf}"
        for s in ("222", "223", "213")
        for b in range(5, 21)
        for suf in ("E", "EK", "E C3", "EK C3")
    ]
    + [
        f"{s} {b:d}{t} {suf}"
        for s in ("NU", "NJ", "NUP")
        for b in (204, 205, 206, 207, 208, 209, 210, 212)
        for t in ("",)
        for suf in ("ECP", "ECJ", "ECP C3")
    ]
    + [f"NA {b}" for b in (4900, 4901, 4902, 4903, 4904, 4905, 4906, 4907, 4908, 6905)]
)
_MOUNTED = tuple(
    f"{h}{bore}{inch}"
    for h in ("UCP2", "UCF2", "UCFL2", "UCT2", "UCPA2", "UCFC2")
    for bore in ("04", "05", "06", "07", "08", "09", "10", "11", "12")
    for inch in ("", "-12", "-16", "-20", "-24", "-31")
)

TEMPLATES: tuple[Template, ...] = (
    # ---- L01 raw materials (generic, mass) ---------------------------------
    Template(
        "L01.01",
        "flat_bar",
        ("FLAT", "BAR"),
        (
            _r("grade", "A36 HR|1018 CD|1045 HR|A572-50"),
            _r(
                "size",
                "1/8X1|1/8X2|3/16X1-1/2|1/4X1|1/4X2|1/4X3|1/4X4|3/8X2|3/8X3|3/8X4|1/2X2|1/2X3|1/2X4|1/2X6|3/4X3|3/4X4|1X4|1X6",
                scale=True,
            ),
            _r("length", "10FT|12FT|20FT"),
        ),
        1.6,
        scale_step=0.02,
    ),
    Template(
        "L01.01",
        "round_bar",
        ("ROUND", "BAR"),
        (
            _r("grade", "1018 CD|4140 HT|1045 TGP|12L14 CD|4340 ANN"),
            _r(
                "dia",
                "1/2IN|5/8IN|3/4IN|7/8IN|1IN|1-1/4IN|1-1/2IN|1-3/4IN|2IN|2-1/2IN|3IN|3-1/2IN|4IN",
                scale=True,
            ),
            _r("length", "10FT|12FT|20FT"),
        ),
        2.1,
        scale_step=0.02,
    ),
    Template(
        "L01.01",
        "plate",
        ("PLATE",),
        (
            _r("grade", "A36|A572-50|AR400|A516-70"),
            _r("thk", "3/16IN|1/4IN|5/16IN|3/8IN|1/2IN|5/8IN|3/4IN|1IN|1-1/4IN|1-1/2IN|2IN"),
            _r("size", "48X96|60X120|72X144|96X240"),
        ),
        1.4,
        scale_step=0.0,
    ),
    Template(
        "L01.02",
        "ss_sheet",
        ("SHEET",),
        (
            _r("grade", "304 2B|304 #4|316L 2B|430 BA|316 #4"),
            _r("gauge", "10GA|11GA|12GA|14GA|16GA|18GA|20GA|22GA|24GA"),
            _r("size", "36X96|48X96|48X120|60X120"),
        ),
        5.2,
        scale_step=0.0,
    ),
    Template(
        "L01.02",
        "ss_bar",
        ("ROUND", "BAR"),
        (
            _r("grade", "304|316L|303|17-4PH|410|2205"),
            _r("dia", "1/4IN|3/8IN|1/2IN|5/8IN|3/4IN|1IN|1-1/4IN|1-1/2IN|2IN|2-1/2IN|3IN|4IN"),
            _r("length", "12FT|20FT"),
        ),
        6.4,
        scale_step=0.0,
    ),
    Template(
        "L01.03",
        "al_plate",
        ("PLATE",),
        (
            _r("grade", "6061-T6|6061-T651|5052-H32|7075-T6|5083-H116|2024-T3"),
            _r("thk", "0.063IN|0.090IN|0.125IN|0.190IN|0.250IN|0.375IN|0.500IN|0.750IN|1.000IN"),
            _r("size", "48X96|48X144|60X120|36X96"),
        ),
        6.8,
        scale_step=0.0,
    ),
    Template(
        "L01.03",
        "copper",
        ("BUS", "BAR"),
        (
            _r("grade", "C110 HH|C101 OFHC|C145"),
            _r("size", "1/8X1|1/4X1|1/4X2|1/4X3|3/8X2|3/8X4|1/2X4|1/4X4|1/2X6"),
            _r("length", "12FT|10FT"),
        ),
        11.5,
        scale_step=0.0,
    ),
    Template(
        "L01.04",
        "resin",
        ("RESIN",),
        (
            _r("polymer", "PP HOMOPOLYMER|PP COPOLYMER|HDPE|LDPE|ABS|PC|NYLON 6|NYLON 66|POM|PBT"),
            _r("mfi", "MFI 2|MFI 4|MFI 8|MFI 12|MFI 20|MFI 35"),
            _r("fill", "UNFILLED|30% GF|15% GF|20% TALC|UV STAB"),
        ),
        2.4,
        scale_step=0.0,
    ),
    Template(
        "L01.04",
        "plastic_rod",
        ("ROD",),
        (
            _r("polymer", "NYLON 6/6|ACETAL|UHMW|PTFE|PEEK|HDPE|POLYCARB"),
            _r("dia", "1/2IN|3/4IN|1IN|1-1/2IN|2IN|2-1/2IN|3IN|4IN"),
            _r("length", "4FT|8FT|10FT"),
        ),
        9.0,
        scale_step=0.0,
    ),
    # ---- castings (generic, count) -----------------------------------------
    Template(
        "L01.05",
        "casting",
        ("CASTING",),
        (
            _r("part", "HOUSING|BRACKET|COVER|IMPELLER|HUB|FLANGE|BODY|BASE|ARM|YOKE"),
            _r("matl", "DUCTILE 65-45-12|GREY CL30|CF8M|WCB|A356-T6|CA954"),
            _r("dwg", tuple(f"DWG {n}" for n in range(1100, 1700, 7))),
            _r("rev", "REV A|REV B|REV C|REV D"),
        ),
        140.0,
        scale_step=0.0,
    ),
    Template(
        "L01.05",
        "forging",
        ("FORGING",),
        (
            _r("part", "SHAFT|GEAR BLANK|RING|LINK|CLEVIS|HOOK"),
            _r("matl", "4140|4340|1045|8620|F316"),
            _r("dwg", tuple(f"DWG {n}" for n in range(2200, 2800, 9))),
            _r("rev", "REV A|REV B|REV C"),
        ),
        260.0,
        weight=0.6,
        scale_step=0.0,
    ),
    # ---- L02 fasteners ------------------------------------------------------
    Template(
        "L02.01",
        "hex_bolt_m",
        ("HEX", "BOLT"),
        (_r("thread", M_THREAD, scale=True), _r("length", M_LEN, "x"), _r("spec", M_SPEC)),
        0.16,
        1.6,
        packs=(25, 50, 100, 200),
        scale_step=0.35,
    ),
    Template(
        "L02.01",
        "hhcs_i",
        ("HEX", "HEAD", "CAP", "SCREW"),
        (_r("thread", I_THREAD, scale=True), _r("length", I_LEN, "x"), _r("spec", I_SPEC)),
        0.14,
        1.6,
        packs=(25, 50, 100),
        scale_step=0.35,
    ),
    Template(
        "L02.01",
        "shcs_m",
        ("SOCKET", "HEAD", "CAP", "SCREW"),
        (
            _r("thread", "M3|M4|M5|M6|M8|M10|M12|M16", scale=True),
            _r("length", M_LEN, "x"),
            _r("spec", "12.9 BLKOX|12.9 ZP|A2-70 SS|A4-80 SS|10.9 ZP"),
        ),
        0.12,
        1.0,
        packs=(50, 100),
        scale_step=0.35,
    ),
    Template(
        "L02.01",
        "carriage_i",
        ("CARRIAGE", "BOLT"),
        (
            _r("thread", "1/4-20|5/16-18|3/8-16|1/2-13|5/8-11", scale=True),
            _r("length", I_LEN, "x"),
            _r("spec", "GR2 ZP|GR2 HDG|GR5 ZP|18-8 SS"),
        ),
        0.18,
        0.5,
        packs=(50, 100),
    ),
    Template(
        "L02.02",
        "hex_nut_m",
        ("HEX", "NUT"),
        (
            _r("thread", "M4|M5|M6|M8|M10|M12|M14|M16|M18|M20|M22|M24|M27|M30", scale=True),
            _r("pitch", "COARSE|FINE"),
            _r("spec", "CL8 ZP|CL8 HDG|CL10 ZP|CL10 PLAIN|A2 SS|A4 SS|CL8 YZN"),
        ),
        0.05,
        1.2,
        packs=(100, 200, 500),
        scale_step=0.3,
    ),
    Template(
        "L02.02",
        "nylock_i",
        ("NYLON", "INSERT", "LOCK", "NUT"),
        (
            _r("thread", I_THREAD, scale=True),
            _r("spec", "GR5 ZP|GR8 YZN|GR2 ZP|18-8 SS|316 SS|GR5 PLAIN"),
        ),
        0.07,
        0.8,
        packs=(100, 250),
        scale_step=0.3,
    ),
    Template(
        "L02.02",
        "flat_washer",
        ("FLAT", "WASHER"),
        (
            _r(
                "size",
                "M4|M5|M6|M8|M10|M12|M14|M16|M20|M24|1/4|5/16|3/8|7/16|1/2|5/8|3/4|7/8|1",
                scale=True,
            ),
            _r("type", "SAE|USS|DIN 125|DIN 9021|F436"),
            _r("spec", "ZP|HDG|SS|PLAIN|YZN"),
        ),
        0.03,
        1.0,
        packs=(100, 500, 1000),
        scale_step=0.2,
    ),
    Template(
        "L02.03",
        "wedge_anchor",
        ("WEDGE", "ANCHOR"),
        (
            _r("dia", "1/4|3/8|1/2|5/8|3/4|1", scale=True),
            _r("length", "1-3/4|2-1/4|2-3/4|3|3-1/2|3-3/4|4|4-1/4|5|5-1/2|6|7|8|10", "x"),
            _r("spec", "ZP|HDG|304 SS|316 SS|YZN"),
        ),
        0.65,
        packs=(25, 50),
        scale_step=0.5,
    ),
    Template(
        "L02.03",
        "sleeve_anchor",
        ("SLEEVE", "ANCHOR"),
        (
            _r("dia", "M6|M8|M10|M12|M16|1/4|3/8|1/2", scale=True),
            _r("length", "40|50|60|65|75|80|100|120|150", "x"),
            _r("spec", "ZP|304 SS|HDG|YZN"),
        ),
        0.55,
        packs=(25, 50, 100),
        scale_step=0.5,
    ),
    Template(
        "L02.04",
        "blind_rivet",
        ("BLIND", "RIVET"),
        (
            _r("dia", "3/32|1/8|5/32|3/16|1/4", scale=True),
            _r(
                "grip",
                "0.020-0.125|0.126-0.250|0.251-0.375|0.376-0.500|0.501-0.625|0.626-0.750",
                "x",
            ),
            _r("spec", "AL/STL|AL/AL|SS/SS|STL/STL|CU/STL|AL/SS"),
            _r("head", "DOME HD|LG FLANGE|CSK HD"),
        ),
        0.04,
        packs=(250, 500, 1000),
        scale_step=0.3,
    ),
    Template(
        "L02.05",
        "threaded_rod",
        ("THREADED", "ROD"),
        (
            _r(
                "thread",
                "M6|M8|M10|M12|M16|M20|M24|1/4-20|5/16-18|3/8-16|1/2-13|5/8-11|3/4-10|1-8",
                scale=True,
            ),
            _r("spec", "B7|B7 HDG|GR2 ZP|304 SS|316 SS|B16|GR5 ZP|8.8 ZP"),
        ),
        4.5,
        scale_step=0.4,
    ),
    # ---- L03 bearings ------------------------------------------------------
    Template(
        "L03.01",
        "ball_bearing",
        ("BALL", "BEARING"),
        (_r("desig", _BALL, "desig", scale=True),),
        14.0,
        scale_step=0.002,
    ),
    Template(
        "L03.02",
        "roller_bearing",
        ("ROLLER", "BEARING"),
        (_r("desig", _ROLLER, "desig", scale=True),),
        95.0,
        scale_step=0.004,
    ),
    Template(
        "L03.03",
        "mounted_unit",
        ("MOUNTED", "BEARING", "UNIT"),
        (_r("desig", _MOUNTED, "desig", scale=True),),
        42.0,
        scale_step=0.004,
    ),
    Template(
        "L03.03",
        "bushing",
        ("SLEEVE", "BUSHING"),
        (
            _r(
                "desig",
                tuple(
                    f"{m}-{i:02d}{o:02d}-{w:02d}"
                    for m in ("BB", "SF", "FB")
                    for i in (4, 6, 8, 10, 12, 16, 20, 24)
                    for o in (6, 8, 10, 12, 14)
                    for w in (4, 8, 12, 16)
                    if o > i // 2
                ),
                "desig",
            ),
        ),
        6.5,
        weight=0.7,
        scale_step=0.0,
    ),
    Template(
        "L03.04",
        "v_belt",
        ("V-BELT",),
        (
            _r("section", "A|B|C|3V|5V|AX|BX|3VX|5VX"),
            _r("length", tuple(str(n) for n in range(26, 181, 2)), scale=True),
        ),
        18.0,
        scale_step=0.004,
    ),
    Template(
        "L03.04",
        "timing_belt",
        ("TIMING", "BELT"),
        (
            _r("pitch", "5M|8M|14M|3M|XL|L|H"),
            _r("length", tuple(str(n) for n in range(400, 3000, 40))),
            _r("width", "15MM|20MM|25MM|30MM|50MM|85MM"),
        ),
        45.0,
        scale_step=0.0,
    ),
    Template(
        "L03.05",
        "sprocket",
        ("SPROCKET",),
        (
            _r("chain", "#35|#40|#50|#60|#80|#100"),
            _r("teeth", tuple(f"{n}T" for n in range(9, 61))),
            _r(
                "bore",
                "1/2IN BORE|5/8IN BORE|3/4IN BORE|1IN BORE|1-1/4IN BORE|1-1/2IN BORE|QD BORE|TL BORE",
            ),
        ),
        38.0,
        scale_step=0.0,
    ),
    Template(
        "L03.05",
        "jaw_coupling",
        ("JAW", "COUPLING", "HUB"),
        (
            _r("size", "L050|L070|L075|L090|L095|L099|L100|L110|L150|L190|L225"),
            _r(
                "bore",
                "3/8IN|1/2IN|5/8IN|3/4IN|7/8IN|1IN|1-1/8IN|1-1/4IN|1-3/8IN|1-1/2IN|1-5/8IN|2IN|14MM|19MM|24MM|28MM|38MM",
            ),
            _r("key", "KW|NO KW"),
        ),
        24.0,
        scale_step=0.0,
    ),
    Template(
        "L03.05",
        "roller_chain",
        ("ROLLER", "CHAIN"),
        (
            _r("chain", "#25|#35|#40|#41|#50|#60|#80|#100|#120"),
            _r("strand", "SINGLE|DOUBLE|TRIPLE"),
            _r("length", "10FT|25FT|50FT|100FT"),
            _r("type", "RIVETED|COTTERED|NICKEL PLATED|SS"),
        ),
        70.0,
        scale_step=0.0,
    ),
    # ---- L04 pipe, valves, fittings ---------------------------------------
    Template(
        "L04.01",
        "pipe",
        ("PIPE",),
        (
            _r("size", NPS, "inch", scale=True),
            _r("sched", "SCH 10S|SCH 40|SCH 40S|SCH 80|SCH 80S|SCH 160|STD|XS"),
            _r("matl", "CS A106B|CS A53B|SS 304L|SS 316L|GALV A53|CPVC|PVC"),
            _r("end", "PE|BE|TBE|SMLS"),
        ),
        9.0,
        scale_step=0.35,
    ),
    Template(
        "L04.02",
        "ball_valve",
        ("BALL", "VALVE"),
        (
            _r("size", NPS, "inch", scale=True),
            _r("class", "150|300|600|800|1000|2000|3000", "class"),
            _r("matl", "SS 316|CS|BRASS|BRONZE|SS 304|CF8M|WCB"),
            _r("end", "NPT|SW|FLG RF|BW|TC"),
        ),
        55.0,
        1.5,
        scale_step=0.45,
    ),
    Template(
        "L04.02",
        "gate_valve",
        ("GATE", "VALVE"),
        (
            _r("size", NPS, "inch", scale=True),
            _r("class", "125|150|300|600|800|1500", "class"),
            _r("matl", "BRONZE|CS A216 WCB|SS CF8M|DI|FS A105"),
            _r("end", "NPT|FLG RF|SW|BW"),
        ),
        110.0,
        scale_step=0.45,
    ),
    Template(
        "L04.02",
        "check_valve",
        ("CHECK", "VALVE"),
        (
            _r("size", NPS, "inch", scale=True),
            _r("class", "125|150|200|300|600|800", "class"),
            _r("matl", "BRONZE|DI|SS 316|CS|PVC"),
            _r("end", "NPT|FLG RF|WAFER|SW"),
        ),
        75.0,
        scale_step=0.45,
    ),
    Template(
        "L04.02",
        "butterfly_valve",
        ("BUTTERFLY", "VALVE"),
        (
            _r("size", "2|2-1/2|3|4|5|6|8|10|12|14|16", "inch", scale=True),
            _r("class", "150|200|285", "class"),
            _r("matl", "DI EPDM|DI BUNA|CS PTFE|SS 316 PTFE|DI VITON"),
            _r("end", "WAFER|LUG|FLG"),
        ),
        160.0,
        scale_step=0.35,
    ),
    Template(
        "L04.03",
        "elbow",
        ("90", "ELBOW"),
        (
            _r("size", NPS, "inch", scale=True),
            _r("class", "150|300|2000|3000|6000", "class"),
            _r("matl", "FS A105|SS 316|MI GALV|MI BLK|BRASS|CS A234 WPB"),
            _r("end", "NPT|SW|BW"),
        ),
        6.0,
        1.2,
        scale_step=0.45,
    ),
    Template(
        "L04.03",
        "tee",
        ("TEE",),
        (
            _r("size", NPS, "inch", scale=True),
            _r("class", "150|300|2000|3000|6000", "class"),
            _r("matl", "FS A105|SS 316|MI GALV|MI BLK|BRASS|SS 304"),
            _r("end", "NPT|SW|BW"),
        ),
        8.0,
        scale_step=0.45,
    ),
    Template(
        "L04.03",
        "weld_neck_flange",
        ("WELD", "NECK", "FLANGE"),
        (
            _r("size", NPS, "inch", scale=True),
            _r("class", "150|300|600|900", "class"),
            _r("matl", "A105|SS 316L|SS 304L|A350 LF2"),
            _r("end", "RF SCH 40|RF SCH 80|RTJ SCH 80|FF SCH 40"),
        ),
        38.0,
        scale_step=0.45,
    ),
    Template(
        "L04.03",
        "coupling",
        ("COUPLING",),
        (
            _r("size", NPS, "inch", scale=True),
            _r("class", "150|2000|3000|6000", "class"),
            _r("matl", "FS A105|SS 316|MI GALV|BRASS|SS 304"),
            _r("end", "NPT|SW"),
        ),
        5.0,
        scale_step=0.45,
    ),
    Template(
        "L04.04",
        "hyd_hose",
        ("HYDRAULIC", "HOSE"),
        (
            _r(
                "dash",
                "-4 1/4IN|-6 3/8IN|-8 1/2IN|-10 5/8IN|-12 3/4IN|-16 1IN|-20 1-1/4IN",
                scale=True,
            ),
            _r("spec", "100R1AT|100R2AT|100R12|100R13|100R17|4SH"),
            _r("psi", "1500PSI|2250PSI|3000PSI|4000PSI|5000PSI|6000PSI"),
        ),
        9.5,
        scale_step=0.3,
    ),
    Template(
        "L04.04",
        "air_hose",
        ("AIR", "HOSE"),
        (
            _r("id", "1/4IN ID|3/8IN ID|1/2IN ID|3/4IN ID|1IN ID", scale=True),
            _r("psi", "200PSI|250PSI|300PSI"),
            _r("matl", "RUBBER|PVC|HYBRID|POLYURETHANE|NYLON"),
        ),
        2.4,
        scale_step=0.3,
    ),
    Template(
        "L04.05",
        "o_ring",
        ("O-RING",),
        (
            _r(
                "dash",
                tuple(
                    f"AS568-{n:03d}"
                    for n in list(range(4, 50))
                    + list(range(104, 179))
                    + list(range(201, 284))
                    + list(range(325, 395))
                ),
            ),
            _r("matl", "VITON 75|BUNA-N 70|EPDM 70|SILICONE 70|BUNA-N 90|VITON 90|PTFE|FKM 75"),
        ),
        0.35,
        1.3,
        packs=(25, 50, 100),
        scale_step=0.0,
    ),
    Template(
        "L04.05",
        "spiral_gasket",
        ("SPIRAL", "WOUND", "GASKET"),
        (
            _r("size", "1/2IN|3/4IN|1IN|1-1/2IN|2IN|3IN|4IN|6IN|8IN|10IN|12IN", scale=True),
            _r("class", "150#|300#|600#|900#|1500#"),
            _r("matl", "316/GRAPHITE|304/GRAPHITE|316/PTFE|INCONEL/GRAPHITE"),
            _r("ring", "CS INNER|316 INNER|NO INNER"),
        ),
        14.0,
        scale_step=0.3,
    ),
    # ---- L05 electrical ----------------------------------------------------
    Template(
        "L05.01",
        "thhn_wire",
        ("WIRE", "THHN"),
        (
            _r(
                "gauge",
                "14AWG|12AWG|10AWG|8AWG|6AWG|4AWG|3AWG|2AWG|1AWG|1/0AWG|2/0AWG|4/0AWG",
                scale=True,
            ),
            _r("strand", "STRANDED|SOLID"),
            _r("color", "BLACK|WHITE|RED|BLUE|GREEN|YELLOW|ORANGE|BROWN|GRAY"),
            _r("voltage", "600V"),
        ),
        1.1,
        scale_step=0.45,
    ),
    Template(
        "L05.01",
        "cord",
        ("PORTABLE", "CORD"),
        (
            _r("type", "SOOW|SJOOW|SEOOW|STOOW"),
            _r("gauge", "18/2|18/3|16/3|16/4|14/3|14/4|12/3|12/4|10/3|10/4|8/4|6/4", scale=True),
            _r("voltage", "600V|300V"),
        ),
        2.6,
        scale_step=0.25,
    ),
    Template(
        "L05.02",
        "breaker",
        ("CIRCUIT", "BREAKER"),
        (
            _r("poles", "1|2|3", "poles"),
            _r(
                "current",
                "15A|20A|30A|40A|50A|60A|70A|100A|125A|150A|200A|225A|250A|400A",
                scale=True,
            ),
            _r("voltage", "120/240V|240V|277/480V|480V|600V"),
            _r("rating", "10KA|14KA|18KA|22KA|35KA|65KA"),
        ),
        110.0,
        scale_step=0.25,
    ),
    Template(
        "L05.02",
        "fuse",
        ("FUSE",),
        (
            _r("class", "CLASS J|CLASS RK5|CLASS RK1|CLASS CC|CLASS T|CLASS L"),
            _r("current", "1A|3A|6A|10A|15A|20A|25A|30A|40A|60A|100A|200A|400A", scale=True),
            _r("voltage", "250V|600V"),
            _r("speed", "TIME DELAY|FAST ACTING"),
        ),
        18.0,
        packs=(10,),
        scale_step=0.15,
    ),
    Template(
        "L05.02",
        "disconnect",
        ("DISCONNECT", "SWITCH"),
        (
            _r("current", "30A|60A|100A|200A|400A|600A", scale=True),
            _r("poles", "3|2", "poles"),
            _r("voltage", "240V|600V"),
            _r("encl", "NEMA 1|NEMA 3R|NEMA 4X|NEMA 12"),
            _r("fused", "FUSED|NON-FUSED"),
        ),
        340.0,
        scale_step=0.4,
    ),
    Template(
        "L05.03",
        "motor",
        ("MOTOR",),
        (
            _r(
                "hp",
                "1HP|1-1/2HP|2HP|3HP|5HP|7-1/2HP|10HP|15HP|20HP|25HP|30HP|40HP|50HP|75HP|100HP",
                scale=True,
            ),
            _r("rpm", "1200RPM|1800RPM|3600RPM"),
            _r("voltage", "208-230/460V|460V|575V|230/460V"),
            _r("encl", "TEFC|ODP|TENV|XP"),
            _r("frame", "143T|145T|182T|184T|213T|215T|254T|256T|284T|286T|324T|326T|364T|405T"),
        ),
        900.0,
        1.4,
        scale_step=0.3,
    ),
    Template(
        "L05.03",
        "vfd",
        ("AC", "DRIVE", "VFD"),
        (
            _r("hp", "1HP|2HP|3HP|5HP|7-1/2HP|10HP|15HP|20HP|25HP|30HP|40HP|50HP", scale=True),
            _r("voltage", "230V|480V|600V"),
            _r("current", "4.8A|7.6A|11A|14A|21A|27A|34A|40A|52A|65A"),
            _r("encl", "NEMA 1|NEMA 4X|IP20|IP66|NEMA 12"),
        ),
        1300.0,
        scale_step=0.3,
    ),
    Template(
        "L05.04",
        "contactor",
        ("CONTACTOR",),
        (
            _r("current", "9A|12A|18A|25A|32A|40A|50A|65A|80A|95A", scale=True),
            _r("poles", "3|4", "poles"),
            _r("coil", "24VDC|24VAC|120VAC|208VAC|240VAC|480VAC"),
            _r("aux", "1NO|1NC|1NO1NC|NO AUX"),
        ),
        75.0,
        scale_step=0.25,
    ),
    Template(
        "L05.04",
        "relay",
        ("RELAY", "PLUG-IN"),
        (
            _r("contacts", "SPDT|DPDT|3PDT|4PDT"),
            _r("coil", "12VDC|24VDC|24VAC|120VAC|240VAC"),
            _r("current", "5A|7A|10A|12A|15A"),
            _r("pins", "8 PIN|11 PIN|14 PIN|BLADE"),
        ),
        14.0,
        packs=(10,),
        scale_step=0.0,
    ),
    Template(
        "L05.04",
        "pushbutton",
        ("PUSHBUTTON", "22MM"),
        (
            _r("color", "RED|GREEN|BLACK|YELLOW|BLUE|WHITE"),
            _r("operator", "FLUSH|EXTENDED|MUSHROOM|ILLUMINATED|MAINTAINED"),
            _r("contacts", "1NO|1NC|1NO1NC|2NO|2NC"),
            _r("encl", "NEMA 4|NEMA 4X|NEMA 13|IP66"),
        ),
        22.0,
        scale_step=0.0,
    ),
    Template(
        "L05.05",
        "prox_sensor",
        ("PROXIMITY", "SENSOR", "INDUCTIVE"),
        (
            _r("barrel", "M8|M12|M18|M30"),
            _r("output", "PNP NO|NPN NO|PNP NC|NPN NC|PNP NO/NC"),
            _r("range", "1.5MM|2MM|4MM|5MM|8MM|10MM|15MM|20MM"),
            _r("supply", "10-30VDC|20-250VAC"),
            _r("conn", "M12 QD|2M CABLE|5M CABLE|M8 QD"),
        ),
        48.0,
        scale_step=0.0,
    ),
    Template(
        "L05.05",
        "thermocouple",
        ("THERMOCOUPLE",),
        (
            _r("type", "TYPE K|TYPE J|TYPE T|TYPE E"),
            _r("length", "2IN|3IN|4IN|6IN|8IN|10IN|12IN|18IN|24IN"),
            _r("sheath", "1/8IN OD|3/16IN OD|1/4IN OD|6MM OD"),
            _r("fitting", "1/4NPT|1/2NPT|NO FITTING"),
        ),
        36.0,
        scale_step=0.0,
    ),
    # ---- L06 abrasives and cutting tools -----------------------------------
    Template(
        "L06.01",
        "cutoff_wheel",
        ("CUTOFF", "WHEEL"),
        (
            _r("dia", "3|4|4-1/2|5|6|7|9|12|14", "inch", scale=True),
            _r("thk", "0.035|0.040|0.045|1/16|3/32|1/8|5/32", "x"),
            _r("bore", "3/8|5/8|7/8|1|5/8-11", "x"),
            _r("grit", "A36|A46|A60|ZA36|ZA60|A24|A30|CER60"),
            _r("type", "T1|T27|T41"),
        ),
        3.2,
        1.2,
        packs=(10, 25, 50),
        scale_step=0.25,
    ),
    Template(
        "L06.01",
        "flap_disc",
        ("FLAP", "DISC"),
        (
            _r("dia", "4|4-1/2|5|7", "inch", scale=True),
            _r("bore", "7/8|5/8-11", "x"),
            _r("grit", "40 GRIT|60 GRIT|80 GRIT|120 GRIT|36 GRIT"),
            _r("type", "T27|T29"),
            _r("grain", "ZIRC|CERAMIC|AO"),
        ),
        5.5,
        packs=(10,),
        scale_step=0.2,
    ),
    Template(
        "L06.02",
        "sanding_disc",
        ("SANDING", "DISC"),
        (
            _r("dia", "2|3|4-1/2|5|6|7", "inch", scale=True),
            _r(
                "grit",
                "36 GRIT|40 GRIT|50 GRIT|60 GRIT|80 GRIT|100 GRIT|120 GRIT|150 GRIT|180 GRIT|220 GRIT|320 GRIT|400 GRIT",
            ),
            _r("attach", "HOOK LOOP|PSA|ROLOC"),
            _r("holes", "NO HOLE|5 HOLE|8 HOLE|6 HOLE"),
        ),
        0.55,
        packs=(25, 50, 100),
        scale_step=0.2,
    ),
    Template(
        "L06.02",
        "sanding_belt",
        ("SANDING", "BELT"),
        (
            _r("size", "1X30|1X42|2X48|2X72|3X21|4X36|6X48|1/2X18", scale=True),
            _r("grit", "36 GRIT|40 GRIT|60 GRIT|80 GRIT|120 GRIT|180 GRIT"),
            _r("grain", "ZIRC|CERAMIC|AO|SC"),
        ),
        2.2,
        packs=(10, 20),
        scale_step=0.2,
    ),
    Template(
        "L06.03",
        "jobber_drill",
        ("DRILL", "BIT", "JOBBER"),
        (
            _r(
                "dia",
                (
                    "1/16",
                    "5/64",
                    "3/32",
                    "7/64",
                    "1/8",
                    "9/64",
                    "5/32",
                    "11/64",
                    "3/16",
                    "13/64",
                    "7/32",
                    "15/64",
                    "1/4",
                    "17/64",
                    "9/32",
                    "5/16",
                    "11/32",
                    "3/8",
                    "13/32",
                    "7/16",
                    "1/2",
                    "3MM",
                    "3.3MM",
                    "4MM",
                    "4.2MM",
                    "5MM",
                    "5.5MM",
                    "6MM",
                    "6.8MM",
                    "8MM",
                    "8.5MM",
                    "10MM",
                    "10.2MM",
                    "12MM",
                ),
                scale=True,
            ),
            _r("matl", "HSS|COBALT M42|HSS TIN|CARBIDE|HSS BLKOX|COBALT M35"),
            _r("point", "118 DEG|135 DEG SPLIT|140 DEG"),
        ),
        3.4,
        1.5,
        packs=(6, 12),
        scale_step=0.04,
    ),
    Template(
        "L06.03",
        "tap",
        ("TAP",),
        (
            _r(
                "thread",
                (
                    "#4-40",
                    "#6-32",
                    "#8-32",
                    "#10-24",
                    "#10-32",
                    "1/4-20",
                    "1/4-28",
                    "5/16-18",
                    "3/8-16",
                    "3/8-24",
                    "1/2-13",
                    "M3X0.5",
                    "M4X0.7",
                    "M5X0.8",
                    "M6X1.0",
                    "M8X1.25",
                    "M10X1.5",
                    "M12X1.75",
                ),
                scale=True,
            ),
            _r("type", "SPIRAL POINT|SPIRAL FLUTE|HAND PLUG|HAND BOTTOM|FORMING"),
            _r("matl", "HSS|HSS-E|HSS TIN|COBALT|POWDERED METAL"),
        ),
        14.0,
        scale_step=0.06,
    ),
    Template(
        "L06.04",
        "end_mill",
        ("END", "MILL"),
        (
            _r(
                "dia",
                "1/8|3/16|1/4|5/16|3/8|1/2|5/8|3/4|1|3MM|4MM|6MM|8MM|10MM|12MM|16MM|20MM",
                scale=True,
            ),
            _r("flutes", "2FL|3FL|4FL|5FL|6FL"),
            _r("matl", "CARBIDE|HSS|COBALT"),
            _r("coat", "TIALN|ALTIN|UNCOATED|TICN|ZRN"),
            _r("end", "SQUARE|BALL|0.030R|0.060R"),
        ),
        42.0,
        scale_step=0.15,
    ),
    Template(
        "L06.04",
        "insert",
        ("TURNING", "INSERT"),
        (
            _r(
                "iso",
                "CNMG 120404|CNMG 120408|CNMG 120412|WNMG 080404|WNMG 080408|DNMG 150604|DNMG 150608|TNMG 160404|TNMG 160408|VNMG 160404|VCMT 160404|CCMT 09T304|CCMT 09T308|DCMT 11T304|DCMT 11T308|SNMG 120408|APMT 1135|APMT 1604",
            ),
            _r("grade", "P15|P25|P35|M15|M25|M35|K10|K20|N10"),
            _r("chip", "-MF|-MM|-MR|-PF|-PM|-PR|-NF"),
        ),
        9.5,
        1.3,
        packs=(10,),
        scale_step=0.0,
    ),
    Template(
        "L06.05",
        "bandsaw_blade",
        ("BANDSAW", "BLADE", "BI-METAL"),
        (
            _r("length", "93-1/2IN|111IN|132IN|142IN|150IN|164IN|176IN|196IN|260IN"),
            _r("width", "1/2|3/4|1|1-1/4|1-1/2|2", "inch", scale=True),
            _r("tpi", "2/3 TPI|3/4 TPI|4/6 TPI|5/8 TPI|6/10 TPI|8/12 TPI|10/14 TPI|14/18 TPI"),
        ),
        48.0,
        scale_step=0.2,
    ),
    Template(
        "L06.05",
        "hole_saw",
        ("HOLE", "SAW", "BI-METAL"),
        (
            _r(
                "dia",
                (
                    "3/4",
                    "7/8",
                    "1",
                    "1-1/8",
                    "1-1/4",
                    "1-3/8",
                    "1-1/2",
                    "1-3/4",
                    "2",
                    "2-1/4",
                    "2-1/2",
                    "3",
                    "3-1/2",
                    "4",
                    "4-1/2",
                    "5",
                    "6",
                ),
                "inch",
                scale=True,
            ),
            _r("depth", "1-1/2IN DEEP|2IN DEEP|1-7/8IN DEEP"),
            _r("tpi", "4/6 TPI|5/8 TPI|3/4 TPI"),
        ),
        11.0,
        scale_step=0.08,
    ),
    # ---- L07 safety and PPE ------------------------------------------------
    Template(
        "L07.01",
        "nitrile_glove",
        ("GLOVE", "NITRILE", "DISPOSABLE"),
        (
            _r("thk", "3MIL|4MIL|5MIL|6MIL|8MIL|9MIL"),
            _r("color", "BLUE|BLACK|ORANGE|PURPLE"),
            _r("size", GLOVE_SIZE, "size"),
            _r("finish", "POWDER FREE|TEXTURED"),
        ),
        0.09,
        1.5,
        packs=(100, 50, 1000),
        scale_step=0.0,
    ),
    Template(
        "L07.01",
        "cut_glove",
        ("GLOVE", "CUT", "RESISTANT"),
        (
            _r("level", "A2|A3|A4|A5|A6|A7|A9"),
            _r("coat", "PU PALM|NITRILE PALM|LATEX CRINKLE|FOAM NITRILE|UNCOATED"),
            _r("gauge", "13GA|15GA|18GA|21GA"),
            _r("size", GLOVE_SIZE, "size"),
        ),
        6.5,
        scale_step=0.0,
    ),
    Template(
        "L07.01",
        "leather_glove",
        ("GLOVE", "LEATHER", "DRIVER"),
        (
            _r("matl", "COWHIDE|GOATSKIN|PIGSKIN|DEERSKIN"),
            _r("grade", "GRAIN|SPLIT|PREMIUM GRAIN"),
            _r("lining", "UNLINED|THINSULATE LINED|FLEECE LINED|KEVLAR SEWN"),
            _r("size", GLOVE_SIZE, "size"),
        ),
        7.8,
        scale_step=0.0,
    ),
    Template(
        "L07.02",
        "safety_glasses",
        ("SAFETY", "GLASSES"),
        (
            _r("lens", "CLEAR|GRAY|AMBER|INDOOR/OUTDOOR|BLUE MIRROR|SHADE 3|SHADE 5"),
            _r("coat", "ANTI-FOG|HARD COAT|ANTI-FOG/ANTI-SCRATCH|UNCOATED"),
            _r("frame", "BLACK FRAME|BLUE FRAME|FRAMELESS|GRAY FRAME|CLEAR FRAME|OTG"),
            _r("std", "Z87+|Z87+ U6"),
        ),
        3.8,
        packs=(12,),
        scale_step=0.0,
    ),
    Template(
        "L07.02",
        "face_shield",
        ("FACE", "SHIELD"),
        (
            _r("size", "8X12IN|8X15.5IN|9X16IN|9X18IN"),
            _r("matl", "PC CLEAR|PETG CLEAR|PC GREEN SHADE 5|ACETATE"),
            _r("thk", "0.040IN|0.060IN|0.080IN"),
        ),
        9.0,
        scale_step=0.0,
    ),
    Template(
        "L07.03",
        "earplug",
        ("EARPLUG", "FOAM"),
        (
            _r("nrr", "NRR 29|NRR 30|NRR 31|NRR 32|NRR 33"),
            _r("cord", "CORDED|UNCORDED|DETECTABLE CORDED|BANDED"),
            _r("color", "ORANGE|YELLOW|GREEN|BLUE|PINK"),
            _r("size", "M|L|S", "size"),
        ),
        0.22,
        packs=(200, 100, 500),
        scale_step=0.0,
    ),
    Template(
        "L07.03",
        "respirator",
        ("RESPIRATOR", "HALF", "MASK"),
        (
            _r(
                "type",
                "REUSABLE|N95 DISPOSABLE|N95 VALVED|P100 DISPOSABLE|R95 DISPOSABLE|N99 VALVED",
            ),
            _r("matl", "SILICONE|ELASTOMER|TPE|NONWOVEN"),
            _r("size", "S|M|L", "size"),
        ),
        4.5,
        packs=(10, 20),
        scale_step=0.0,
    ),
    Template(
        "L07.04",
        "coverall",
        ("COVERALL", "DISPOSABLE"),
        (
            _r("matl", "SMS|MICROPOROUS|POLYPROPYLENE|SPP 40GSM|FR TREATED"),
            _r("style", "HOOD BOOTS|HOOD|COLLAR|HOOD ELASTIC WRIST"),
            _r("size", "M|L|XL|2XL|3XL", "size"),
        ),
        6.0,
        packs=(25,),
        scale_step=0.0,
    ),
    Template(
        "L07.04",
        "safety_boot",
        ("SAFETY", "BOOT"),
        (
            _r("toe", "STEEL TOE|COMPOSITE TOE|ALLOY TOE"),
            _r("height", "6IN|8IN|10IN|WELLINGTON"),
            _r("feature", "EH WP|MET GUARD|PR EH|SLIP RESISTANT|INSULATED WP"),
            _r(
                "size",
                tuple(
                    f"{s}{w}"
                    for s in ("7", "8", "8.5", "9", "9.5", "10", "10.5", "11", "12", "13")
                    for w in ("M", "W")
                ),
                "size",
            ),
        ),
        95.0,
        scale_step=0.0,
    ),
    Template(
        "L07.05",
        "harness",
        ("HARNESS", "FULL", "BODY"),
        (
            _r("points", "3-POINT|5-POINT|4-POINT"),
            _r("legs", "PASS-THRU LEGS|TONGUE LEGS|QUICK CONNECT LEGS"),
            _r("rating", "310LB|420LB|400LB"),
            _r("size", "S/M|M/L|L/XL|2XL|UNIVERSAL"),
        ),
        85.0,
        scale_step=0.0,
    ),
    Template(
        "L07.05",
        "lanyard",
        ("LANYARD", "SHOCK", "ABSORBING"),
        (
            _r("length", "4FT|6FT|8FT|10FT"),
            _r("legs", "SINGLE LEG|TWIN LEG"),
            _r("hook", "SNAP HOOK|REBAR HOOK|CARABINER"),
            _r("rating", "310LB|420LB"),
        ),
        55.0,
        scale_step=0.0,
    ),
    Template(
        "L07.05",
        "first_aid",
        ("FIRST", "AID", "KIT"),
        (
            _r("persons", "10 PERSON|25 PERSON|50 PERSON|75 PERSON|100 PERSON"),
            _r("case", "METAL CASE|PLASTIC CASE|SOFT BAG|WALL CABINET"),
            _r("class", "ANSI CLASS A|ANSI CLASS B"),
        ),
        45.0,
        scale_step=0.0,
    ),
    # ---- L08 packaging ----------------------------------------------------
    Template(
        "L08.01",
        "rsc_box",
        ("CORRUGATED", "BOX", "RSC"),
        (
            _r(
                "dims",
                tuple(
                    f"{a}X{b}X{c}"
                    for a in (6, 8, 10, 12, 14, 16, 18, 20, 24)
                    for b in (4, 6, 8, 10, 12, 16)
                    for c in (4, 6, 8, 10, 12)
                    if b <= a
                ),
                scale=True,
            ),
            _r("test", "32ECT|44ECT|200#|275#|48ECT DW"),
            _r("color", "KRAFT|WHITE"),
        ),
        0.95,
        1.4,
        packs=(25, 50),
        scale_step=0.003,
    ),
    Template(
        "L08.02",
        "pallet",
        ("PALLET", "WOOD"),
        (
            _r("dims", "48X40|48X48|42X42|48X42|40X40|36X36|48X45|44X44|60X48"),
            _r("entry", "2-WAY|4-WAY|PARTIAL 4-WAY"),
            _r("grade", "GRADE A|GRADE B|NEW|HT ISPM15|COMBO"),
            _r("deck", "5 DECK BOARD|7 DECK BOARD|9 DECK BOARD"),
        ),
        14.0,
        scale_step=0.0,
    ),
    Template(
        "L08.03",
        "stretch_film",
        ("STRETCH", "FILM"),
        (
            _r("width", "12IN|15IN|18IN|20IN|30IN"),
            _r("length", "1000FT|1500FT|2000FT|5000FT|6000FT"),
            _r("gauge", "47GA|60GA|70GA|80GA|90GA|120GA"),
            _r("type", "CAST|BLOWN|PRE-STRETCHED"),
        ),
        22.0,
        packs=(4,),
        scale_step=0.0,
    ),
    Template(
        "L08.03",
        "packing_tape",
        ("PACKING", "TAPE"),
        (
            _r("width", "1.88IN|2IN|2.83IN|3IN|48MM|72MM"),
            _r("length", "55YD|60YD|100YD|110YD|1000YD"),
            _r("thk", "1.6MIL|1.8MIL|2.0MIL|2.5MIL|3.0MIL"),
            _r("color", "CLEAR|TAN|BROWN"),
        ),
        2.1,
        packs=(36, 6),
        scale_step=0.0,
    ),
    Template(
        "L08.04",
        "thermal_label",
        ("LABEL", "THERMAL", "TRANSFER"),
        (
            _r("size", "2X1|3X1|3X2|4X2|4X3|4X4|4X6|4X8|6X4"),
            _r("core", "1IN CORE|3IN CORE"),
            _r("count", "500 LBL/RL|1000 LBL/RL|2000 LBL/RL|250 LBL/RL"),
            _r("perf", "PERF|NON-PERF"),
        ),
        9.5,
        scale_step=0.0,
    ),
    Template(
        "L08.05",
        "bubble_roll",
        ("BUBBLE", "ROLL"),
        (
            _r("width", "12IN|24IN|48IN"),
            _r("length", "125FT|175FT|250FT|500FT|750FT"),
            _r("bubble", "3/16IN|5/16IN|1/2IN"),
            _r("perf", "PERF 12IN|NON-PERF|ANTI-STATIC"),
        ),
        32.0,
        scale_step=0.0,
    ),
    Template(
        "L08.05",
        "foam_sheet",
        ("FOAM", "SHEET", "PE"),
        (
            _r("thk", "1/8IN|1/4IN|1/2IN|1IN|2IN"),
            _r("size", "24X48|48X96|12X12|24X24|36X48"),
            _r("density", "1.7LB|2.2LB|4LB|6LB"),
        ),
        6.0,
        scale_step=0.0,
    ),
    # ---- L09 chemicals (volume) -------------------------------------------
    Template(
        "L09.01",
        "hyd_oil",
        ("HYDRAULIC", "OIL"),
        (
            _r("grade", "AW 32|AW 46|AW 68|AW 100|HVI 32|HVI 46|FR 46|BIO 46"),
            _r("base", "MINERAL|SYNTHETIC|SEMI-SYNTHETIC"),
        ),
        4.2,
        1.3,
        scale_step=0.0,
    ),
    Template(
        "L09.01",
        "gear_oil",
        ("GEAR", "OIL"),
        (
            _r("grade", "ISO 68|ISO 100|ISO 150|ISO 220|ISO 320|ISO 460|ISO 680"),
            _r("type", "EP MINERAL|PAO SYNTHETIC|PAG SYNTHETIC|FOOD GRADE H1"),
        ),
        6.5,
        scale_step=0.0,
    ),
    Template(
        "L09.01",
        "grease",
        ("GREASE",),
        (
            _r("type", "LITHIUM COMPLEX|LITHIUM|CALCIUM SULFONATE|POLYUREA|ALUMINUM COMPLEX|MOLY"),
            _r("nlgi", "NLGI 0|NLGI 1|NLGI 2|NLGI 3|NLGI 00"),
            _r("ep", "EP|NON-EP|FOOD GRADE H1"),
        ),
        8.0,
        scale_step=0.0,
    ),
    Template(
        "L09.02",
        "coolant",
        ("COOLANT",),
        (
            _r("type", "SOLUBLE OIL|SEMI-SYNTHETIC|SYNTHETIC|STRAIGHT OIL|MICRO-EMULSION"),
            _r("conc", "CONC 5%|CONC 8%|CONC 10%|CONC 100%|RTU 3%"),
            _r("feature", "CHLORINE FREE|BORON FREE|LOW FOAM|AMINE FREE"),
        ),
        9.0,
        scale_step=0.0,
    ),
    Template(
        "L09.03",
        "solvent",
        ("SOLVENT",),
        (
            _r(
                "type",
                "ISOPROPYL ALCOHOL|ACETONE|MINERAL SPIRITS|MEK|TOLUENE|DENATURED ALCOHOL|CITRUS DEGREASER|PARTS WASHER",
            ),
            _r("purity", "99%|91%|70%|TECH GRADE|USP|ACS"),
            _r("flash", "FP 12C|FP 40C|FP 60C|NON-FLAM"),
        ),
        5.5,
        scale_step=0.0,
    ),
    Template(
        "L09.04",
        "adhesive",
        ("ADHESIVE",),
        (
            _r(
                "type",
                "EPOXY 2-PART|CYANOACRYLATE|THREADLOCKER|RTV SILICONE|POLYURETHANE|METHACRYLATE|HOT MELT",
            ),
            _r("strength", "LOW STRENGTH|MEDIUM STRENGTH|HIGH STRENGTH|FLEXIBLE"),
            _r("cure", "5 MIN|10 MIN|30 MIN|24 HR|UV CURE"),
            _r("color", "BLUE|RED|CLEAR|GRAY|BLACK|WHITE"),
        ),
        85.0,
        scale_step=0.0,
    ),
    Template(
        "L09.05",
        "paint",
        ("PAINT", "ENAMEL"),
        (
            _r(
                "color",
                "SAFETY YELLOW|SAFETY RED|OSHA GREEN|GLOSS BLACK|GLOSS WHITE|MACHINERY GRAY|ASA 61 GRAY|SAFETY BLUE|ORANGE",
            ),
            _r("type", "ALKYD|ACRYLIC|EPOXY|URETHANE|ZINC RICH 90%"),
            _r("voc", "VOC 100G/L|VOC 250G/L|VOC 340G/L|VOC 420G/L"),
        ),
        16.0,
        scale_step=0.0,
    ),
    # ---- L10 MRO general ---------------------------------------------------
    Template(
        "L10.01",
        "socket",
        ("SOCKET",),
        (
            _r("drive", "1/4DR|3/8DR|1/2DR|3/4DR|1DR"),
            _r(
                "size",
                "8MM|10MM|12MM|13MM|14MM|17MM|19MM|22MM|24MM|27MM|30MM|7/16IN|1/2IN|9/16IN|5/8IN|3/4IN|7/8IN|15/16IN|1IN|1-1/8IN|1-1/4IN",
            ),
            _r("point", "6PT|12PT"),
            _r("type", "STANDARD|DEEP|IMPACT|IMPACT DEEP"),
        ),
        9.0,
        scale_step=0.0,
    ),
    Template(
        "L10.01",
        "wrench",
        ("WRENCH", "COMBINATION"),
        (
            _r(
                "size",
                "8MM|10MM|11MM|12MM|13MM|14MM|15MM|16MM|17MM|18MM|19MM|21MM|22MM|24MM|1/4IN|5/16IN|3/8IN|7/16IN|1/2IN|9/16IN|5/8IN|11/16IN|3/4IN|13/16IN|7/8IN|15/16IN|1IN",
            ),
            _r("point", "12PT|6PT"),
            _r("finish", "FULL POLISH|SATIN|BLACK"),
        ),
        14.0,
        scale_step=0.0,
    ),
    Template(
        "L10.01",
        "cordless_tool",
        ("CORDLESS",),
        (
            _r(
                "tool",
                "IMPACT DRIVER|DRILL DRIVER|HAMMER DRILL|ANGLE GRINDER|RECIP SAW|IMPACT WRENCH|BAND SAW",
            ),
            _r("voltage", "12V|18V|20V|36V|60V"),
            _r("chuck", "1/4 HEX|1/2 CHUCK|3/8 SQ|1/2 SQ|4-1/2IN|5IN|NA"),
            _r("kit", "TOOL ONLY|KIT 2 BATT|KIT 1 BATT"),
        ),
        190.0,
        scale_step=0.0,
    ),
    Template(
        "L10.02",
        "electrode",
        ("ELECTRODE", "STICK"),
        (
            _r("aws", "E6010|E6011|E6013|E7018|E7018-1|E7024|E308L-16|E316L-16|E8018-B2"),
            _r("dia", "3/32IN|1/8IN|5/32IN|3/16IN|1/4IN"),
        ),
        6.5,
        scale_step=0.0,
    ),
    Template(
        "L10.02",
        "mig_wire",
        ("MIG", "WIRE"),
        (
            _r("aws", "ER70S-6|ER70S-3|ER308LSI|ER316LSI|ER4043|ER5356|E71T-1|E71T-11"),
            _r("dia", "0.023IN|0.030IN|0.035IN|0.045IN|0.052IN|1/16IN"),
            _r("spool", "2LB SPOOL|11LB SPOOL|33LB SPOOL|44LB SPOOL|500LB DRUM"),
        ),
        4.8,
        scale_step=0.0,
    ),
    Template(
        "L10.03",
        "trash_liner",
        ("TRASH", "LINER"),
        (
            _r("size", "24X33|30X37|33X40|38X58|40X46|43X47|60X60"),
            _r("thk", "0.7MIL|0.9MIL|1.1MIL|1.5MIL|2.0MIL|8MIC|13MIC|16MIC"),
            _r("color", "BLACK|CLEAR|WHITE|BLUE"),
        ),
        0.16,
        packs=(100, 250, 500),
        scale_step=0.0,
    ),
    Template(
        "L10.03",
        "paper_towel",
        ("PAPER", "TOWEL"),
        (
            _r("type", "HARDWOUND ROLL|C-FOLD|MULTIFOLD|CENTER PULL|KITCHEN ROLL"),
            _r("size", "8IN X 350FT|8IN X 600FT|8IN X 800FT|10IN X 800FT|7.5IN X 1000FT|10X12IN"),
            _r("ply", "1-PLY|2-PLY"),
            _r("color", "WHITE|NATURAL"),
        ),
        3.5,
        packs=(6, 12),
        scale_step=0.0,
    ),
    Template(
        "L10.04",
        "led_tube",
        ("LED", "TUBE"),
        (
            _r("type", "T8|T5|T5HO|T12"),
            _r("length", "2FT|3FT|4FT|8FT"),
            _r("watt", "9W|12W|14W|15W|18W|22W|36W"),
            _r("cct", "3500K|4000K|5000K|6500K"),
            _r("ballast", "TYPE A|TYPE B|TYPE A/B"),
        ),
        6.5,
        packs=(25, 10),
        scale_step=0.0,
    ),
    Template(
        "L10.04",
        "air_filter",
        ("AIR", "FILTER", "PLEATED"),
        (
            _r(
                "dims",
                "12X24X2|16X20X2|16X25X2|20X20X2|20X25X2|24X24X2|16X25X4|20X25X4|24X24X4|20X20X1|24X24X1|12X24X4",
            ),
            _r("merv", "MERV 8|MERV 11|MERV 13|MERV 14|MERV 7"),
            _r("frame", "BEVERAGE BOARD|METAL FRAME|HIGH CAPACITY"),
        ),
        7.5,
        packs=(12, 6, 24),
        scale_step=0.0,
    ),
    Template(
        "L10.04",
        "caster",
        ("CASTER",),
        (
            _r("type", "SWIVEL|RIGID|SWIVEL BRAKE|TOTAL LOCK"),
            _r("dia", "3IN|4IN|5IN|6IN|8IN|10IN"),
            _r("wheel", "POLYURETHANE|PHENOLIC|RUBBER|NYLON|CAST IRON"),
            _r("cap", "250LB|300LB|500LB|800LB|1200LB"),
        ),
        22.0,
        scale_step=0.0,
    ),
    Template(
        "L10.05",
        "caliper",
        ("CALIPER", "DIGITAL"),
        (
            _r("range", "0-4IN|0-6IN|0-8IN|0-12IN|0-150MM|0-200MM|0-300MM"),
            _r("res", "0.0005IN|0.001IN|0.01MM"),
            _r("ip", "IP54|IP67|NO RATING"),
        ),
        95.0,
        scale_step=0.0,
    ),
    Template(
        "L10.05",
        "pressure_gauge",
        ("PRESSURE", "GAUGE"),
        (
            _r("dial", "1-1/2IN|2IN|2-1/2IN|4IN|6IN"),
            _r(
                "range",
                "0-15PSI|0-30PSI|0-60PSI|0-100PSI|0-160PSI|0-200PSI|0-300PSI|0-600PSI|0-1000PSI|0-3000PSI|0-5000PSI",
            ),
            _r("conn", "1/8NPT LM|1/4NPT LM|1/4NPT CBM|1/2NPT LM"),
            _r("fill", "DRY|GLYCERIN"),
        ),
        28.0,
        scale_step=0.0,
    ),
)

# Parser families whose formats differ per ERP style.
PARSER_FAMILIES = ("fasteners", "bearings", "pvf", "electrical", "ppe", "abrasives")
# Roles a clerk drops first when the description field is full.
NON_CRITICAL_ROLES = frozenset(
    "color lining frame finish feature holes perf kit key grain coat cord style deck ip fill "
    "ring aux operator pins speed fused ep base".split()
)
# Index of the head noun when it is not the last word (the target writes it first).
NOUN_HEAD = {
    "nitrile_glove": 0, "cut_glove": 0, "leather_glove": 0, "thhn_wire": 0, "relay": 0,
    "pushbutton": 0, "prox_sensor": 1, "jobber_drill": 1, "wrench": 0, "bandsaw_blade": 1,
    "hole_saw": 1, "earplug": 0, "respirator": 0, "coverall": 0, "harness": 0, "lanyard": 0,
    "pallet": 0, "thermal_label": 0, "foam_sheet": 1, "rsc_box": 1, "paint": 0, "caliper": 0,
    "air_filter": 1, "electrode": 0,
}  # fmt: skip


def by_l2() -> dict[str, tuple[Template, ...]]:
    out: dict[str, list[Template]] = {}
    for template in TEMPLATES:
        out.setdefault(template.l2, []).append(template)
    return {k: tuple(v) for k, v in out.items()}


def format_role(role: Role, value: str, style: str, family: str) -> str:
    """Render one attribute value in an ERP style ("A" acquirer, "B" target)."""
    varied = family in PARSER_FAMILIES and style == "B"
    fmt = role.fmt
    if fmt == "inch":
        return f'{value}"' if varied else f"{value}IN"
    if fmt == "class":
        return f"CL{value}" if varied else f"{value}#"
    if fmt == "size":
        return _SIZE_B.get(value, value) if varied else f"SZ {value}"
    if fmt == "poles":
        return f"{value}POLE" if varied else f"{value}P"
    if fmt == "desig":
        return value.replace("-", " ") if varied else value.replace(" ", "-")
    return value

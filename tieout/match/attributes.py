"""Critical-attribute parsers and the attribute veto (PRD 4.4, I2).

Each parser takes an I0-normalised description (pack tokens already removed)
and returns a canonical ``dict[str, str]``. Values are canonicalised so that
equivalent renderings compare equal: numbers are decimals without trailing
zeros (``1/2IN`` and ``0.5 IN`` are both ``0.5IN``), metric lengths are
millimetres and imperial lengths inches, and synonyms map to one spelling.

Keys come in two kinds per family:

* **critical** keys are the PRD I2 attributes (split into components where one
  PRD attribute has parts, such as thread diameter and pitch). Only these count
  towards the "at least two agreeing attributes" rule for automatic matches.
* **guard** keys (``kind``, ``style``, ``alloy``...) never count towards that
  rule, but a disagreement on them is still a conflict. They exist because a
  wrong match is worse than a missed one (PRD 4.1).

The generic family returns one entry per numeric-and-unit token, keyed by the
token itself.

Use :func:`parse_description` for a raw description and :func:`compare` for the
veto decision.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from tieout.normalise.items import normalise_description
from tieout.normalise.packs import strip_pack_tokens

__all__ = [
    "CRITICAL_KEYS",
    "FAMILIES",
    "Attributes",
    "Comparison",
    "bare_numbers",
    "compare",
    "numeric_tokens",
    "parse_attributes",
    "parse_description",
]

Attributes = dict[str, str]

FAMILIES = ("fasteners", "bearings", "pvf", "electrical", "ppe", "abrasives", "generic")

CRITICAL_KEYS: dict[str, frozenset[str]] = {
    "fasteners": frozenset({"thread", "length", "head", "material", "grade", "finish"}),
    "bearings": frozenset({"designation", "seal", "clearance", "suffix"}),
    "pvf": frozenset({"size", "class", "psi", "pn", "schedule", "material", "end"}),
    "electrical": frozenset({"voltage", "current", "poles", "enclosure", "gauge", "power"}),
    "ppe": frozenset({"type", "material", "coating", "size"}),
    "abrasives": frozenset(
        {"diameter", "bore", "grit", "thickness", "type", "teeth", "flutes", "angle", "insert"}
    ),
}

# Bearing components that, once a base designation is present on both sides,
# read as "none" when absent: the PRD attribute is the full designation.
_BEARING_FULL = ("seal", "clearance", "suffix")

# ----------------------------------------------------------------- numbers

# Mixed numbers are hyphenated by I0 ("1 1/2" -> "1-1/2"), so a space always
# separates two numbers ("90 3/4IN" is a 90 degree elbow of 3/4 inch).
NUM = r"(?:\d+-\d+/\d+|\d+/\d+|\d*\.\d+|\d+)"
_B = r"(?<![A-Z0-9])"  # token start
_E = r"(?![A-Z0-9])"  # token end


def to_float(text: str) -> float:
    """Parse ``1``, ``.5``, ``1/2``, ``1-1/2`` and ``1 1/2``."""
    text = text.strip()
    m = re.fullmatch(r"(\d+)[- ](\d+)/(\d+)", text)
    if m:
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    m = re.fullmatch(r"(\d+)/(\d+)", text)
    if m:
        den = int(m.group(2))
        return int(m.group(1)) / den if den else 0.0
    return float(text)


def fmt(value: float) -> str:
    """Canonical number: up to four decimals, no trailing zeros."""
    out = f"{value:.4f}".rstrip("0").rstrip(".")
    return out if out else "0"


def _num(text: str) -> str:
    return fmt(to_float(text))


def _first(patterns: list[tuple[str, str]], text: str) -> str | None:
    for pattern, value in patterns:
        if re.search(pattern, text):
            return value
    return None


def _length(value: str, unit: str | None, metric: bool) -> str:
    """Canonical length: millimetres for metric, inches for imperial."""
    x = to_float(value)
    unit = (unit or "").upper()
    if unit == "FT":
        return f"{fmt(x * 12)}IN"
    if unit == "IN":
        return f"{fmt(x)}IN"
    if unit == "CM":
        return f"{fmt(x * 10)}MM"
    if unit == "M":
        return f"{fmt(x * 1000)}MM"
    if unit == "MM":
        return f"{fmt(x)}MM"
    return f"{fmt(x)}MM" if metric else f"{fmt(x)}IN"


# --------------------------------------------------------------- fasteners

_METRIC_THREAD = re.compile(
    rf"{_B}M(?P<d>\d+(?:\.\d+)?)(?P<chain>(?:[-X]\d+(?:\.\d+)?(?:MM)?)*)(?![\d.])"
)
_IMPERIAL_THREAD = re.compile(
    rf"(?<![\d./A-Z])(?P<d>#\d{{1,2}}|\d+/\d+|\d*\.\d+|\d{{1,2}})(?:IN)?\s*-\s*"
    rf"(?P<tpi>\d{{1,2}})(?![\d/.])(?:\s*(?:UNC|UNF|UNEF|UN|NC|NF){_E})?"
    rf"(?:\s*X\s*(?P<len>{NUM})(?P<lu>IN|FT|MM)?)?"
)
_BARE_DIAMETER_X_LENGTH = re.compile(
    rf"(?<![\d./A-Z-])(?P<d>\d+/\d+|#\d{{1,2}})(?:IN)?X(?P<len>{NUM})(?P<lu>IN|FT|MM)?"
)
_BARE_DIAMETER = re.compile(r"(?<![\d./A-Z-])(?P<d>\d+/\d+|#\d{1,2})(?:IN)?(?![\d/X-])")
_LENGTH_WORD = re.compile(
    rf"(?:LENGTH|LONG|LG|{_B}L)\s*[:=]?\s*(?P<v>{NUM})(?P<u>IN|MM|FT|CM){_E}"
    rf"|(?P<v2>{NUM})(?P<u2>IN|MM|FT|CM)\s*(?:LONG|LG|LENGTH|L){_E}"
)
_FASTENER_GRADE = [
    (r"(?<![\d.])(4\.6|4\.8|5\.8|8\.8|10\.9|12\.9)(?![\d.])", None),
    (r"(?:GRADE|GR|CLASS|CL)\s*-?\s*(4\.6|4\.8|5\.8|8\.8|10\.9|12\.9)(?![\d.])", None),
    (rf"(?:GRADE|{_B}GR)\s*-?\s*([2589]){_E}", "GR"),
    (rf"{_B}G([258]){_E}", "GR"),
    (rf"{_B}(A[24])\s*-?\s*(50|70|80){_E}", "A"),
    (rf"{_B}(A[24]){_E}", None),
    (rf"{_B}(B7|B8|B8M|A307|A325|A490|L7){_E}", None),
    (
        rf"(?:STAINLESS(?: STEEL)?|{_B}SS)\s*-?\s*(18-8|304|316|410)L?{_E}"
        rf"|{_B}(18-8|304|316|410)L?\s*-?\s*(?:STAINLESS|SS{_E})",
        None,
    ),
    (rf"{_B}(18-8){_E}", None),
]
_FASTENER_HEAD = [
    (r"SET SCREW|SETSCREW", "SET"),
    (r"BUTTON", "BUTTON"),
    (r"FLAT HEAD|FLAT HD|FLAT SOCKET|FLAT CAP|COUNTERSUNK|\bFLAT PHILLIPS", "FLAT"),
    (r"SOCKET", "SOCKET"),
    (r"FLANGE", "FLANGE"),
    (r"CARRIAGE", "CARRIAGE"),
    (r"\bPAN\b", "PAN"),
    (r"TRUSS", "TRUSS"),
    (r"\bOVAL\b", "OVAL"),
    (r"ROUND HEAD|ROUND HD", "ROUND"),
    (r"\bWING\b", "WING"),
    (r"SQUARE HEAD|SQUARE HD|\bSQUARE NUT", "SQUARE"),
    (r"\bEYE\b", "EYE"),
    (r"\bHEX\b|\bHEXAGON", "HEX"),
]
_FASTENER_KIND = [
    (r"SET SCREW|SETSCREW", "SET SCREW"),
    (r"ANCHOR", "ANCHOR"),
    (r"RIVET", "RIVET"),
    (r"WASHER", "WASHER"),
    (r"\bNUTS?\b|LOCKNUT", "NUT"),
    (r"THREADED ROD|ALL ?THREAD|\bROD\b", "ROD"),
    (r"\bSTUDS?\b", "STUD"),
    (r"\bBOLTS?\b|\bSCREWS?\b|CAPSCREW", "SCREW"),
]
_FASTENER_STYLE = [
    (r"LOCK WASHER|LOCKWASHER|SPLIT WASHER|SPLIT LOCK", "LOCK"),
    (r"FENDER WASHER", "FENDER"),
    (r"FLAT WASHER", "FLAT"),
    (r"NYLON INSERT|NYLOCK|NYLOC|NYLON LOCK", "NYLON INSERT"),
    (r"\bJAM\b", "JAM"),
    (r"COUPLING NUT", "COUPLING"),
    (r"ACORN|CAP NUT", "ACORN"),
    (r"\bKEPS\b|K-LOCK", "KEPS"),
]
_FASTENER_MATERIAL = [
    (r"STAINLESS|(?<![A-Z])SS(?=\d)|\dL?SS\b", "STAINLESS STEEL"),
    (r"SILICON BRONZE", "SILICON BRONZE"),
    (r"BRASS", "BRASS"),
    (r"BRONZE", "BRONZE"),
    (r"ALUMINUM|ALUMINIUM", "ALUMINUM"),
    (r"TITANIUM", "TITANIUM"),
    (r"\bNYLON\b", "NYLON"),
    (r"COPPER", "COPPER"),
    (r"ALLOY STEEL|\bALLOY\b", "ALLOY STEEL"),
    (r"CARBON STEEL|\bSTEEL\b", "STEEL"),
]
_FASTENER_FINISH = [
    (r"ELECTRO GALVANIZED", "ZINC PLATED"),
    (r"GALVANIZED|\bHDG\b|\bGALV\b", "GALVANIZED"),
    (r"YELLOW ZINC|ZINC YELLOW|YELLOW CHROMATE|YELLOW PLATED|\bZY\b", "YELLOW ZINC"),
    (r"BLACK OXIDE", "BLACK OXIDE"),
    (r"PHOSPHATE", "BLACK PHOSPHATE"),
    (r"ZINC FLAKE|GEOMET|DACROMET", "ZINC FLAKE"),
    (r"\bZINC\b|ZINC PLATED|\bZC\b", "ZINC PLATED"),
    (r"NICKEL", "NICKEL"),
    (r"CHROME", "CHROME"),
    (r"\bPLAIN\b|UNPLATED|UNFINISHED|SELF COLOU?R|\bBRIGHT\b", "PLAIN"),
    (r"\bBLACK\b", "BLACK OXIDE"),
]


def _fastener_grade(text: str) -> str | None:
    for pattern, prefix in _FASTENER_GRADE:
        m = re.search(pattern, text)
        if not m:
            continue
        groups = [g for g in m.groups() if g]
        if prefix == "GR":
            return f"GR{groups[0]}"
        if prefix == "A":
            return f"{groups[0]}-{groups[1]}"
        return groups[0]
    return None


def parse_fasteners(text: str) -> Attributes:
    """Thread (diameter and pitch), length, head, material, grade, finish."""
    out: Attributes = {}
    grade = _fastener_grade(text)
    if grade:
        out["grade"] = grade
    # Remove things that look like threads but are not (18-8, A2-70, grades).
    work = re.sub(r"(?<![\d.])18-8(?!\d)|A[24]\s*-?\s*(?:50|70|80)", " ", text)
    metric: bool | None = None
    span: tuple[int, int] | None = None

    m = _METRIC_THREAD.search(work)
    if m:
        metric, span = True, m.span()
        out["thread"] = f"M{_num(m.group('d'))}"
        parts = re.findall(r"([-X])(\d+(?:\.\d+)?)(MM)?", m.group("chain"))
        if parts:
            sep, first, _ = parts[0]
            first_is_pitch = (len(parts) >= 2 and float(first) <= 4) or (
                len(parts) == 1 and "." in first and float(first) < 4
            )
            if first_is_pitch:
                out["pitch"] = _num(first)
                if len(parts) >= 2:
                    out["length"] = _length(parts[1][1], "MM", True)
            elif sep == "X" or len(parts) == 1:
                out["length"] = _length(first, "MM", True)
    else:
        m = _IMPERIAL_THREAD.search(work)
        if m and 4 <= int(m.group("tpi")) <= 80:
            d, tpi = m.group("d"), int(m.group("tpi"))
            if d.isdigit() and not d.startswith("#"):
                if int(d) <= 12 and tpi >= 24:
                    d = f"#{int(d)}"
                elif int(d) > 4:
                    m = None
        if m:
            metric, span = False, m.span()
            out["thread"] = d if d.startswith("#") else _num(d)
            out["pitch"] = str(int(m.group("tpi")))
            if m.group("len"):
                out["length"] = _length(m.group("len"), m.group("lu"), False)
        else:
            m = _BARE_DIAMETER_X_LENGTH.search(work)
            if m:
                metric, span = False, m.span()
                d = m.group("d")
                out["thread"] = d if d.startswith("#") else _num(d)
                out["length"] = _length(m.group("len"), m.group("lu"), False)
            else:
                m = _BARE_DIAMETER.search(work)
                if m:
                    metric, span = False, m.span()
                    d = m.group("d")
                    out["thread"] = d if d.startswith("#") else _num(d)

    if "length" not in out:
        rest = work if span is None else work[: span[0]] + " " + work[span[1] :]
        lm = _LENGTH_WORD.search(rest)
        if lm:
            value, unit = (
                (lm.group("v"), lm.group("u"))
                if lm.group("v")
                else (lm.group("v2"), lm.group("u2"))
            )
            out["length"] = _length(value, unit, bool(metric))
        elif metric is not None:
            unit = "MM" if metric else "IN"
            found = {
                _length(v, u, metric)
                for v, u in re.findall(rf"(?<![\d./A-Z-])({NUM})({unit}|FT){_E}", rest)
            }
            if len(found) == 1:
                out["length"] = found.pop()

    for key, table in (
        ("head", _FASTENER_HEAD),
        ("kind", _FASTENER_KIND),
        ("style", _FASTENER_STYLE),
        ("finish", _FASTENER_FINISH),
    ):
        value = _first(table, text)
        if value:
            out[key] = value
    material_text = re.sub(r"NYLON INSERT|NYLON LOCK", " ", text)
    material = _first(_FASTENER_MATERIAL, material_text)
    if material:
        out["material"] = material
    if out.get("finish") == "BLACK OXIDE" and "BLACK OXIDE" not in text and "BLACK" in text:
        # A bare "BLACK" on a nylon or plastic part is a colour, not a finish.
        if material in {"NYLON"}:
            del out["finish"]
    return out


# ---------------------------------------------------------------- bearings

_SEAL_CODES: dict[str, str] = {
    "2RSH": "2RS",
    "2RSR": "2RS",
    "2RS1": "2RS",
    "2RSL": "2RS",
    "2RS": "2RS",
    "LLU": "2RS",
    "DDU": "2RS",
    "UU": "2RS",
    "RSH": "RS",
    "RSR": "RS",
    "RS1": "RS",
    "RS": "RS",
    "LU": "RS",
    "DU": "RS",
    "2RZ": "2RZ",
    "LLB": "2RZ",
    "VV": "2RZ",
    "RZ": "RZ",
    "2ZR": "ZZ",
    "2Z": "ZZ",
    "ZZ": "ZZ",
    "ZR": "Z",
    "Z": "Z",
}
_CLEARANCE_CODES = {"C2": "C2", "C3": "C3", "C4": "C4", "C5": "C5", "CN": "CN"}
_OTHER_CODES = (
    "TN9",
    "TVH",
    "TVP",
    "ECP",
    "ECJ",
    "ECM",
    "CCK",
    "W33",
    "EK",
    "NR",
    "CC",
    "CA",
    "MB",
    "P6",
    "P5",
    "P4",
    "BE",
    "E",
    "J",
    "M",
    "K",
    "N",
    "B",
    "X",
    "C",
)
_SUFFIX_CODES = sorted(
    list(_SEAL_CODES) + list(_CLEARANCE_CODES) + list(_OTHER_CODES), key=lambda c: (-len(c), c)
)
_SUFFIX_RE = re.compile("|".join(re.escape(c) for c in _SUFFIX_CODES))
_BEARING_BASE = re.compile(
    r"(?<![A-Z0-9./])(?P<prefix>UCFL|UCFC|UCP|UCF|UCT|UC|NUP|NU|NJ|NN|NA|NK|RNA|HK|SA|SB|JLM|JL|JM"
    r"|LM|HM|L|M|N)?(?P<digits>\d{3,6})(?P<tail>[A-Z0-9]*(?:[-/.][A-Z0-9]+)*)(?![A-Z0-9])"
)
_BEARING_UNITS = re.compile(r"^(?:MM|IN|X|V|A|LB|KG|RPM)")


def _split_suffix_chunk(chunk: str) -> list[str] | None:
    """Split ``ZZC3`` into known codes; ``None`` when the chunk is not all codes."""
    codes: list[str] = []
    pos = 0
    while pos < len(chunk):
        m = _SUFFIX_RE.match(chunk, pos)
        if not m:
            return None
        codes.append(m.group(0))
        pos = m.end()
    return codes


def _classify(codes: list[str], out: Attributes, other: set[str]) -> None:
    for code in codes:
        if code in _SEAL_CODES:
            out.setdefault("seal", _SEAL_CODES[code])
        elif code in _CLEARANCE_CODES:
            if code != "CN":
                out.setdefault("clearance", code)
        else:
            other.add(code)


def parse_bearings(text: str) -> Attributes:
    """Full designation: base number plus seal, clearance and other suffixes."""
    out: Attributes = {}
    other: set[str] = set()
    base = None
    for m in _BEARING_BASE.finditer(text):
        tail = m.group("tail")
        if _BEARING_UNITS.match(tail):
            continue
        base = m
        break
    if base is not None:
        out["designation"] = (base.group("prefix") or "") + base.group("digits")
        tail = base.group("tail")
        chunks = [c for c in re.split(r"[-/.]", tail) if c]
        for i, chunk in enumerate(chunks):
            codes = _split_suffix_chunk(chunk)
            if codes is not None:
                _classify(codes, out, other)
            elif chunk.isdigit() and i == 0 and len(chunk) <= 2:
                other.add(f"-{chunk}")  # inch bore of insert units, e.g. UC205-16
            else:
                other.add(chunk)
        # Space-separated suffix tokens straight after the designation. A one- or
        # two-digit token straight after a bare designation is the inch bore that a
        # hyphen would attach ("UC205 16" reads as "UC205-16").
        rest = text[base.end() :].split()
        if rest and not chunks and rest[0].isdigit() and len(rest[0]) <= 2:
            other.add(f"-{rest[0]}")
            rest = rest[1:]
        for token in rest:
            parts = [p for p in re.split(r"[-/.]", token) if p]
            split = [_split_suffix_chunk(p) for p in parts]
            if not parts or any(s is None for s in split):
                break
            for codes in split:
                _classify(codes or [], out, other)
    # Seal and clearance stated anywhere else in the description.
    if "seal" not in out:
        seal = _first(
            [
                (r"(?<![A-Z0-9])(?:2RSH|2RSR|2RS1|2RS|LLU|DDU)(?![A-Z0-9])", "2RS"),
                (r"DOUBLE (?:RUBBER )?SEAL|2 SEALS?|SEALED BOTH|\bSEALED\b", "2RS"),
                (r"(?<![A-Z0-9])(?:ZZ|2Z|2ZR)(?![A-Z0-9])", "ZZ"),
                (r"DOUBLE SHIELD|2 SHIELDS?|\bSHIELDED\b", "ZZ"),
                (r"SINGLE SEAL|ONE SEAL", "RS"),
                (r"SINGLE SHIELD|ONE SHIELD", "Z"),
                (r"\bOPEN\b", "OPEN"),
            ],
            text,
        )
        if seal:
            out["seal"] = seal
    if "clearance" not in out:
        cm = re.search(r"(?<![A-Z0-9])(C[2-5])(?![A-Z0-9])", text)
        if cm:
            out["clearance"] = cm.group(1)
    if other:
        out["suffix"] = "+".join(sorted(other))
    return out


# ---------------------------------------------------------------------- pvf

_PVF_SIZE_GROUP = re.compile(
    rf"(?<![\d./A-Z#-])(?P<g>{NUM}(?:IN)?(?:X{NUM}(?:IN)?)+)(?P<u>IN)?(?![\d/])"
)
_PVF_SIZE_UNIT = re.compile(rf"(?<![\d./A-Z#-])(?P<v>{NUM})IN{_E}|NPS\s*(?P<n>{NUM})")
_PVF_SIZE_BARE = re.compile(
    rf"(?<![\d./A-Z#-])(?P<v>\d+-\d+/\d+|\d+/\d+|\d*\.\d+|1[0-2]|[1-9])"
    rf"(?![\d/.]|\s*(?:PC|PIECE|WAY|DEG|#|LB|PSI|WOG|FT|MM|M{_E}|X))"
)
_PVF_MATERIAL = [
    (r"\bCPVC\b", "CPVC"),
    (r"\bPVC\b", "PVC"),
    (r"\bHDPE\b|POLYETHYLENE", "HDPE"),
    (r"POLYPROPYLENE|\bPP\b", "POLYPROPYLENE"),
    (r"STAINLESS|(?<![A-Z])SS(?=\d)|\dL?SS\b|CF8M|CF8\b", "STAINLESS STEEL"),
    (r"MALLEABLE", "MALLEABLE IRON"),
    (r"DUCTILE", "DUCTILE IRON"),
    (r"CAST IRON|\bCI\b", "CAST IRON"),
    (r"GALVANIZED|\bGALV\b", "GALVANIZED STEEL"),
    (r"BLACK", "BLACK STEEL"),
    (r"\bBRASS\b", "BRASS"),
    (r"\bBRONZE\b", "BRONZE"),
    (r"\bCOPPER\b", "COPPER"),
    (r"ALUMINUM|ALUMINIUM", "ALUMINUM"),
    (r"CARBON STEEL|FORGED STEEL|\bA105\b|\bA106\b|\bA53\b|\bSTEEL\b|\bCS\b", "CARBON STEEL"),
]
_PVF_ENDS = [
    (
        r"(?:FEMALE |MALE )?NPT|\bFNPT|\bMNPT|\bFIP\b|\bMIP\b|THREADED|\bTHREAD\b|\bTHD\b"
        r"|SCREWED|\bFPT\b|\bMPT\b",
        "THREADED",
    ),
    (r"SOCKET WELD|SOCKETWELD|\bS/W\b|\bSWITCH\b|\bSW\b", "SOCKET WELD"),
    (r"BUTT ?WELD|\bBW\b|BEVEL", "BUTT WELD"),
    (r"FLANGED?|RAISED FACE|\bRF\b|\bFF\b", "FLANGED"),
    (r"SWEAT|SOLDER|\bCXC\b|\bC X C\b", "SOLDER"),
    (r"GROOVED|\bGRV\b", "GROOVED"),
    (r"PLAIN END|\bPE\b", "PLAIN END"),
    (r"COMPRESSION", "COMPRESSION"),
    (r"SOCKET(?! ?WELD)|\bSLIP\b|\bSXS\b|\bSOC\b", "SOCKET"),
    (r"\bPRESS\b|PROPRESS", "PRESS"),
    (r"WAFER", "WAFER"),
    (r"\bLUG\b", "LUG"),
]
_PVF_KIND = [
    (r"BALL VALVE|\bBALL\b", "BALL VALVE"),
    (r"GATE", "GATE VALVE"),
    (r"GLOBE", "GLOBE VALVE"),
    (r"CHECK", "CHECK VALVE"),
    (r"BUTTERFLY", "BUTTERFLY VALVE"),
    (r"NEEDLE", "NEEDLE VALVE"),
    (r"PLUG VALVE", "PLUG VALVE"),
    (r"SOLENOID", "SOLENOID VALVE"),
    (r"RELIEF", "RELIEF VALVE"),
    (r"ELBOW|\bELL\b", "ELBOW"),
    (r"\bTEE\b", "TEE"),
    (r"CROSS", "CROSS"),
    (r"UNION", "UNION"),
    (r"NIPPLE", "NIPPLE"),
    (r"REDUCER|REDUCING", "REDUCER"),
    (r"BUSHING", "BUSHING"),
    (r"COUPLING", "COUPLING"),
    (r"\bCAP\b", "CAP"),
    (r"\bPLUG\b", "PLUG"),
    (r"ADAPTER", "ADAPTER"),
    (r"FLANGE", "FLANGE"),
    (r"\bPIPE\b|\bTUBE\b|TUBING", "PIPE"),
]


def parse_pvf(text: str) -> Attributes:
    """Nominal size, pressure class (class, psi, PN, schedule), material, end connection."""
    out: Attributes = {}
    work = text
    sch = re.search(r"(?:SCHEDULE|SCH)\s*-?\s*(\d{1,3}S?|XXS|XS|STD)(?![A-Z0-9])", work)
    if sch:
        out["schedule"] = f"SCH{sch.group(1)}"
        work = work[: sch.start()] + " " + work[sch.end() :]
    psi = re.search(r"(?<![\d.])(\d{2,5})\s*#?\s*(?:PSIG|PSI|WOG|CWP|WSP)(?![A-Z])", work)
    if psi:
        out["psi"] = f"{int(psi.group(1))}PSI"
        work = work[: psi.start()] + " " + work[psi.end() :]
    cls = re.search(
        r"(?:CLASS|CL)\s*-?\s*(\d{2,4})(?!\d)|(?<![\d.])(\d{2,4})\s*(?:#|LBS?(?![A-Z]))", work
    )
    if cls:
        out["class"] = f"CL{int(cls.group(1) or cls.group(2))}"
    pn = re.search(r"(?<![A-Z0-9])PN\s*(\d{1,3})(?!\d)", work)
    if pn:
        out["pn"] = f"PN{int(pn.group(1))}"
    work = re.sub(
        r"(?:CLASS|CL|PN)\s*-?\s*\d+|\d+\s*(?:#|LBS?|PSIG|PSI|WOG|CWP|WSP)(?![A-Z])"
        r"|\d+\s*DEG(?:REE)?S?|(?:45|90|180)\s*(?=ELBOW|ELL|BEND)|(?:ELBOW|ELL)\s*(?:45|90)",
        " ",
        work,
    )
    is_nipple = "NIPPLE" in text
    size: str | None = None
    g = _PVF_SIZE_GROUP.search(work)
    if g:
        parts = [p for p in re.split(r"X", g.group("g").replace("IN", "")) if p]
        values = [_num(p) for p in parts]
        if is_nipple and len(values) == 2:
            size, out["length"] = values[0], f"{values[1]}IN"
        else:
            size = "X".join(values)
    else:
        u = _PVF_SIZE_UNIT.search(work)
        if u:
            size = _num(u.group("v") or u.group("n"))
        else:
            dn = re.search(r"(?<![A-Z0-9])DN\s*(\d{1,4})(?!\d)", work)
            mm = re.search(r"(?<![\d./])(\d{1,4})MM(?![A-Z0-9])", work)
            if dn:
                out["size"] = f"DN{int(dn.group(1))}"
            elif mm:
                out["size"] = f"{int(mm.group(1))}MM"
            else:
                b = _PVF_SIZE_BARE.search(work)
                if b:
                    size = _num(b.group("v"))
    if size is not None:
        out["size"] = f"{size}IN"
    material = _first(_PVF_MATERIAL, text)
    if material:
        out["material"] = material
    alloy = re.search(r"(?<![\d.])(304L|316L|304|316)(?![\d.])|CF8M", text)
    if alloy:
        out["alloy"] = alloy.group(1) or "316"
    ends = sorted({v for p, v in _PVF_ENDS if re.search(p, text)})
    if ends:
        out["end"] = "+".join(ends)
    kind = _first(_PVF_KIND, text)
    if kind:
        out["kind"] = kind
    angle = re.search(
        r"(?<!\d)(45|90|180)\s*(?:DEG(?:REE)?S?)?\s*(?:ELBOW|ELL|BEND)|(?:ELBOW|ELL)\s*(45|90)(?!\d)",
        text,
    )
    if angle:
        out["angle"] = angle.group(1) or angle.group(2)
    return out


# --------------------------------------------------------------- electrical

_VOLT = re.compile(
    r"(?<![\d./])(?P<v>\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)*(?:-\d+(?:\.\d+)?)?)\s*"
    r"(?P<u>KV|VAC|VDC|V|VOLTS?)(?:\s*(?P<t>AC|DC))?(?![A-Z0-9])"
)
_AMP = re.compile(r"(?<![\d./])(?P<v>\d+(?:\.\d+)?)\s*(?P<u>KA|MA|A|AMPS?|AMPERES?)(?![A-Z0-9])")


def parse_electrical(text: str) -> Attributes:
    """Voltage, current rating (amps, wire gauge, horsepower), poles, enclosure rating."""
    out: Attributes = {}
    volts: set[str] = set()
    vtype: set[str] = set()
    for m in _VOLT.finditer(text):
        raw, unit = m.group("v"), m.group("u")
        scale = 1000.0 if unit == "KV" else 1.0
        parts = re.split(r"([/-])", raw)
        canon = "".join(p if p in "/-" else fmt(float(p) * scale) for p in parts)
        volts.add(f"{canon}V")
        if unit in {"VAC", "VDC"}:
            vtype.add(unit[1:])
        elif m.group("t"):
            vtype.add(m.group("t"))
    if volts:
        out["voltage"] = ",".join(sorted(volts))
    if vtype:
        out["vtype"] = ",".join(sorted(vtype))
    amps: set[str] = set()
    for m in _AMP.finditer(text):
        unit = m.group("u")
        value = fmt(float(m.group("v")))
        if unit == "KA":
            out["kaic"] = f"{value}KA"
        elif unit == "MA":
            amps.add(f"{value}MA")
        else:
            amps.add(f"{value}A")
    if amps:
        out["current"] = ",".join(sorted(amps))
    gauge = re.search(
        r"(?<![\d./])(\d{1,2}|[1-4]/0)\s*(?:AWG|GA|GAUGE)(?![A-Z])|AWG\s*(\d{1,2}|[1-4]/0)(?![\d/])"
        r"|(?<![A-Z0-9/])#(\d{1,2}|[1-4]/0)(?![\d/])",
        text,
    )
    if gauge:
        out["gauge"] = f"{gauge.group(1) or gauge.group(2) or gauge.group(3)}AWG"
    cond = re.search(
        r"(?<![\d./#])(\d{1,2})/(\d{1,2})(?![\d/]|\s*(?:HP|IN|AWG|GA)(?![A-Z]))"
        r"|(?<![\d.])(\d{1,2})\s*(?:C|COND|CONDUCTOR)S?(?![A-Z0-9])",
        text,
    )
    if cond and cond.group(1) and 6 <= int(cond.group(1)) <= 22:
        out.setdefault("gauge", f"{int(cond.group(1))}AWG")
        out["conductors"] = str(int(cond.group(2)))
    elif cond and cond.group(3):
        out["conductors"] = str(int(cond.group(3)))
    hp = re.search(rf"(?<![\d./])({NUM})\s*HP(?![A-Z])", text)
    if hp:
        out["power"] = f"{_num(hp.group(1))}HP"
    else:
        kw = re.search(r"(?<![\d./])(\d+(?:\.\d+)?)\s*KW(?![A-Z])", text)
        if kw:
            out["power"] = f"{fmt(float(kw.group(1)))}KW"
    poles = re.search(r"(?<![\d.])([1-4])\s*-?\s*(?:POLES?|P)(?![A-Z0-9])", text)
    if poles:
        out["poles"] = poles.group(1)
    else:
        word = _first(
            [
                (r"SINGLE POLE|\bSPST\b|\bSPDT\b", "1"),
                (r"DOUBLE POLE|TWO POLE|\bDPST\b|\bDPDT\b", "2"),
                (r"TRIPLE POLE|THREE POLE|\b3PST\b|\b3PDT\b", "3"),
                (r"FOUR POLE", "4"),
            ],
            text,
        )
        if word:
            out["poles"] = word
    phase = re.search(r"(?<![\d.])([13])\s*-?\s*(?:PH|PHASE)(?![A-Z])", text)
    if phase:
        out["phase"] = phase.group(1)
    elif re.search(r"SINGLE PHASE", text):
        out["phase"] = "1"
    elif re.search(r"THREE PHASE", text):
        out["phase"] = "3"
    enclosure: set[str] = set()
    for m in re.finditer(
        r"NEMA\s*(?:TYPE\s*)?(\d{1,2}[XRSKP]?)(?![A-Z0-9])|TYPE\s*(\d{1,2}[XRSKP]?)(?![A-Z0-9])",
        text,
    ):
        enclosure.add(f"NEMA{m.group(1) or m.group(2)}")
    for m in re.finditer(r"(?<![A-Z0-9])IP\s*(\d{2})(?!\d)", text):
        enclosure.add(f"IP{m.group(1)}")
    motor = _first(
        [
            (r"\bTEFC\b|TOTALLY ENCLOSED FAN COOLED", "TEFC"),
            (r"\bTENV\b", "TENV"),
            (r"\bTEAO\b", "TEAO"),
            (r"\bODP\b|OPEN DRIP", "ODP"),
            (r"EXPLOSION PROOF|\bXP\b|\bEXP\b", "XP"),
        ],
        text,
    )
    if motor:
        enclosure.add(motor)
    if enclosure:
        out["enclosure"] = "+".join(sorted(enclosure))
    rpm = re.search(r"(?<![\d.])(\d{3,4})\s*RPM", text)
    if rpm:
        out["rpm"] = rpm.group(1)
    frame = re.search(
        r"(?<![A-Z0-9])(\d{2,3}[A-Z]{0,3})\s*FRAME|FRAME\s*(\d{2,3}[A-Z]{0,3})(?![A-Z0-9])", text
    )
    if frame:
        out["frame"] = frame.group(1) or frame.group(2)
    contacts = re.search(
        r"(?<![A-Z0-9])(\d)\s*NO\s*-?\s*(\d)\s*NC(?![A-Z])|(?<![A-Z0-9])(\d)\s*(NO|NC)(?![A-Z])",
        text,
    )
    if contacts:
        if contacts.group(1):
            out["contacts"] = f"{contacts.group(1)}NO{contacts.group(2)}NC"
        else:
            out["contacts"] = f"{contacts.group(3)}{contacts.group(4)}"
    return out


# --------------------------------------------------------------------- ppe

_PPE_TYPE = [
    (r"FACE ?SHIELD", "FACE SHIELD"),
    (r"GOGGLES?", "GOGGLES"),
    (r"GLASSES|SPECTACLES|EYEWEAR", "GLASSES"),
    (r"RESPIRATOR|\bMASK\b|DUST MASK", "RESPIRATOR"),
    (r"EAR ?PLUGS?", "EARPLUG"),
    (r"EAR ?MUFFS?", "EARMUFF"),
    (r"HARD ?HAT|HELMET", "HARD HAT"),
    (r"COVERALLS?", "COVERALL"),
    (r"\bVEST\b", "VEST"),
    (r"APRON", "APRON"),
    (r"SLEEVES?", "SLEEVE"),
    (r"BOOTS?\b", "BOOT"),
    (r"SHOES?\b", "SHOE"),
    (r"JACKET", "JACKET"),
    (r"GLOVES?|MITTS?|MITTENS?", "GLOVE"),
]
_PPE_MATERIALS = [
    (r"NITRILE", "NITRILE"),
    (r"LATEX|NATURAL RUBBER", "LATEX"),
    (r"VINYL", "VINYL"),
    (r"NEOPRENE", "NEOPRENE"),
    (r"POLYURETHANE|(?<![A-Z])PU(?![A-Z])", "POLYURETHANE"),
    (r"\bPVC\b", "PVC"),
    (r"LEATHER|COWHIDE|GOATSKIN|PIGSKIN|DEERSKIN|COW GRAIN|GOAT GRAIN", "LEATHER"),
    (r"KEVLAR|ARAMID", "ARAMID"),
    (r"\bHPPE\b|DYNEEMA", "HPPE"),
    (r"COTTON", "COTTON"),
    (r"\bNYLON\b", "NYLON"),
    (r"POLYESTER", "POLYESTER"),
    (r"POLYCARBONATE", "POLYCARBONATE"),
    (r"\bFOAM\b", "FOAM"),
    (r"TYVEK|POLYPROPYLENE", "POLYPROPYLENE"),
]
_T0 = r"(?<![A-Z0-9'’])"
_T1 = r"(?![A-Z0-9])"
_PPE_SIZES = [
    (rf"{_T0}(?:XXXL|3XL|3X|3X-LARGE|XXX-LARGE){_T1}", "3XL"),
    (rf"{_T0}(?:XXL|2XL|2X|2X-LARGE|XX-LARGE|XXLARGE){_T1}", "2XL"),
    (rf"{_T0}(?:XL|XLG|X-LARGE|XLARGE|EXTRA LARGE|X-LG){_T1}", "XL"),
    (rf"{_T0}(?:XS|X-SMALL|XSMALL|EXTRA SMALL){_T1}", "XS"),
    (rf"{_T0}(?:LARGE|LG|LRG|L){_T1}", "L"),
    (rf"{_T0}(?:MEDIUM|MED|MD|M){_T1}", "M"),
    (rf"{_T0}(?:SMALL|SM|S){_T1}", "S"),
    (r"ONE SIZE|\bOSFA\b|UNIVERSAL", "ONE SIZE"),
]


def parse_ppe(text: str) -> Attributes:
    """Type, material (shell and coating), size."""
    out: Attributes = {}
    kind = _first(_PPE_TYPE, text)
    if kind:
        out["type"] = kind
    work = text
    coat_material = r"(NITRILE|LATEX|POLYURETHANE|(?<![A-Z])PU(?![A-Z])|PVC|NEOPRENE)"
    coating = re.search(
        rf"(?:FOAM |SANDY )?{coat_material}\s*(?:FOAM\s*)?(?:COATED|COAT|DIPPED|DIP|PALM)"
        rf"|(?:COATED|DIPPED)\s+(?:PALM\s+)?(?:WITH\s+)?(?:FOAM |SANDY )?{coat_material}",
        work,
    )
    if coating:
        name = coating.group(1) or coating.group(2)
        name = "POLYURETHANE" if name == "PU" else name.replace("FOAM ", "").replace("SANDY ", "")
        out["coating"] = name
        work = work[: coating.start()] + " " + work[coating.end() :]
    materials = sorted({v for p, v in _PPE_MATERIALS if re.search(p, work)})
    if materials:
        out["material"] = "+".join(materials)
    sm = re.search(r"(?:SIZE|SZ)\s*[:#]?\s*(\d{1,2}(?:\.5)?)(?![\d.A-Z])", text)
    if sm:
        out["size"] = fmt(float(sm.group(1)))
    else:
        size = _first(_PPE_SIZES, text)
        if size:
            out["size"] = size
        elif out.get("type") == "GLOVE":
            num = re.search(r"(?<![\d./A-Z])([6-9]|1[0-2])(?![\d./A-Z])", text)
            if num:
                out["size"] = num.group(1)
    mil = re.search(r"(?<![\d.])(\d+(?:\.\d+)?)\s*MIL(?![A-Z])", text)
    if mil:
        out["thickness"] = f"{fmt(float(mil.group(1)))}MIL"
    cut = re.search(r"(?<![A-Z0-9])(A[1-9])(?![A-Z0-9])", text) if "CUT" in text else None
    if cut:
        out["cut_level"] = cut.group(1)
    rating = re.search(r"(?<![A-Z0-9])([NPR](?:95|99|100))(?![0-9])", text)
    if rating:
        out["rating"] = rating.group(1)
    nrr = re.search(r"NRR\s*(\d{2})(?!\d)|(?<!\d)(\d{2})\s*(?:DB\s*)?NRR", text)
    if nrr:
        out["nrr"] = nrr.group(1) or nrr.group(2)
    if re.search(r"DISPOSABLE|EXAM", text):
        out["style"] = "DISPOSABLE"
    lens = _first(
        [
            (r"CLEAR", "CLEAR"),
            (r"GRAY|GREY|SMOKE", "GRAY"),
            (r"AMBER|YELLOW", "AMBER"),
            (r"MIRROR", "MIRROR"),
            (r"SHADE\s*\d", "SHADE"),
        ],
        text,
    )
    if lens and out.get("type") in {"GLASSES", "GOGGLES", "FACE SHIELD"}:
        out["lens"] = lens
    return out


# ---------------------------------------------------------------- abrasives

_DIM_GROUP = re.compile(
    rf"(?<![\d./A-Z#-])(?P<a>{NUM})(?P<au>IN|MM)?X(?P<b>{NUM})(?P<bt>-\d{{1,2}})?(?P<bu>IN|MM)?"
    rf"(?:X(?P<c>{NUM})(?P<ct>-\d{{1,2}})?(?P<cu>IN|MM)?)?(?![\d/A-Z])"
)
_ABRASIVE_MATERIAL = [
    (r"ZIRCONIA|ZIRC|\bZA\b|\bZO\b", "ZIRCONIA"),
    (r"CERAMIC", "CERAMIC"),
    (r"SILICON CARBIDE|\bSIC\b", "SILICON CARBIDE"),
    (r"ALUMINUM OXIDE|ALUMINIUM OXIDE|\bA/O\b|\bAO\b", "ALUMINUM OXIDE"),
    (r"DIAMOND", "DIAMOND"),
    (r"\bCBN\b", "CBN"),
    (r"COBALT|\bM42\b|\bM35\b|\bHSCO\b", "COBALT"),
    (r"CARBIDE", "CARBIDE"),
    (r"\bHSS\b|HIGH SPEED STEEL", "HSS"),
    (r"BI-?METAL", "BI-METAL"),
]


def _abrasive_unit(values: list[tuple[str, str | None]]) -> str:
    units = {u for _, u in values if u}
    if "MM" in units:
        return "MM"
    if "IN" in units:
        return "IN"
    # Unitless: metric wheel diameters start at about 50 mm; imperial ones are inches.
    return "MM" if to_float(values[0][0]) >= 50 else "IN"


def _dim(value: str, unit: str) -> str:
    return f"{_num(value)}{unit}"


def _threaded(diameter: str, tpi: str) -> str:
    """Canonical threaded arbor or tap: ``5/8-11`` -> ``0.625-11``, ``#10-24`` kept."""
    head = diameter if diameter.startswith("#") else _num(diameter)
    return f"{head}-{int(tpi)}"


def parse_abrasives(text: str) -> Attributes:
    """Diameter, thickness, bore, grit, wheel type, and cutting-tool geometry."""
    out: Attributes = {}
    work = text
    insert = re.search(
        r"(?<![A-Z0-9])([CDKRSTVW][ABCNP][GMUAT][AGMNRTWX])\s*-?\s*(\d{3,6})(?!\d)", work
    )
    if insert:
        out["insert"] = f"{insert.group(1)}{insert.group(2)}"
        work = work[: insert.start()] + " " + work[insert.end() :]
    thread = re.search(
        r"(?<![\d./A-Z])(?:M(?P<md>\d+(?:\.\d+)?)X(?P<mp>\d+(?:\.\d+)?)"
        r"|(?P<d>\d+/\d+|#\d{1,2})-(?P<tpi>\d{1,2}))(?![\d/.])",
        work,
    )
    if thread and re.search(r"\bTAP\b", work):
        if thread.group("md"):
            out["thread"] = f"M{_num(thread.group('md'))}X{_num(thread.group('mp'))}"
        else:
            out["thread"] = _threaded(thread.group("d"), thread.group("tpi"))
        work = work[: thread.start()] + " " + work[thread.end() :]
    g = _DIM_GROUP.search(work)
    if g:
        vals = [(g.group("a"), g.group("au")), (g.group("b"), g.group("bu"))]
        if g.group("c"):
            vals.append((g.group("c"), g.group("cu")))
        unit = _abrasive_unit(vals)
        out["diameter"] = _dim(vals[0][0], vals[0][1] or unit)
        threaded = g.group("ct") or (None if g.group("c") else g.group("bt"))
        if threaded:
            last = vals.pop()
            out.setdefault("bore", _threaded(last[0], threaded[1:]))
            if len(vals) == 2:
                out["thickness"] = _dim(vals[1][0], vals[1][1] or unit)
        elif len(vals) == 3:
            out["thickness"] = _dim(vals[1][0], vals[1][1] or unit)
            out.setdefault("bore", _dim(vals[2][0], vals[2][1] or unit))
        else:
            second, su = vals[1]
            su = su or unit
            limit = 10.0 if su == "MM" else 0.5
            if to_float(second) >= limit:
                out.setdefault("bore", _dim(second, su))
            else:
                out["thickness"] = _dim(second, su)
        work = work[: g.start()] + " " + work[g.end() :]
    if "bore" not in out:
        b = re.search(
            rf"(?<![\d./A-Z])(?P<v>{NUM})(?P<t>-\d{{1,2}})?(?P<u>IN|MM)?\s*"
            rf"(?:ARBOR|BORE|HOLE|SHANK|SHK){_E}"
            rf"|(?:ARBOR|BORE|HOLE|SHANK|SHK)\s*[:=]?\s*(?P<v2>{NUM})(?P<t2>-\d{{1,2}})?(?P<u2>IN|MM)?"
            rf"|(?<![\d./A-Z#-])(?P<v3>\d+/\d+)(?P<t3>-\d{{1,2}})(?![\d/.])",
            work,
        )
        if b:
            n = next(k for k in ("", "2", "3") if b.group("v" + k))
            v, t = b.group("v" + n), b.group("t" + n)
            u = b.group("u" + n) if n != "3" else None
            if t:
                out["bore"] = _threaded(v, t[1:])
            else:
                out["bore"] = _dim(v, u or _abrasive_unit([(v, None)]))
            work = work[: b.start()] + " " + work[b.end() :]
    if "diameter" not in out:
        named = re.search(rf"(?:DIAMETER|DIA|OD)\s*[:=]?\s*(?P<v>{NUM})(?P<u>IN|MM)", work)
        # Otherwise the largest stated size that is not a depth, length or width
        # qualifier ("2IN DEEP"), so word order never changes the reading.
        sizes = [
            (to_float(m.group("v")) * (25.4 if m.group("u") == "IN" else 1.0), m.start(), m)
            for m in re.finditer(
                rf"(?<![\d./A-Z#-])(?P<v>{NUM})(?P<u>IN|MM){_E}(?!\s*(?:DEEP|DEPTH|LONG|WIDE))",
                work,
            )
        ]
        d = named or (max(sizes, key=lambda s: (s[0], -s[1]))[2] if sizes else None)
        if d:
            out["diameter"] = _dim(d.group("v"), d.group("u"))
        else:
            d2 = re.search(r"(?<![\d./A-Z#-])(?P<v>\d+-\d+/\d+|\d+/\d+|\d*\.\d+)(?![\d/.])", work)
            if d2 and not re.search(r"GRIT", work[d2.end() : d2.end() + 6]):
                out["diameter"] = _dim(d2.group("v"), "IN")
    grit = re.search(
        r"(?<![\d.])(\d{2,4})\s*-?\s*(?:GRIT|G)(?![A-Z0-9])|GRIT\s*[:#]?\s*P?(\d{2,4})(?!\d)|(?<![A-Z0-9])P(\d{2,4})(?![\d])",
        work,
    )
    if grit:
        out["grit"] = str(int(grit.group(1) or grit.group(2) or grit.group(3)))
    else:
        word = _first(
            [
                (r"EXTRA COARSE", "EXTRA COARSE"),
                (r"COARSE", "COARSE"),
                (r"EXTRA FINE|VERY FINE", "EXTRA FINE"),
                (r"\bFINE\b", "FINE"),
                (r"\bMEDIUM\b", "MEDIUM"),
            ],
            work,
        )
        if word:
            out["grit_grade"] = word
    wheel = re.search(r"(?:TYPE|(?<![A-Z0-9])T)\s*-?\s*(1|27|28|29|41|42|11|6)(?![\d.])", work)
    if wheel:
        out["type"] = f"T{wheel.group(1)}"
    teeth = re.search(r"(?<![\d.])(\d{1,3}(?:/\d{1,2})?)\s*(?:T|TOOTH|TEETH|TPI)(?![A-Z0-9])", work)
    if teeth:
        out["teeth"] = teeth.group(1)
    flutes = re.search(r"(?<![\d.])(\d)\s*-?\s*(?:FL|FLT|FLUTES?)(?![A-Z0-9])", work)
    if flutes:
        out["flutes"] = flutes.group(1)
    angle = re.search(r"(?<![\d.])(\d{2,3})\s*(?:DEG|DEGREE)S?", work)
    if angle:
        out["angle"] = angle.group(1)
    material = _first(_ABRASIVE_MATERIAL, text)
    if material:
        out["material"] = material
    kind = _first(
        [
            (r"FLAP DIS[CK]", "FLAP DISC"),
            (r"CUT-?OFF|CUTOFF|CUTTING WHEEL", "CUT-OFF WHEEL"),
            (r"GRINDING WHEEL|DEPRESSED CENTER", "GRINDING WHEEL"),
            (r"FIBER DIS[CK]|RESIN FIBER", "FIBER DISC"),
            (r"\bBELT\b", "BELT"),
            (r"END ?MILL", "END MILL"),
            (r"DRILL", "DRILL"),
            (r"\bTAP\b", "TAP"),
            (r"BLADE", "BLADE"),
            (r"WIRE (?:WHEEL|BRUSH|CUP)", "WIRE BRUSH"),
            (r"SANDING DIS[CK]|\bPSA\b|HOOK AND LOOP", "SANDING DISC"),
            (r"SHEET", "SHEET"),
        ],
        text,
    )
    if kind:
        out["kind"] = kind
    return out


# ----------------------------------------------------------------- generic

_GENERIC_UNITS: dict[str, str] = {
    "MM": "MM",
    "CM": "CM",
    "M": "M",
    "METER": "M",
    "METERS": "M",
    "METRE": "M",
    "IN": "IN",
    "INCH": "IN",
    "INCHES": "IN",
    "FT": "FT",
    "FOOT": "FT",
    "FEET": "FT",
    "YD": "YD",
    "KG": "KG",
    "G": "G",
    "GM": "G",
    "GRAM": "G",
    "LB": "LB",
    "LBS": "LB",
    "POUND": "LB",
    "#": "LB",
    "OZ": "OZ",
    "OUNCE": "OZ",
    "L": "L",
    "LT": "L",
    "LITER": "L",
    "LITRE": "L",
    "ML": "ML",
    "GAL": "GAL",
    "GALLON": "GAL",
    "QT": "QT",
    "QUART": "QT",
    "MIL": "MIL",
    "GA": "GA",
    "GAUGE": "GA",
    "AWG": "AWG",
    "V": "V",
    "VAC": "V",
    "VDC": "V",
    "VOLT": "V",
    "A": "A",
    "AMP": "A",
    "W": "W",
    "WATT": "W",
    "KW": "KW",
    "HP": "HP",
    "PSI": "PSI",
    "BAR": "BAR",
    "DEG": "DEG",
    "F": "F",
    "RPM": "RPM",
    "MICRON": "MICRON",
    "GSM": "GSM",
    "PLY": "PLY",
    "%": "%",
    "CFM": "CFM",
    "GPM": "GPM",
    "TON": "TON",
    "PCT": "%",
}
_GENERIC_UNIT_RE = "|".join(
    re.escape(u) for u in sorted(_GENERIC_UNITS, key=lambda u: (-len(u), u))
)
_GENERIC_GROUP = re.compile(
    rf"(?<![\d./A-Z])(?P<g>{NUM}\s*(?:(?:{_GENERIC_UNIT_RE})\s*)?(?:X\s*{NUM}\s*"
    rf"(?:{_GENERIC_UNIT_RE})?)+)(?![A-Z0-9])"
)
_GENERIC_PART = re.compile(rf"(?P<v>{NUM})\s*(?P<u>{_GENERIC_UNIT_RE})?")
_GENERIC_TOKEN = re.compile(rf"(?<![\d./A-Z])(?P<v>{NUM})\s*(?P<u>{_GENERIC_UNIT_RE})(?![A-Z0-9])")
# Brand names that read like a quantity and a unit.
_GENERIC_STOP = frozenset({"3M"})


def _group_tokens(text: str) -> list[str]:
    """One token for a same-unit group; separate tokens when the units differ."""
    parts = [
        (m.group("v"), _GENERIC_UNITS.get(m.group("u") or "", ""))
        for m in _GENERIC_PART.finditer(text)
    ]
    units = {u for _, u in parts if u}
    if len(units) <= 1:
        unit = units.pop() if units else ""
        return ["X".join(_num(v) for v, _ in parts) + unit]
    filled: list[str] = []
    following = ""
    for v, u in reversed(parts):
        following = u or following
        filled.append(_num(v) + following)
    return filled


def numeric_tokens(text: str) -> frozenset[str]:
    """Every numeric-and-unit token (and every ``AxB`` dimension group), canonical.

    ``1/2IN`` and ``0.5 IN`` both give ``0.5IN``; ``12X10X8IN`` and
    ``12INX10INX8IN`` both give ``12X10X8IN``.
    """
    tokens: set[str] = set()
    pieces: list[str] = []
    last = 0
    for m in _GENERIC_GROUP.finditer(text):
        tokens.update(_group_tokens(m.group("g")))
        pieces.append(text[last : m.start()])
        last = m.end()
    pieces.append(text[last:])
    for m in _GENERIC_TOKEN.finditer(" ".join(pieces)):
        token = _num(m.group("v")) + _GENERIC_UNITS[m.group("u")]
        if token not in _GENERIC_STOP:
            tokens.add(token)
    return frozenset(tokens)


def bare_numbers(text: str) -> frozenset[str]:
    """Whole tokens that are plain numbers (``46``, ``1/2``, ``1-1/2``), canonical."""
    out = set()
    for token in re.split(r"[\s,;()]+", text):
        if re.fullmatch(NUM, token):
            out.add(_num(token))
    return frozenset(out)


def parse_generic(text: str) -> Attributes:
    """One attribute per numeric-and-unit token, keyed by the token."""
    return {t: t for t in sorted(numeric_tokens(text))}


# ------------------------------------------------------------------ dispatch

_PARSERS: dict[str, Callable[[str], Attributes]] = {
    "fasteners": parse_fasteners,
    "bearings": parse_bearings,
    "pvf": parse_pvf,
    "electrical": parse_electrical,
    "ppe": parse_ppe,
    "abrasives": parse_abrasives,
    "generic": parse_generic,
}


def parse_attributes(normalised: str, family: str | None) -> Attributes:
    """Parse an I0-normalised description with the family's parser."""
    parser = _PARSERS.get((family or "generic").strip().lower(), parse_generic)
    return parser(normalised or "")


def parse_description(
    description: str | None,
    family: str | None,
    abbreviations: Mapping[str, str] | None = None,
) -> Attributes:
    """Strip pack tokens, apply I0, then parse with the family's parser."""
    return parse_attributes(
        normalise_description(strip_pack_tokens(description), abbreviations), family
    )


# ---------------------------------------------------------------- compare


@dataclass(frozen=True)
class Comparison:
    """Outcome of comparing two attribute dictionaries (PRD 4.4 veto rules)."""

    family: str
    agreements: tuple[tuple[str, str], ...]
    conflicts: tuple[tuple[str, str, str], ...]
    subset_only: bool = False

    @property
    def veto(self) -> bool:
        """A hard veto: any conflict."""
        return bool(self.conflicts)

    @property
    def critical_agreements(self) -> int:
        """Agreeing attributes that count towards the automatic-match rule."""
        if self.family == "generic":
            return len(self.agreements)
        keys = CRITICAL_KEYS.get(self.family, frozenset())
        return sum(1 for key, _ in self.agreements if key in keys)

    @property
    def auto_eligible(self) -> bool:
        """No veto, no subset-only case, and at least two critical attributes agree."""
        return not self.veto and not self.subset_only and self.critical_agreements >= 2


def compare(a: Mapping[str, str], b: Mapping[str, str], family: str | None) -> Comparison:
    """Compare parsed attributes under the PRD 4.4 veto rules.

    Parser families: a conflict is a key extracted on both sides with different
    values; a key missing on one side is not a conflict. For bearings, once the
    base designation is present on both sides, a missing seal, clearance or
    other suffix reads as "none" (the PRD attribute is the full designation).

    Generic: identical token sets agree; a strict subset is review only; any
    other difference is a hard veto.
    """
    fam = (family or "generic").strip().lower()
    if fam not in CRITICAL_KEYS:
        sa, sb = set(a), set(b)
        agreements = tuple((t, t) for t in sorted(sa & sb))
        if sa == sb:
            return Comparison("generic", agreements, ())
        if sa < sb or sb < sa:
            return Comparison("generic", agreements, (), subset_only=True)
        conflicts = (("numeric tokens", ", ".join(sorted(sa - sb)), ", ".join(sorted(sb - sa))),)
        return Comparison("generic", agreements, conflicts)
    left, right = dict(a), dict(b)
    if fam == "bearings" and "designation" in left and "designation" in right:
        for key in _BEARING_FULL:
            if key in left or key in right:
                left.setdefault(key, "NONE")
                right.setdefault(key, "NONE")
        for side in (left, right):
            if side.get("seal") == "OPEN":
                side["seal"] = "NONE"
    agree: list[tuple[str, str]] = []
    conflict: list[tuple[str, str, str]] = []
    for key in sorted(set(left) & set(right)):
        if left[key] == right[key]:
            if key in a and key in b:
                agree.append((key, left[key]))
        else:
            conflict.append((key, left[key], right[key]))
    return Comparison(fam, tuple(agree), tuple(conflict))

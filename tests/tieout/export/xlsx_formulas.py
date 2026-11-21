"""A small evaluator for the workbook's formulas, so the tests need no Excel.

It covers exactly the grammar the workbook uses: numbers, strings, A1 cell and
range references (optionally sheet-qualified), defined names, the operators
``+ - * / ^ = <> < > <= >=`` and the functions ``SUM``, ``SUMIFS``,
``SUMPRODUCT``, ``IF``, ``AND``, ``MAX``, ``MIN``, ``ABS``, ``INDEX`` and
``MATCH`` (exact match). Ranges evaluate to numpy arrays, so array arithmetic
inside ``SUMPRODUCT`` broadcasts as in Excel. Anything else raises
:class:`FormulaError`, which is how the tests catch a formula outside the
grammar, an unknown sheet or name, or a circular reference.
"""

from __future__ import annotations

import io
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import numpy as np
import openpyxl
from openpyxl.utils import column_index_from_string

FUNCTIONS = {"SUM", "SUMIFS", "SUMPRODUCT", "IF", "AND", "MAX", "MIN", "ABS", "INDEX", "MATCH"}
EXCEL_ERRORS = ("#REF!", "#NAME?", "#VALUE!", "#DIV/0!", "#N/A", "#NUM!", "#NULL!")

_TOKEN = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<str>"(?:[^"]|"")*")
  | (?P<ref>(?:(?:'[^']+'|[A-Za-z_][A-Za-z0-9_]*)!)?\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?)
      (?![A-Za-z0-9_(])
  | (?P<num>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)
  | (?P<name>[A-Za-z_][A-Za-z0-9_.]*)
  | (?P<op><=|>=|<>|[-+*/^=<>(),])
    """,
    re.VERBOSE,
)
_CELL = re.compile(r"\$?([A-Z]{1,3})\$?(\d+)")


class FormulaError(Exception):
    """A formula the evaluator cannot evaluate."""


@dataclass(frozen=True)
class Ref:
    sheet: str
    r1: int
    c1: int
    r2: int
    c2: int

    @property
    def single(self) -> bool:
        return self.r1 == self.r2 and self.c1 == self.c2


def tokenize(formula: str) -> list[tuple[str, str]]:
    text = formula[1:] if formula.startswith("=") else formula
    out, pos = [], 0
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if not match:
            raise FormulaError(f"cannot tokenise {text[pos:]!r} in {formula!r}")
        pos = match.end()
        kind = match.lastgroup
        if kind != "ws":
            out.append((kind, match.group(kind)))
    return out


def parse_ref(text: str, default_sheet: str) -> Ref:
    sheet = default_sheet
    if "!" in text:
        sheet, text = text.rsplit("!", 1)
        sheet = sheet.strip("'")
    parts = text.split(":")
    cells = []
    for part in parts:
        match = _CELL.fullmatch(part)
        if not match:
            raise FormulaError(f"bad reference {text!r}")
        cells.append((int(match.group(2)), column_index_from_string(match.group(1))))
    (r1, c1), (r2, c2) = cells[0], cells[-1]
    return Ref(sheet, r1, c1, r2, c2)


class _Parser:
    """Recursive descent over the tokens into nested tuples."""

    _LEVELS = (("=", "<>", "<", ">", "<=", ">="), ("+", "-"), ("*", "/"), ("^",))

    def __init__(self, tokens: list[tuple[str, str]], sheet: str) -> None:
        self.tokens, self.pos, self.sheet = tokens, 0, sheet

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self, value: str | None = None) -> tuple[str, str]:
        token = self.peek()
        if token is None or (value is not None and token[1] != value):
            raise FormulaError(f"expected {value!r}, got {token!r}")
        self.pos += 1
        return token

    def parse(self) -> Any:
        node = self.binary(0)
        if self.peek() is not None:
            raise FormulaError(f"trailing tokens {self.tokens[self.pos :]}")
        return node

    def binary(self, level: int) -> Any:
        if level == len(self._LEVELS):
            return self.unary()
        node = self.binary(level + 1)
        while (token := self.peek()) and token[0] == "op" and token[1] in self._LEVELS[level]:
            self.take()
            node = ("bin", token[1], node, self.binary(level + 1))
        return node

    def unary(self) -> Any:
        token = self.peek()
        if token and token == ("op", "-"):
            self.take()
            return ("neg", self.unary())
        if token and token == ("op", "+"):
            self.take()
            return self.unary()
        return self.atom()

    def atom(self) -> Any:
        kind, text = self.take()
        if kind == "num":
            return ("num", float(text))
        if kind == "str":
            return ("str", text[1:-1].replace('""', '"'))
        if kind == "ref":
            return ("ref", parse_ref(text, self.sheet))
        if kind == "name":
            if self.peek() == ("op", "("):
                self.take("(")
                args = []
                if self.peek() != ("op", ")"):
                    args.append(self.binary(0))
                    while self.peek() == ("op", ","):
                        self.take(",")
                        args.append(self.binary(0))
                self.take(")")
                if text.upper() not in FUNCTIONS:
                    raise FormulaError(f"unsupported function {text}")
                return ("call", text.upper(), args)
            return ("name", text)
        if (kind, text) == ("op", "("):
            node = self.binary(0)
            self.take(")")
            return node
        raise FormulaError(f"unexpected token {text!r}")


def _numeric(value: Any) -> Any:
    """Numbers as floats; blanks as 0; arrays elementwise."""
    if isinstance(value, np.ndarray):
        if value.dtype.kind == "f":
            return value
        flat = [_numeric(v) for v in value.ravel()]
        return np.array(flat, dtype=float).reshape(value.shape)
    if value is None:
        return 0.0
    if isinstance(value, bool | np.bool_):
        return float(value)
    if isinstance(value, int | float | np.integer | np.floating):
        return float(value)
    raise FormulaError(f"text {value!r} in arithmetic")


def _equal(a: Any, b: Any) -> bool:
    if isinstance(a, str) or isinstance(b, str):
        return str(a if a is not None else "").lower() == str(b if b is not None else "").lower()
    return _numeric(a) == _numeric(b)


def _key(value: Any) -> Any:
    """What SUMIFS equality compares: text case-insensitively, numbers as floats."""
    if isinstance(value, str):
        return ("text", value.lower())
    if value is None:
        return ("blank",)
    return ("number", float(value))


def _compare(op: str, a: Any, b: Any) -> Any:
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        if op in ("=", "<>"):
            fn = np.frompyfunc(_equal, 2, 1)
            result = fn(a, b).astype(bool)
            return result if op == "=" else ~result
        a, b = _numeric(a), _numeric(b)
    elif op in ("=", "<>"):
        return _equal(a, b) if op == "=" else not _equal(a, b)
    else:
        a, b = _numeric(a), _numeric(b)
    return {"<": np.less, ">": np.greater, "<=": np.less_equal, ">=": np.greater_equal}[op](a, b)


def _flat(values: list[Any]) -> Iterator[Any]:
    for value in values:
        if isinstance(value, np.ndarray):
            yield from value.ravel().tolist()
        else:
            yield value


class Workbook:
    """Formulas and cached values of an ``.xlsx``, with on-demand evaluation."""

    def __init__(self, data: bytes) -> None:
        formulas = openpyxl.load_workbook(io.BytesIO(data), data_only=False)
        cached = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        self.sheets = list(formulas.sheetnames)
        self.cells: dict[tuple[str, int, int], Any] = {}
        self.cached: dict[tuple[str, int, int], Any] = {}
        for ws in formulas.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if cell.value is not None:
                        self.cells[(ws.title, cell.row, cell.column)] = cell.value
        for ws in cached.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if cell.value is not None:
                        self.cached[(ws.title, cell.row, cell.column)] = cell.value
        self.names: dict[str, Ref] = {}
        for name, defined in formulas.defined_names.items():
            self.names[name] = parse_ref(defined.attr_text, "")
        self.tables = {
            name: (ws.title, ref) for ws in formulas.worksheets for name, ref in ws.tables.items()
        }
        self.overrides: dict[tuple[str, int, int], Any] = {}
        self._parsed: dict[tuple[str, str], Any] = {}
        self.reset()

    # -------------------------------------------------------------- access

    def reset(self) -> None:
        self._memo: dict[tuple[str, int, int], Any] = {}
        self._ranges: dict[Ref, np.ndarray] = {}
        self._busy: set[tuple[str, int, int]] = set()
        self._numbers: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._indexes: dict[int, tuple[np.ndarray, dict[Any, np.ndarray]]] = {}

    def numbers(self, value: Any) -> Any:
        """``_numeric`` with the conversion of each range cached."""
        if not isinstance(value, np.ndarray) or value.dtype.kind == "f":
            return _numeric(value)
        cached = self._numbers.get(id(value))
        if cached is None or cached[0] is not value:
            cached = (value, _numeric(value))
            self._numbers[id(value)] = cached
        return cached[1]

    def matches(self, crange: np.ndarray, criterion: Any) -> np.ndarray:
        """Positions of ``crange`` equal to ``criterion`` (SUMIFS equality), via a cached index."""
        cached = self._indexes.get(id(crange))
        if cached is None or cached[0] is not crange:
            groups: dict[Any, list[int]] = {}
            for i, item in enumerate(crange.ravel().tolist()):
                groups.setdefault(_key(item), []).append(i)
            cached = (crange, {k: np.array(v, dtype=np.int64) for k, v in groups.items()})
            self._indexes[id(crange)] = cached
        mask = np.zeros(crange.size, dtype=bool)
        mask[cached[1].get(_key(criterion), np.zeros(0, dtype=np.int64))] = True
        return mask.reshape(crange.shape)

    def formula_cells(self) -> Iterator[tuple[tuple[str, int, int], str]]:
        for key, value in self.cells.items():
            if isinstance(value, str) and value.startswith("="):
                yield key, value

    def name_cell(self, name: str) -> tuple[str, int, int]:
        ref = self.names[name]
        return (ref.sheet, ref.r1, ref.c1)

    def cached_name(self, name: str) -> Any:
        return self.cached.get(self.name_cell(name))

    def set_value(self, key: tuple[str, int, int], value: Any) -> None:
        self.overrides[key] = value
        self.reset()

    def table_rows(self, name: str, *, evaluated: bool = False) -> list[dict[str, Any]]:
        """An Excel table as dictionaries keyed by header (cached or evaluated values)."""
        sheet, ref = self.tables[name]
        rng = parse_ref(ref, sheet)
        headers = [self.cells.get((sheet, rng.r1, c)) for c in range(rng.c1, rng.c2 + 1)]
        rows = []
        for r in range(rng.r1 + 1, rng.r2 + 1):
            get: Callable[[tuple[str, int, int]], Any] = (
                self.value if evaluated else self.cached.get
            )
            rows.append(
                {
                    h: get((sheet, r, c))
                    for h, c in zip(headers, range(rng.c1, rng.c2 + 1), strict=True)
                }
            )
        return rows

    # -------------------------------------------------------------- evaluation

    def parsed(self, sheet: str, formula: str) -> Any:
        key = (sheet, formula)
        if key not in self._parsed:
            self._parsed[key] = _Parser(tokenize(formula), sheet).parse()
        return self._parsed[key]

    def value(self, key: tuple[str, int, int]) -> Any:
        if key in self.overrides:
            return self.overrides[key]
        raw = self.cells.get(key)
        if not (isinstance(raw, str) and raw.startswith("=")):
            return raw
        if key in self._memo:
            return self._memo[key]
        if key in self._busy:
            raise FormulaError(f"circular reference at {key}")
        self._busy.add(key)
        try:
            result = self.evaluate(self.parsed(key[0], raw))
        finally:
            self._busy.discard(key)
        if isinstance(result, np.ndarray):
            if result.size != 1:
                raise FormulaError(f"{key} evaluates to an array")
            result = result.ravel()[0]
        if isinstance(result, np.generic):
            result = result.item()
        self._memo[key] = result
        return result

    def range(self, ref: Ref) -> np.ndarray:
        if ref.sheet not in self.sheets:
            raise FormulaError(f"unknown sheet {ref.sheet!r}")
        if ref not in self._ranges:
            values = [
                [self.value((ref.sheet, r, c)) for c in range(ref.c1, ref.c2 + 1)]
                for r in range(ref.r1, ref.r2 + 1)
            ]
            array = np.empty((len(values), len(values[0])), dtype=object)
            for i, row in enumerate(values):
                for j, v in enumerate(row):
                    array[i, j] = v
            self._ranges[ref] = array[:, 0] if array.shape[1] == 1 else array
        return self._ranges[ref]

    def resolve(self, ref: Ref) -> Any:
        if ref.sheet not in self.sheets:
            raise FormulaError(f"unknown sheet {ref.sheet!r}")
        if ref.single:
            return self.value((ref.sheet, ref.r1, ref.c1))
        return self.range(ref)

    def evaluate(self, node: Any) -> Any:
        kind = node[0]
        if kind in ("num", "str"):
            return node[1]
        if kind == "ref":
            return self.resolve(node[1])
        if kind == "name":
            if node[1] not in self.names:
                raise FormulaError(f"unknown name {node[1]!r}")
            return self.resolve(self.names[node[1]])
        if kind == "neg":
            return -_numeric(self.evaluate(node[1]))
        if kind == "bin":
            op, a, b = node[1], self.evaluate(node[2]), self.evaluate(node[3])
            if op in ("=", "<>", "<", ">", "<=", ">="):
                return _compare(op, a, b)
            a, b = self.numbers(a), self.numbers(b)
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            if op == "/":
                if np.any(np.asarray(b) == 0):
                    raise FormulaError("division by zero")
                return a / b
            return a**b
        if kind == "call":
            return self.call(node[1], node[2])
        raise FormulaError(f"unknown node {node!r}")

    def call(self, name: str, args: list[Any]) -> Any:
        if name == "IF":
            condition = self.evaluate(args[0])
            branch = args[1] if bool(condition) else (args[2] if len(args) > 2 else ("num", 0.0))
            return self.evaluate(branch)
        values = [self.evaluate(a) for a in args]
        if name == "SUM":
            if all(isinstance(v, np.ndarray) for v in values):
                try:
                    return float(sum(np.sum(self.numbers(v)) for v in values))
                except FormulaError:
                    pass
            return float(sum(_numeric(v) for v in _flat(values) if not isinstance(v, str)))
        if name == "SUMPRODUCT":
            arrays = [self.numbers(v) for v in values]
            product = arrays[0]
            for array in arrays[1:]:
                product = product * array
            return float(np.sum(product))
        if name == "SUMIFS":
            total = np.asarray(values[0])
            mask = np.ones(total.shape, dtype=bool)
            for crange, criterion in zip(values[1::2], values[2::2], strict=True):
                if isinstance(criterion, str) and (
                    criterion[:1] in "<>=" or set("*?~") & set(criterion)
                ):
                    raise FormulaError(f"criterion {criterion!r} would be read as an operator")
                mask &= self.matches(np.asarray(crange), criterion)
            picked = [v for v in total[mask].tolist() if not isinstance(v, str)]
            return float(sum(_numeric(v) for v in picked))
        if name == "AND":
            return all(bool(v) for v in _flat(values))
        if name in ("MAX", "MIN"):
            numbers = [_numeric(v) for v in _flat(values) if v is not None]
            return float(max(numbers) if name == "MAX" else min(numbers))
        if name == "ABS":
            return abs(_numeric(values[0]))
        if name == "MATCH":
            key, array = values[0], np.asarray(values[1]).ravel()
            if len(values) < 3 or _numeric(values[2]) != 0:
                raise FormulaError("only exact MATCH is supported")
            for i, item in enumerate(array.tolist()):
                if _equal(item, key):
                    return float(i + 1)
            raise FormulaError(f"MATCH found no {key!r}")
        if name == "INDEX":
            array = np.asarray(values[0])
            row = int(_numeric(values[1])) - 1
            return array.ravel()[row] if array.ndim == 1 else array[row, 0]
        raise FormulaError(f"unsupported function {name}")


def names_in(formula: str) -> set[str]:
    """Defined names a formula refers to (functions excluded)."""
    tokens = tokenize(formula)
    found = set()
    for i, (kind, text) in enumerate(tokens):
        if kind == "name" and not (i + 1 < len(tokens) and tokens[i + 1] == ("op", "(")):
            found.add(text)
    return found


def sheets_in(formula: str) -> set[str]:
    """Sheets a formula refers to explicitly."""
    return {parse_ref(t, "").sheet for k, t in tokenize(formula) if k == "ref" and "!" in t}


def close(a: float, b: float, cents: float = 0.01) -> bool:
    return abs(float(a) - float(b)) <= cents


def relative_close(a: float, b: float) -> bool:
    """Within 1e-6 x max(1, |b|), the LibreOffice tolerance of PRD 7.1."""
    return abs(float(a) - float(b)) <= 1e-6 * max(1.0, abs(float(b)))

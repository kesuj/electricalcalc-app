"""Common result container so every calculation reports inputs, method, outputs,
assumptions and warnings in the same auditable shape (used by UI, reports and AI)."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any


class ValidationError(ValueError):
    """Raised when calculation inputs are missing, out of range or inconsistent."""


@dataclass
class Quantity:
    value: float | int | str
    unit: str = ""
    label: str = ""

    def fmt(self, digits: int = 4) -> str:
        v = self.value
        if isinstance(v, float):
            v = f"{v:,.{digits}g}" if abs(v) < 1e6 else f"{v:,.0f}"
        return f"{v} {self.unit}".strip()


@dataclass
class CalcResult:
    name: str
    inputs: dict[str, Quantity]
    outputs: dict[str, Quantity]
    equations: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CalcResult":
        d = dict(d)
        d["inputs"] = {k: Quantity(**v) for k, v in d["inputs"].items()}
        d["outputs"] = {k: Quantity(**v) for k, v in d["outputs"].items()}
        return cls(**d)

    def out(self, key: str) -> float:
        return self.outputs[key].value  # type: ignore[return-value]


def require_positive(name: str, value: float | None, allow_zero: bool = False) -> float:
    if value is None:
        raise ValidationError(f"{name} is required.")
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{name} must be a number.") from None
    if math.isnan(v) or math.isinf(v):
        raise ValidationError(f"{name} must be a finite number.")
    if v < 0 or (v == 0 and not allow_zero):
        raise ValidationError(f"{name} must be {'zero or ' if allow_zero else ''}greater than zero.")
    return v


def require_range(name: str, value: float | None, lo: float, hi: float) -> float:
    v = require_positive(name, value, allow_zero=lo <= 0)
    if not lo <= v <= hi:
        raise ValidationError(f"{name} must be between {lo} and {hi} (got {v}).")
    return v

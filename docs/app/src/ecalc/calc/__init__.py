"""Deterministic engineering calculation layer. No AI code may live in this package."""

from .result import CalcResult, Quantity, ValidationError

__all__ = ["CalcResult", "Quantity", "ValidationError"]

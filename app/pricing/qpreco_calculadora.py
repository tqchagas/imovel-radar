"""Application adapter for the standalone QuintoAndar valuation client."""

from __future__ import annotations

from typing import Any, Callable

from app.core.http_client import PortalBlocked as AppPortalBlocked
from app.core.http_client import request as default_request
from quintoandar import QuintoAndarClient
from quintoandar.errors import EstimateUnavailable, PortalBlocked
from quintoandar.valuation import (
    Comparables,
    Estimate,
    EstimateInput,
    SoldComparable,
)

QprecoUnavailable = EstimateUnavailable


def fetch_estimate(
    entrada: EstimateInput,
    *,
    request_fn: Callable[..., Any] = default_request,
) -> Estimate:
    try:
        return QuintoAndarClient(request_fn).estimate(entrada)
    except PortalBlocked as error:
        raise AppPortalBlocked(str(error)) from error


def fetch_comparables(
    entrada: EstimateInput,
    estimate: Estimate,
    *,
    request_fn: Callable[..., Any] = default_request,
) -> Comparables:
    try:
        return QuintoAndarClient(request_fn).comparables(entrada, estimate)
    except PortalBlocked as error:
        raise AppPortalBlocked(str(error)) from error


__all__ = [
    "Comparables", "Estimate", "EstimateInput", "QprecoUnavailable",
    "SoldComparable", "fetch_comparables", "fetch_estimate",
]

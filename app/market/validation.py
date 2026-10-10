"""Validation and normalization for provider supplied OHLCV history."""
from __future__ import annotations

import math
from typing import Any

import pandas as pd


def validate_ohlcv_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    """Return normalized unique price bars, or an error without partial acceptance."""
    if not isinstance(rows, list) or not rows:
        return [], "Historical data contained no price bars."

    normalized: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            return [], f"Historical bar {index} is not a record."
        stamp = row.get("Date") or row.get("Datetime") or row.get("date") or row.get("datetime")
        if stamp is None:
            return [], f"Historical bar {index} has no timestamp."
        try:
            parsed = pd.Timestamp(stamp)
            if pd.isna(parsed):
                raise ValueError
            if parsed.tzinfo is not None:
                parsed = parsed.tz_convert("UTC").tz_localize(None)
            bar_at = parsed.to_pydatetime()
        except (TypeError, ValueError, OverflowError):
            return [], f"Historical bar {index} has an invalid timestamp."

        values: dict[str, float | None] = {}
        for key, aliases, required in (
            ("open", ("Open", "open"), True),
            ("high", ("High", "high"), True),
            ("low", ("Low", "low"), True),
            ("close", ("Close", "close"), True),
            ("adj_close", ("Adj Close", "Adj_Close", "adj_close"), False),
            ("volume", ("Volume", "volume"), True),
        ):
            raw = next((row[name] for name in aliases if name in row), None)
            if raw is None and not required:
                values[key] = None
                continue
            try:
                number = float(raw)
                if not math.isfinite(number):
                    raise ValueError
            except (TypeError, ValueError, OverflowError):
                return [], f"Historical bar {index} has a missing or nonnumeric {key}."
            values[key] = number

        opening, high, low, close, volume = (values[name] for name in ("open", "high", "low", "close", "volume"))
        if min(opening, high, low, close) <= 0 or volume < 0:
            return [], f"Historical bar {index} has a nonpositive price or negative volume."
        if high < max(opening, close, low) or low > min(opening, close, high):
            return [], f"Historical bar {index} violates OHLC consistency."

        identity = (bar_at.isoformat(), str(row.get("interval", "")))
        result = {"bar_at": bar_at, **values}
        if identity in seen:
            if seen[identity] != result:
                return [], f"Historical data contains conflicting duplicate bars at {bar_at.isoformat()}."
            continue
        seen[identity] = result
        normalized.append(result)

    return normalized, None

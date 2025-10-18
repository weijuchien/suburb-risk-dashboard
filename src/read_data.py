from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import json
import re

import pandas as pd
import requests

RISK_ENDPOINT = "https://www.microburbs.com.au/report_generator/api/suburb/risk"


@dataclass
class RiskRecord:
    """Typed representation of a single risk metric row."""

    area_level: str
    area_name: str
    name: str
    value_raw: str
    value_unit: Optional[str]
    value: Optional[float]
    value_kind: str


def _coerce_float(value: str) -> Optional[float]:

    if value is None:
        return None

    stripped = value.strip()
    if stripped in {"", "-", "NA", "N/A"}:
        return None

    match = re.search(r"-?\d+(?:\.\d+)?", stripped)
    if not match:
        return None

    number = float(match.group(0))
    if stripped.endswith("%"):
        return number / 100
    return number


def _infer_value_kind(value: str) -> str:
    """Infer a simple type descriptor for a raw value string."""
    if not value or not value.strip():
        return "missing"
    stripped = value.strip()
    if stripped.endswith("%"):
        return "proportion"
    if re.fullmatch(r"-?\d+(?:\.\d+)?", stripped):
        return "numeric"
    return "categorical"


def normalise_payload(records):
    """Convert raw payload rows into RiskRecord objects."""
    results: List[RiskRecord] = []
    for row in records:
        raw_value = row.get("value", "") or ""
        record = RiskRecord(
            area_level=row.get("area_level", ""),
            area_name=row.get("area_name", ""),
            name=row.get("name", ""),
            value_raw=raw_value,
            value_unit=row.get("value_unit"),
            value=_coerce_float(raw_value),
            value_kind=_infer_value_kind(raw_value),
        )
        results.append(record)
    return results


def fetch_risk_data(
    suburb_name,
    *,
    session=None,
    timeout=10,
    fallback_path="src/default_risk_data.json",
):
    """Fetch risk data for the requested suburb."""

    suburb = suburb_name.replace(" ", "+")

    params = {"suburb": suburb} if suburb else None
    headers = {
        "Authorization": "Bearer test",
        "Content-Type": "application/json"
    }

    client = session or requests

    try:
        response = client.get(RISK_ENDPOINT, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()

        # Check if response is JSON
        content_type = response.headers.get('content-type', '').lower()
        if 'application/json' not in content_type:
            raise ValueError(f"API returned HTML instead of JSON. Content-Type: {content_type}")

        payload = response.json()
    except (requests.RequestException, json.JSONDecodeError) as exc:
        if fallback_path:
            return load_risk_data_from_file(fallback_path)
        raise ValueError(f"Could not fetch risk data: {exc}") from exc

    if "results" not in payload:
        raise ValueError("Unexpected payload from risk endpoint: 'results' missing")

    return normalise_payload(payload["results"])


def load_risk_data_from_file(path: str) -> List[RiskRecord]:
    """Load risk records from a JSON file with the sandbox response format."""
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return normalise_payload(payload.get("results", []))


def risk_records_to_frame(records: Iterable[RiskRecord]) -> pd.DataFrame:
    """Convert a sequence of RiskRecord objects into a pandas DataFrame."""
    as_dicts = (
        {
            "area_level": record.area_level,
            "area_name": record.area_name,
            "metric": record.name,
            "value": record.value,
            "value_raw": record.value_raw,
            "value_unit": record.value_unit,
            "value_kind": record.value_kind,
        }
        for record in records
    )
    return pd.DataFrame(as_dicts)

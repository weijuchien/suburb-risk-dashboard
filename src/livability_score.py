from dataclasses import dataclass
from typing import Dict, List, Tuple

import math

import pandas as pd


@dataclass(frozen=True)
class MetricConfig:
    """
    Configuration metadata describing how to score a single metric.
    Weight:
       Fire Risk (Weight: 1.0)
       Flood Risk (Weight: 1.0)
       Public Housing Proportion (Weight: 1.5)
       Heritage Protection (Weight: 0.5)")
    Formula:
    1. Normalize Individual Metrics
    2. When multiple values exist for the same metric (ex: Public Housing), average the values
    3: Calculate Weighted Scores
    4: Compute Category Scores
    5: Calculate Overall Score"
    """
    metric: str
    category: str
    weight: float
    min_value: float
    max_value: float
    direction: str = "lower_is_better"

    def normalise(self, value: float) -> float:
        """Convert a raw metric value into a 0-100 score."""
        if math.isnan(value):
            raise ValueError("Metric normalisation expects a non-NaN value")
        span = self.max_value - self.min_value
        if span <= 0:
            raise ValueError(f"Invalid span for metric {self.metric}")

        if self.direction == "higher_is_better":
            normalised = (value - self.min_value) / span
        elif self.direction == "lower_is_better":
            normalised = (self.max_value - value) / span
        else:
            raise ValueError(f"Unknown direction '{self.direction}' for {self.metric}")

        return max(0.0, min(1.0, normalised)) * 100


DEFAULT_METRIC_CONFIG: Dict[str, MetricConfig] = {
    "Fire": MetricConfig(
        metric="Fire",
        category="Personal Safety",
        weight=1.0,
        min_value=0.0,
        max_value=1.0,
        direction="lower_is_better",
    ),
    "Flood": MetricConfig(
        metric="Flood",
        category="Personal Safety",
        weight=1.0,
        min_value=0.0,
        max_value=1.0,
        direction="lower_is_better",
    ),
    "Public Housing": MetricConfig(
        metric="Public Housing",
        category="Community Stability",
        weight=1.5,
        min_value=0.0,
        max_value=0.6,
        direction="lower_is_better",
    ),
    # Heritage restrictions can limit growth but also preserve amenity; here higher is better.
    "Heritage": MetricConfig(
        metric="Heritage",
        category="Community Stability",
        weight=0.5,
        min_value=0.0,
        max_value=1.0,
        direction="higher_is_better",
    ),
}


def compute_scores(df, metric_config=DEFAULT_METRIC_CONFIG,) -> Tuple[float, pd.DataFrame]:

    if df.empty:
        return 0.0, pd.DataFrame(columns=["category", "score", "weight"])

    contributions: Dict[str, Dict[str, float]] = {}
    total_weight = 0.0
    total_score = 0.0

    # Group by metric name to handle multiple values for same metric
    metric_values = {}
    for _, row in df.iterrows():
        metric_name = row.get("metric")
        value = row.get("value")

        if metric_name and value is not None and not math.isnan(value):
            if metric_name not in metric_values:
                metric_values[metric_name] = []
            metric_values[metric_name].append(float(value))

    # Process each metric (using average for multiple values)
    for metric_name, values in metric_values.items():
        config = metric_config.get(metric_name)
        if config is None:
            continue

        # Use average value for metrics with multiple entries
        avg_value = sum(values) / len(values)
        score = config.normalise(avg_value)
        weighted_score = score * config.weight

        bucket = contributions.setdefault(
            config.category, {"score": 0.0, "weight": 0.0}
        )
        bucket["score"] += weighted_score
        bucket["weight"] += config.weight

        total_score += weighted_score
        total_weight += config.weight

    if not contributions or total_weight == 0.0:
        return 0.0, pd.DataFrame(columns=["category", "score", "weight"])

    breakdown_rows: List[Dict[str, float]] = []
    for category, payload in contributions.items():
        category_weight = payload["weight"]
        category_score = payload["score"] / category_weight
        breakdown_rows.append(
            {"category": category, "score": category_score, "weight": category_weight}
        )

    breakdown_df = pd.DataFrame(breakdown_rows).sort_values(
        by="score", ascending=False
    )
    overall_score = total_score / total_weight
    return overall_score, breakdown_df.reset_index(drop=True)

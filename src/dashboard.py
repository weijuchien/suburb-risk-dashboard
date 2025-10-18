"""
Dashboard entry point for the Livability Score visualisation.

Run with:
    python -m src.dashboard
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from dash import Dash, Input, Output, State, dcc, html, dash_table
import pandas as pd
import plotly.graph_objects as go

from src.livability_score import compute_scores
from src.read_data import RiskDataError, fetch_risk_data, risk_records_to_frame

APP_TITLE = "Livability Score Dashboard"
FALLBACK_JSON = Path(__file__).resolve().parent / "default_risk_data.json"


def prepare_metrics_df(raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df.empty:
        return raw_df

    value_df = raw_df.dropna(subset=["value"])
    if value_df.empty:
        return raw_df

    collapsed = (
        value_df.groupby("metric", as_index=False)
        .agg(
            value=("value", "mean"),
            value_kind=("value_kind", "first"),
            value_unit=("value_unit", "first"),
        )
        .sort_values("metric")
    )
    return collapsed


def make_gauge(score: float) -> go.Figure:
    gauge = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            number={"suffix": " / 100", "font": {"size": 36}},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#2E86AB", "thickness": 0.3},
                "steps": [
                    {"range": [0, 40], "color": "#E74C3C"},
                    {"range": [40, 70], "color": "#F1C40F"},
                    {"range": [70, 100], "color": "#27AE60"},
                ],
            },
            title={"text": "Overall Livability"},
        )
    )
    gauge.update_layout(margin=dict(l=40, r=40, t=80, b=40))
    return gauge


def _make_category_bars(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return go.Figure()

    fig = go.Figure(
        go.Bar(
            x=df["score"],
            y=df["category"],
            orientation="h",
            marker=dict(color="#2E86AB"),
            hovertemplate="%{y}: %{x:.1f}/100<extra></extra>",
        )
    )
    fig.update_layout(
        title="Category Breakdown",
        xaxis_title="Score",
        yaxis_title="Category",
        margin=dict(l=60, r=20, t=60, b=40),
        height=250,
    )
    return fig


def _metrics_table(df: pd.DataFrame) -> dash_table.DataTable:
    columns = [
        {"name": "Metric", "id": "metric"},
        {"name": "Score Input", "id": "value_display"},
        {"name": "Unit", "id": "value_unit"},
    ]

    if df.empty:
        data = []
    else:
        working_df = df.copy()
        working_df["value_display"] = working_df["value"].apply(
            lambda x: f"{x * 100:.1f}%" if isinstance(x, float) else "--"
        )
        data = working_df.assign(metric=working_df["metric"].astype(str)).to_dict(
            orient="records"
        )

    return dash_table.DataTable(
        columns=columns,
        data=data,
        style_header={"backgroundColor": "#f6f6f6", "fontWeight": "bold"},
        style_cell={"padding": "0.5rem", "textAlign": "left"},
        page_size=10,
    )


def _load_scores(suburb_name: Optional[str], json_file: Optional[str] = None) -> Tuple[float, pd.DataFrame, pd.DataFrame]:
    """Load scores from API or specified JSON file

    Args:
        suburb_name: Name of suburb to query (if None, uses fallback)
        json_file: Path to specific JSON file to use instead of API
    """
    from src.read_data import load_risk_data_from_file

    if json_file:
        # Use specified JSON file instead of API
        records = load_risk_data_from_file(json_file)
    elif suburb_name is None:
        # Use default fallback JSON
        records = load_risk_data_from_file(str(FALLBACK_JSON))
    else:
        # Use API with fallback
        records = fetch_risk_data(
            suburb_name=suburb_name,
            fallback_path=str(FALLBACK_JSON),
        )

    raw_df = risk_records_to_frame(records)
    metrics_df = prepare_metrics_df(raw_df)
    overall_score, breakdown = compute_scores(metrics_df)
    return overall_score, breakdown, metrics_df


def create_app() -> Dash:
    app = Dash(__name__)
    app.title = APP_TITLE

    app.layout = html.Div(
        className="app-container",
        children=[
            html.H1(APP_TITLE),
            html.P(
                "Combine multiple risk indicators into a single 0-100 livability score."
            ),
            html.Div(
                className="controls",
                children=[
                    html.Div([
                        html.Label("Suburb Name:"),
                        dcc.Input(
                            id="suburb-name",
                            placeholder="Enter suburb name",
                            type="text",
                            value="",
                        ),
                    ]),
                    html.Div([
                        html.Label("Or use JSON file:"),
                        dcc.Dropdown(
                            id="json-file-selector",
                            options=[
                                {"label": "Default", "value": "src/default_risk_data.json"}
                            ],
                            value=None,
                            placeholder="Select JSON file (optional)",
                        ),
                    ]),
                    html.Button("Search", id="load-button", n_clicks=0),
                    html.Div(id="error-message", className="error"),
                ],
            ),
            html.Div(
                className="visuals",
                children=[
                    dcc.Loading(
                        id="overall-score",
                        type="default",
                        children=dcc.Graph(id="gauge", figure=make_gauge(0.0)),
                    ),
                    dcc.Loading(
                        id="category-scores",
                        type="default",
                        children=dcc.Graph(
                            id="category-bar", figure=_make_category_bars(pd.DataFrame())
                        ),
                    ),
                ],
            ),
            html.Div(
                id="metrics",
                className="metrics",
                children=[
                    html.H2("Source Metrics"),
                    _metrics_table(pd.DataFrame()),
                ],
            ),
        ],
    )

    @app.callback(
        Output("gauge", "figure"),
        Output("category-bar", "figure"),
        Output("metrics", "children"),
        Output("error-message", "children"),
        Input("load-button", "n_clicks"),
        State("suburb-name", "value"),
        State("json-file-selector", "value"),
        prevent_initial_call=False,
    )
    def update_dashboard(_: int, suburb_name: str, json_file: Optional[str]):
        try:
            suburb_param = suburb_name.strip() if suburb_name and suburb_name.strip() else None
            overall, breakdown, metrics_df = _load_scores(suburb_param, json_file)
            error_message = ""
        except RiskDataError as exc:
            overall, breakdown, metrics_df = 0.0, pd.DataFrame(), pd.DataFrame()
            error_message = str(exc)

        gauge_fig = make_gauge(overall)
        bar_fig = _make_category_bars(breakdown)
        metrics_section = [html.H2("Source Metrics"), _metrics_table(metrics_df)]
        return gauge_fig, bar_fig, metrics_section, error_message

    return app


def main() -> None:
    app = create_app()
    app.run(debug=True)


if __name__ == "__main__":
    main()

"""Shared plumbing for the model scripts (gravity, BVAR, r*): paths, data loading and
static chart styling.

Model outputs are derived, not sourced -- the same status as analysis/ and model_data/ --
so they live in the top-level models/ folder, one sub-folder per model.

Chart palette: the first three slots of the validated reference categorical palette
(blue, orange, aqua), which pass the colour-vision checks for every pair; aqua sits below
3:1 contrast on the light surface, so every chart names its series in a legend or a
direct label and every chart has its numbers in a CSV next to it (the table view).
"""
from __future__ import annotations

import gzip
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
UNIFIED = REPO_ROOT / "data" / "unified"
REFERENCE = REPO_ROOT / "data" / "reference"
MODEL_DATA = REPO_ROOT / "model_data"
MODELS = REPO_ROOT / "models"

SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
DISCLAIMER = "DERIVED, NOT SOURCED -- see models/README.md"


def load_dims(variables: list[str] | None = None) -> pd.DataFrame:
    with gzip.open(UNIFIED / "macro_dims_long.csv.gz", "rt", encoding="utf-8") as f:
        df = pd.read_csv(f, usecols=["date", "region", "variable", "item_code", "value"],
                         dtype={"date": str})
    if variables is not None:
        df = df[df.variable.isin(variables)]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["value"])


def load_quarterly() -> pd.DataFrame:
    q = pd.read_csv(MODEL_DATA / "quarterly.csv", parse_dates=["date"]).set_index("date")
    q.index = pd.PeriodIndex(q.index, freq="Q")
    return q


def load_monthly() -> pd.DataFrame:
    m = pd.read_csv(MODEL_DATA / "monthly.csv", parse_dates=["date"]).set_index("date")
    m.index = pd.PeriodIndex(m.index, freq="M")
    return m


# ---------------------------------------------------------------- charts
def figure(width: float = 8.0, height: float = 4.2):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(width, height))
    style(fig, ax)
    return fig, ax


def style(fig, *axes) -> None:
    fig.patch.set_facecolor(SURFACE)
    for ax in axes:
        ax.set_facecolor(SURFACE)
        ax.grid(True, axis="y", color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(BASELINE)
        ax.tick_params(colors=MUTED, labelcolor=INK_2, length=0, labelsize=9)
        ax.title.set_color(INK)


def title(ax, text: str, subtitle: str | None = None) -> None:
    ax.set_title(text, loc="left", fontsize=11.5, color=INK, pad=22 if subtitle else 8,
                 fontweight="semibold")
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=INK_2, va="bottom")


def zero_line(ax) -> None:
    ax.axhline(0, color=BASELINE, linewidth=0.9, zorder=1)


def legend(ax, **kw) -> None:
    kw.setdefault("fontsize", 9)
    return ax.legend(frameon=False, labelcolor=INK_2, **kw)


def save(fig, path: Path) -> None:
    import matplotlib.pyplot as plt

    fig.text(0.99, -0.01, DISCLAIMER, ha="right", va="top", fontsize=7, color=MUTED)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def fmt(x: float, nd: int = 2) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:,.{nd}f}".replace(",", " ")


def md_table(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(v) for v in row.values) + " |")
    return "\n".join(lines)

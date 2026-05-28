import io
from datetime import datetime, timezone, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch
import matplotlib.patches as mpatches

_MSK = timezone(timedelta(hours=3))
_PALETTE = ["#4C9BE8", "#E85C5C", "#58C97A", "#F5A623", "#9B59B6", "#1ABC9C"]
_BG = "#1E1E2E"
_CARD = "#2A2A3E"
_TEXT = "#E0E0F0"
_SUBTEXT = "#9090B0"


def _style():
    plt.rcParams.update({
        "figure.facecolor": _BG,
        "axes.facecolor": _CARD,
        "axes.edgecolor": "#3A3A5A",
        "axes.labelcolor": _TEXT,
        "xtick.color": _SUBTEXT,
        "ytick.color": _SUBTEXT,
        "text.color": _TEXT,
        "grid.color": "#3A3A5A",
        "grid.linestyle": "--",
        "grid.alpha": 0.5,
        "font.family": "DejaVu Sans",
        "font.size": 10,
    })


def build_stats_chart(
    tickets: list,
    ratings: list,
    category_labels: dict,
    status_labels: dict,
) -> bytes:
    _style()

    now_msk = datetime.now(_MSK)

    # --- prepare data ---
    total = len(tickets)
    closed = [t for t in tickets if t.status == "closed"]
    active = [t for t in tickets if t.status != "closed"]
    new_t  = [t for t in tickets if t.status == "new"]

    avg_hours = 0.0
    if closed:
        total_sec = sum(
            (t.updated_at - t.created_at).total_seconds()
            for t in closed if t.updated_at and t.created_at
        )
        avg_hours = round(total_sec / 3600 / len(closed), 1)

    useful = sum(1 for r in ratings if r.rating == "useful")
    not_useful = len(ratings) - useful
    useful_pct = round(useful / len(ratings) * 100) if ratings else 0

    # tickets by category
    cat_counts: dict[str, int] = {}
    for t in tickets:
        label = category_labels.get(t.category, t.category)
        cat_counts[label] = cat_counts.get(label, 0) + 1

    # tickets by status
    status_counts: dict[str, int] = {}
    for t in tickets:
        label = status_labels.get(t.status, t.status)
        status_counts[label] = status_counts.get(label, 0) + 1

    # daily activity last 14 days
    days: dict[str, int] = {}
    for i in range(13, -1, -1):
        day = (now_msk - timedelta(days=i)).strftime("%d.%m")
        days[day] = 0
    for t in tickets:
        if t.created_at:
            day = t.created_at.replace(tzinfo=timezone.utc).astimezone(_MSK).strftime("%d.%m")
            if day in days:
                days[day] += 1

    # --- layout ---
    fig = plt.figure(figsize=(14, 10), facecolor=_BG)
    fig.suptitle("Статистика обращений", fontsize=16, fontweight="bold",
                 color=_TEXT, y=0.97)

    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.55, wspace=0.4,
                           top=0.92, bottom=0.06, left=0.07, right=0.97)

    # ── KPI cards (top row) ───────────────────────────────────────────────
    kpis = [
        ("Всего тикетов", str(total), _PALETTE[0]),
        ("Активных", str(len(active)), _PALETTE[3]),
        ("Закрыто", str(len(closed)), _PALETTE[2]),
        ("Новых", str(len(new_t)), _PALETTE[1]),
        ("Ср. время закрытия", f"{avg_hours} ч", _PALETTE[4]),
        ("Полезных ответов", f"{useful_pct}%", _PALETTE[5]),
    ]
    for col, (label, value, color) in enumerate(kpis[:3]):
        ax = fig.add_subplot(gs[0, col])
        ax.set_facecolor(_CARD)
        for spine in ax.spines.values():
            spine.set_edgecolor(color)
            spine.set_linewidth(2)
        ax.set_xticks([]); ax.set_yticks([])
        ax.text(0.5, 0.62, value, ha="center", va="center", fontsize=26,
                fontweight="bold", color=color, transform=ax.transAxes)
        ax.text(0.5, 0.22, label, ha="center", va="center", fontsize=9,
                color=_SUBTEXT, transform=ax.transAxes)

    # extra KPIs as sub-row inside bottom of first row
    # We'll put them in row 1 as a bar chart instead

    # ── Category bar chart (middle left + center) ────────────────────────
    ax_bar = fig.add_subplot(gs[1, :2])
    if cat_counts:
        cats = list(cat_counts.keys())
        vals = list(cat_counts.values())
        colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(cats))]
        bars = ax_bar.barh(cats, vals, color=colors, height=0.55, zorder=3)
        ax_bar.set_xlabel("Кол-во тикетов", color=_SUBTEXT, fontsize=9)
        ax_bar.set_title("По категориям", color=_TEXT, fontsize=11, fontweight="bold")
        ax_bar.grid(axis="x", zorder=0)
        ax_bar.set_xlim(0, max(vals) * 1.25 if vals else 1)
        for bar, val in zip(bars, vals):
            ax_bar.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height() / 2,
                        str(val), va="center", color=_TEXT, fontsize=9)
    else:
        ax_bar.text(0.5, 0.5, "Нет данных", ha="center", va="center",
                    color=_SUBTEXT, transform=ax_bar.transAxes)
        ax_bar.set_title("По категориям", color=_TEXT, fontsize=11, fontweight="bold")

    # ── Status pie chart (middle right) ──────────────────────────────────
    ax_pie = fig.add_subplot(gs[1, 2])
    if status_counts:
        pie_labels = list(status_counts.keys())
        pie_vals   = list(status_counts.values())
        pie_colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(pie_labels))]
        wedges, texts, autotexts = ax_pie.pie(
            pie_vals, labels=None, autopct="%1.0f%%",
            colors=pie_colors, startangle=140,
            pctdistance=0.75,
            wedgeprops={"linewidth": 0.5, "edgecolor": _BG},
        )
        for at in autotexts:
            at.set_color(_BG); at.set_fontsize(8); at.set_fontweight("bold")
        ax_pie.legend(wedges, pie_labels, loc="lower center",
                      bbox_to_anchor=(0.5, -0.25), ncol=2,
                      fontsize=7, framealpha=0, labelcolor=_TEXT)
        ax_pie.set_title("По статусам", color=_TEXT, fontsize=11, fontweight="bold")
    else:
        ax_pie.text(0.5, 0.5, "Нет данных", ha="center", va="center",
                    color=_SUBTEXT, transform=ax_pie.transAxes)
        ax_pie.set_title("По статусам", color=_TEXT, fontsize=11, fontweight="bold")

    # ── Daily trend (bottom, full width) ─────────────────────────────────
    ax_line = fig.add_subplot(gs[2, :])
    day_keys = list(days.keys())
    day_vals = list(days.values())
    ax_line.plot(day_keys, day_vals, color=_PALETTE[0], linewidth=2,
                 marker="o", markersize=5, zorder=3)
    ax_line.fill_between(day_keys, day_vals, alpha=0.15, color=_PALETTE[0])
    ax_line.set_title("Активность за 14 дней", color=_TEXT, fontsize=11, fontweight="bold")
    ax_line.set_ylabel("Тикетов/день", color=_SUBTEXT, fontsize=9)
    ax_line.grid(axis="y", zorder=0)
    ax_line.set_ylim(bottom=0)
    step = max(1, len(day_keys) // 7)
    ax_line.set_xticks(range(0, len(day_keys), step))
    ax_line.set_xticklabels([day_keys[i] for i in range(0, len(day_keys), step)],
                             rotation=30, ha="right", fontsize=8)

    # ── Extra KPI strip (row 1, add 3 more KPIs under top cards) ─────────
    # Re-use gs[0] area — draw thin annotation boxes
    for col, (label, value, color) in enumerate(kpis[3:]):
        ax = fig.add_axes([0.07 + col * 0.305, 0.74, 0.27, 0.06])
        ax.set_facecolor(_BG)
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.set_xticks([]); ax.set_yticks([])
        ax.text(0.0, 0.5, f"{label}:", va="center", color=_SUBTEXT, fontsize=8.5)
        ax.text(1.0, 0.5, value, va="center", ha="right",
                color=color, fontsize=10, fontweight="bold")

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=130, facecolor=_BG, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()

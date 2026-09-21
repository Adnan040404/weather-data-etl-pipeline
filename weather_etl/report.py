"""REPORT: read the database and produce charts, an HTML page and an Excel file."""

import sqlite3
from datetime import datetime

import matplotlib

matplotlib.use("Agg")  # draw to files, no display needed
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from jinja2 import Environment, FileSystemLoader  # noqa: E402

from . import config  # noqa: E402

NAVY, BLUE = "#1F3864", "#2F5597"
PALETTE = ["#1F3864", "#ED7D31", "#70AD47", "#9E6BD1", "#00A3A3", "#FFC000"]  # easy to tell apart


def _read(conn, sql):
    return pd.read_sql_query(sql, conn)


def build_report(db_path=None, out_dir=None):
    db_path = db_path or config.DB_PATH
    out_dir = out_dir or config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        history = _read(conn, "SELECT * FROM weather_observations ORDER BY observed_at")
        latest = _read(conn, "SELECT * FROM v_latest_by_city ORDER BY city")
        summary = _read(conn, "SELECT * FROM v_city_summary ORDER BY city")
        sources = _read(conn, "SELECT DISTINCT source FROM weather_observations")["source"].tolist()
    finally:
        conn.close()
    if history.empty:
        raise RuntimeError("No data to report. Run the pipeline first.")

    history["observed_at"] = pd.to_datetime(history["observed_at"])
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False,
                         "axes.spines.right": False})

    # 1) temperature over time, one line per city
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for i, (city, grp) in enumerate(history.groupby("city")):
        ax.plot(grp["observed_at"], grp["temperature_c"], label=city, color=PALETTE[i % len(PALETTE)],
                linewidth=1.6)
    ax.set_title("Temperature over time", loc="left", color=NAVY, fontweight="bold")
    ax.set_ylabel("Temperature (°C)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    fig.tight_layout()
    fig.savefig(out_dir / "temperature_trend.png", dpi=150)
    plt.close(fig)

    # 2) latest temperature by city
    fig, ax = plt.subplots(figsize=(5.4, 4.2))
    bars = ax.bar(latest["city"], latest["temperature_c"], color=BLUE)
    ax.bar_label(bars, fmt="%.1f°", padding=2, fontsize=9)
    ax.set_title("Latest temperature", loc="left", color=NAVY, fontweight="bold")
    ax.set_ylabel("°C")
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(out_dir / "latest_temperature.png", dpi=150)
    plt.close(fig)

    # 3) how often each weather condition was recorded
    counts = history["conditions"].value_counts()
    fig, ax = plt.subplots(figsize=(5.4, 4.2))
    bars = ax.barh(counts.index[::-1], counts.values[::-1], color=PALETTE[3])
    ax.bar_label(bars, padding=3, fontsize=9)
    ax.set_title("Conditions recorded", loc="left", color=NAVY, fontweight="bold")
    ax.set_xlabel("Readings")
    fig.tight_layout()
    fig.savefig(out_dir / "conditions.png", dpi=150)
    plt.close(fig)

    sample_only = sources == ["sample"]
    env = Environment(loader=FileSystemLoader(str(config.TEMPLATE_DIR)), autoescape=True)
    html = env.get_template("report.html.j2").render(
        n_readings=len(history), n_cities=history["city"].nunique(),
        first=history["observed_at"].min().strftime("%Y-%m-%d %H:%M"),
        last=history["observed_at"].max().strftime("%Y-%m-%d %H:%M"),
        source_label="sample data (generated, not real weather)" if sample_only else ", ".join(sources),
        latest=latest.to_dict("records"), summary=summary.to_dict("records"),
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        disclaimer="Sample data is generated for demonstration." if sample_only else "")
    (out_dir / "weather_report.html").write_text(html, encoding="utf-8")

    with pd.ExcelWriter(out_dir / "weather_data.xlsx", engine="openpyxl") as xl:
        summary.to_excel(xl, sheet_name="City summary", index=False)
        latest.to_excel(xl, sheet_name="Latest", index=False)
        history.assign(observed_at=history["observed_at"].dt.strftime("%Y-%m-%d %H:%M")).to_excel(
            xl, sheet_name="History", index=False)
        for ws in xl.book.worksheets:
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(
                    28, max(len(str(c.value)) if c.value is not None else 0 for c in col) + 3)
            ws.freeze_panes = "A2"
    return out_dir

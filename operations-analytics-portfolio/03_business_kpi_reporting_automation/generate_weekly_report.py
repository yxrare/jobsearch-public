from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

DATA_PATH = Path("data/weekly_kpi_sample.csv")
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)


def load_data():
    return pd.read_csv(DATA_PATH, parse_dates=["date"])


def wow_summary(df):
    max_date = df["date"].max()
    current = df[df["date"] >= max_date - pd.Timedelta(days=6)]
    previous = df[(df["date"] < max_date - pd.Timedelta(days=6)) & (df["date"] >= max_date - pd.Timedelta(days=13))]

    def calc(col, agg="sum"):
        cur = current[col].sum() if agg == "sum" else current[col].mean()
        prev = previous[col].sum() if agg == "sum" else previous[col].mean()
        wow = (cur - prev) / prev if prev else 0
        return cur, wow

    return {
        "orders": calc("orders", "sum"),
        "gmv": calc("gmv_eur", "sum"),
        "revenue": calc("revenue_eur", "sum"),
        "fulfillment_rate": calc("fulfillment_rate", "mean"),
        "delivery_sla_rate": calc("delivery_sla_rate", "mean"),
        "cancellation_rate": calc("cancellation_rate", "mean"),
        "return_rate": calc("return_rate", "mean"),
        "inventory_turnover": calc("inventory_turnover", "mean"),
    }


def create_charts(df):
    daily = df.groupby("date", as_index=False).agg(
        orders=("orders", "sum"),
        fulfillment_rate=("fulfillment_rate", "mean"),
        delivery_sla_rate=("delivery_sla_rate", "mean"),
    )
    plt.figure(figsize=(10, 5))
    plt.plot(daily["date"], daily["orders"])
    plt.title("Daily Orders Trend")
    plt.ylabel("Orders")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "orders_trend.png", dpi=160)

    plt.figure(figsize=(10, 5))
    plt.plot(daily["date"], daily["fulfillment_rate"], label="Fulfillment Rate")
    plt.plot(daily["date"], daily["delivery_sla_rate"], label="Delivery SLA")
    plt.title("Operational Service KPIs")
    plt.ylabel("Rate")
    plt.xticks(rotation=45)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "service_kpis.png", dpi=160)


def create_markdown_report(summary):
    orders, orders_wow = summary["orders"]
    revenue, revenue_wow = summary["revenue"]
    sla, sla_wow = summary["delivery_sla_rate"]
    text = f"""# Weekly Business KPI Report

## Executive summary
- Orders: {orders:,.0f} ({orders_wow:+.1%} WoW)
- Revenue: €{revenue:,.0f} ({revenue_wow:+.1%} WoW)
- Delivery SLA: {sla:.1%} ({sla_wow:+.1%} WoW)

## Top issues
1. Delivery SLA below target in selected regions.
2. Cancellation rate increases when fulfillment drops.
3. Inventory turnover should be reviewed for slow-moving SKUs.

## Action items
- Review late-delivery routes with operations.
- Prioritize replenishment for high-demand regions.
- Build exception list for cancellation and return drivers.
"""
    (OUTPUT_DIR / "weekly_business_kpi_report.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    data = load_data()
    summary = wow_summary(data)
    create_charts(data)
    create_markdown_report(summary)
    print(summary)

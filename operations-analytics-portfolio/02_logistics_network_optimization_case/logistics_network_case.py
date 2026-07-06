from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

DATA_DIR = Path("data")
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)


def load_data():
    stations = pd.read_csv(DATA_DIR / "station_performance.csv")
    routes = pd.read_csv(DATA_DIR / "route_performance.csv")
    optimized = pd.read_csv(DATA_DIR / "optimized_station_plan.csv")
    return stations, routes, optimized


def summarize_network(stations, routes):
    return {
        "total_daily_volume": int(stations["daily_volume"].sum()),
        "avg_utilization": round(stations["utilization"].mean(), 3),
        "overloaded_sites": stations.loc[stations["utilization"] > 1.0, "station"].tolist(),
        "avg_cost_per_parcel": round(stations["cost_per_parcel_eur"].mean(), 2),
        "avg_24h_sla": round(stations["sla_24h_rate"].mean(), 3),
        "high_risk_routes": int((routes["sla_risk"] == "High").sum()),
    }


def plot_utilization(stations):
    ordered = stations.sort_values("utilization", ascending=False)
    plt.figure(figsize=(9, 5))
    plt.bar(ordered["station"], ordered["utilization"])
    plt.axhline(1.0, linestyle="--")
    plt.title("Station Utilization")
    plt.ylabel("Volume / Capacity")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "station_utilization.png", dpi=160)


if __name__ == "__main__":
    stations, routes, optimized = load_data()
    print(summarize_network(stations, routes))
    plot_utilization(stations)

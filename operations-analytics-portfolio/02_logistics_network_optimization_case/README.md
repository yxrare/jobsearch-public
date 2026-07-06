# Logistics Network Optimization Case

**Portfolio positioning:** operations optimization, cost analysis, service-level improvement, and logistics network decision-making.

## Business case
A parcel delivery company operates hubs and stations across Germany. Some sites are overloaded, while others are underutilized. The goal is to rebalance volume, reduce cost per parcel, and improve 24-hour delivery SLA.

## What this project shows
- Station utilization analysis
- Route cost and transit-time analysis
- Cost vs speed trade-off
- Overloaded and underutilized site identification
- Before/after network scenario comparison
- Python-based optimization logic and map-style visualization

## Repo structure
```text
02_logistics_network_optimization_case/
├── logistics_network_case.py
├── data/
│   ├── station_performance.csv
│   ├── route_performance.csv
│   └── optimized_station_plan.csv
├── outputs/
├── sql/logistics_network_queries.sql
└── requirements.txt
```

## Main recommendations
1. Reduce load from Frankfurt DC and Dortmund Station because utilization exceeds planned capacity.
2. Rebalance parcels to Nuremberg, Stuttgart and Leipzig to use existing spare capacity.
3. Review high-cost / long-transit routes and shift volume to shorter lanes where possible.
4. Avoid opening a new site immediately; first capture efficiency from rebalancing.

## Business interpretation
This is the kind of case that works well for Logistics Analyst, Operations Analyst, Network Planning, and Management Trainee roles. It shows that you can connect data analysis with a real business decision: where volume should move and why.

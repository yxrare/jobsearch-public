# Demand Planning Dashboard

**Portfolio positioning:** demand forecasting, inventory monitoring, and supply-demand balancing for Supply Chain Analyst / Demand Planning roles.

## Business question
How can a planning team identify forecast quality issues, stockout risk, backlog pressure, and supply gaps across SKU, region, and channel?

## What this project shows
- Forecast Accuracy / MAPE / Bias calculation
- Demand vs Supply gap analysis
- Inventory Days and Stockout Risk classification
- Backlog Volume and Service Level monitoring
- SKU / Region / Channel slicing logic
- SQL-ready analytical queries and a Streamlit dashboard prototype

## Repo structure
```text
01_demand_planning_dashboard/
├── app.py
├── demand_planning_analysis.py
├── data/demand_planning_sample.csv
├── outputs/
├── sql/demand_planning_queries.sql
└── requirements.txt
```

## Key formulas
- `MAPE = ABS(actual_demand - forecast) / actual_demand`
- `Bias = (forecast - actual_demand) / actual_demand`
- `Inventory Days = inventory_units / (actual_demand / 7)`
- `Service Level = fulfilled_units / actual_demand`

## How to run
```bash
pip install -r requirements.txt
python demand_planning_analysis.py
streamlit run app.py
```

## Business interpretation
The dashboard is designed for weekly S&OP review. It helps planners answer: where are we over-forecasting, where supply cannot cover demand, which SKUs create backlog, and where inventory days indicate stockout risk.

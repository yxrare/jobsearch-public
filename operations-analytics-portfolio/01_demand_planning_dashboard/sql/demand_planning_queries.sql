-- Demand Planning KPIs by week, SKU, region and channel
SELECT
    week,
    sku,
    region,
    channel,
    SUM(actual_demand) AS actual_demand,
    SUM(forecast) AS forecast,
    SUM(supply) AS supply,
    SUM(inventory_units) AS inventory_units,
    SUM(backlog_units) AS backlog_units,
    AVG(ABS(actual_demand - forecast) * 1.0 / NULLIF(actual_demand, 0)) AS mape,
    AVG((forecast - actual_demand) * 1.0 / NULLIF(actual_demand, 0)) AS forecast_bias,
    SUM(fulfilled_units) * 1.0 / NULLIF(SUM(actual_demand), 0) AS service_level,
    SUM(inventory_units) * 1.0 / NULLIF(SUM(actual_demand) / 7.0, 0) AS inventory_days,
    SUM(actual_demand - supply) AS demand_supply_gap
FROM demand_planning
GROUP BY week, sku, region, channel;

-- Stockout risk ranking
SELECT
    sku,
    region,
    channel,
    AVG(inventory_days) AS avg_inventory_days,
    SUM(backlog_units) AS total_backlog,
    AVG(service_level) AS avg_service_level
FROM demand_planning_metrics
GROUP BY sku, region, channel
ORDER BY avg_inventory_days ASC, total_backlog DESC;

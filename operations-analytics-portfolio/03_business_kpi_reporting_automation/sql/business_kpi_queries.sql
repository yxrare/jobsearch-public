-- Weekly management KPI report
SELECT
    DATE_TRUNC('week', date) AS week_start,
    region,
    SUM(orders) AS orders,
    SUM(gmv_eur) AS gmv_eur,
    SUM(revenue_eur) AS revenue_eur,
    AVG(fulfillment_rate) AS fulfillment_rate,
    AVG(delivery_sla_rate) AS delivery_sla_rate,
    AVG(cancellation_rate) AS cancellation_rate,
    AVG(return_rate) AS return_rate,
    AVG(inventory_turnover) AS inventory_turnover
FROM business_kpi_daily
GROUP BY DATE_TRUNC('week', date), region
ORDER BY week_start DESC, region;

-- Identify operational issues
SELECT
    date,
    region,
    fulfillment_rate,
    delivery_sla_rate,
    cancellation_rate,
    return_rate,
    CASE
        WHEN delivery_sla_rate < 0.90 THEN 'Delivery SLA below target'
        WHEN fulfillment_rate < 0.93 THEN 'Fulfillment below target'
        WHEN cancellation_rate > 0.05 THEN 'Cancellation spike'
        WHEN return_rate > 0.08 THEN 'Return spike'
        ELSE 'Normal'
    END AS issue_flag
FROM business_kpi_daily
WHERE delivery_sla_rate < 0.90
   OR fulfillment_rate < 0.93
   OR cancellation_rate > 0.05
   OR return_rate > 0.08
ORDER BY date DESC, region;

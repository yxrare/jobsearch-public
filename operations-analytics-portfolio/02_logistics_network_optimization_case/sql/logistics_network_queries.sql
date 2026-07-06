-- Station load analysis
SELECT
    station,
    daily_volume,
    daily_capacity,
    daily_volume * 1.0 / NULLIF(daily_capacity, 0) AS utilization,
    cost_per_parcel_eur,
    sla_24h_rate,
    CASE
        WHEN daily_volume * 1.0 / NULLIF(daily_capacity, 0) > 1.05 THEN 'Overloaded'
        WHEN daily_volume * 1.0 / NULLIF(daily_capacity, 0) > 0.90 THEN 'Near capacity'
        WHEN daily_volume * 1.0 / NULLIF(daily_capacity, 0) < 0.65 THEN 'Underutilized'
        ELSE 'Balanced'
    END AS site_status
FROM station_performance
ORDER BY utilization DESC;

-- High-cost and slow routes
SELECT
    origin,
    destination,
    distance_km,
    daily_parcels,
    cost_per_parcel_eur,
    transit_hours,
    daily_parcels * cost_per_parcel_eur AS route_cost_daily
FROM route_performance
WHERE cost_per_parcel_eur > 2.5 OR transit_hours > 8
ORDER BY route_cost_daily DESC;

-- Before and after scenario comparison
SELECT
    AVG(cost_per_parcel_eur) AS avg_cost_before,
    AVG(optimized_cost_per_parcel_eur) AS avg_cost_after,
    AVG(sla_24h_rate) AS avg_sla_before,
    AVG(optimized_sla_24h_rate) AS avg_sla_after
FROM optimized_station_plan;

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Demand Planning Dashboard", layout="wide")
st.title("Demand Planning Dashboard")
st.caption("Forecast accuracy, supply-demand gap, stockout risk, backlog, and service level monitoring.")

df = pd.read_csv("data/demand_planning_sample.csv", parse_dates=["week"])

with st.sidebar:
    st.header("Filters")
    sku = st.multiselect("SKU", sorted(df["sku"].unique()), default=sorted(df["sku"].unique()))
    region = st.multiselect("Region", sorted(df["region"].unique()), default=sorted(df["region"].unique()))
    channel = st.multiselect("Channel", sorted(df["channel"].unique()), default=sorted(df["channel"].unique()))

filtered = df[df["sku"].isin(sku) & df["region"].isin(region) & df["channel"].isin(channel)]

kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
kpi1.metric("MAPE", f"{filtered['ape'].mean():.1%}")
kpi2.metric("Forecast Bias", f"{filtered['bias'].mean():.1%}")
kpi3.metric("Service Level", f"{filtered['service_level'].mean():.1%}")
kpi4.metric("Backlog", f"{filtered['backlog_units'].sum():,.0f}")
kpi5.metric("High Risk Rows", f"{(filtered['stockout_risk'] == 'High').sum():,.0f}")

weekly = filtered.groupby("week", as_index=False).agg(
    actual_demand=("actual_demand", "sum"),
    forecast=("forecast", "sum"),
    supply=("supply", "sum"),
    backlog_units=("backlog_units", "sum"),
)
st.subheader("Demand vs Forecast vs Supply")
st.line_chart(weekly.set_index("week")[["actual_demand", "forecast", "supply"]])

st.subheader("Backlog by Week")
st.bar_chart(weekly.set_index("week")[["backlog_units"]])

st.subheader("Detail Table")
st.dataframe(filtered, use_container_width=True)

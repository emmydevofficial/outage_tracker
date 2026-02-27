"""
### FILE: pages/6_Reliability_KPI_Report.py
Computes SAIDI, SAIFI, CAIDI approximations. Requires customers served per station to compute accurate indices.
This sample assumes a 'customers' column is NOT available, so it shows station-level outage summary.
"""

import streamlit as st
from utils.auth import login
import pandas as pd
from utils.db import read_outages
from datetime import date, timedelta
import plotly.express as px

login()

st.set_page_config(page_title="Reliability KPIs", layout="wide")

st.title("Reliability KPI Report")

today = date.today()
start_default = today - timedelta(days=30)
start_date, end_date = st.date_input("Select date range", value=[start_default, today], key="reliability_dates")

out_df = read_outages(str(start_date), str(end_date))
if out_df.empty:
    st.warning("No outage records for this range")
    st.stop()

# filtering controls
col1, col2, col3, col4 = st.columns(4)
region_sel = col1.selectbox("Region", options=["All"] + sorted(out_df["region"].dropna().unique()))
if region_sel != "All":
    out_df = out_df[out_df["region"] == region_sel]

disco_sel = col2.selectbox("Disco", options=["All"] + sorted(out_df["disco"].dropna().unique()))
if disco_sel != "All":
    out_df = out_df[out_df["disco"] == disco_sel]

area_sel = col3.selectbox("Area", options=["All"] + sorted(out_df["area"].dropna().unique()))
if area_sel != "All":
    out_df = out_df[out_df["area"] == area_sel]

station_sel = col4.selectbox("Station", options=["All"] + sorted(out_df["station"].dropna().unique()))
if station_sel != "All":
    out_df = out_df[out_df["station"] == station_sel]

# station outage summary
out_df['start_ts'] = pd.to_datetime(out_df['date_off'].astype(str) + ' ' + out_df['time_off'].astype(str), errors='coerce')
out_df['end_ts'] = pd.to_datetime(out_df['date_on'].astype(str) + ' ' + out_df['time_on'].astype(str), errors='coerce')
out_df['duration_min'] = (out_df['end_ts'] - out_df['start_ts']).dt.total_seconds() / 60.0

station_summary = out_df.groupby('station').agg(
    outages_count=('id', 'count'),
    total_outage_min=('duration_min', 'sum')
).reset_index().sort_values('total_outage_min', ascending=False)

station_summary['avg_outage_min'] = station_summary['total_outage_min'] / station_summary['outages_count']

station_summary['outage_hour'] = station_summary['total_outage_min'] / 60.0

st.dataframe(station_summary)

fig = px.bar(station_summary.head(20), x='station', y='total_outage_min', title='Top stations by total outage minutes')
st.plotly_chart(fig, use_container_width=True)

st.subheader("📊 Outage Table")
feeder_summary = out_df.groupby('feeder_33kv').agg(
    outages_count=('id', 'count'),
    total_outage_min=('duration_min', 'sum')
).reset_index().sort_values('total_outage_min', ascending=False)

feeder_summary['avg_outage_hrs'] = feeder_summary['total_outage_min'] / feeder_summary['outages_count'] / 60.0
feeder_summary['outage_hrs'] = feeder_summary['total_outage_min'] / 60.0
feeder_summary = feeder_summary.drop(columns=["total_outage_min"])

st.dataframe(feeder_summary)

st.subheader("📊 Outage Table By Party Responsible")
feeder_party_pivot = out_df.groupby(['feeder_33kv', 'party_responsible']).agg(
    total_outage_hour=('duration_min', lambda x: x.sum() / 60)
).reset_index().pivot_table(
    index='feeder_33kv',
    columns='party_responsible',
    values='total_outage_hour',
    aggfunc='sum',
    fill_value=0
)

feeder_party_pivot.columns.name = None  # clean up column name
feeder_party_pivot = feeder_party_pivot.reset_index()

st.dataframe(feeder_party_pivot)

fig = px.bar(feeder_summary.head(20), x='feeder_33kv', y='outage_hrs', title='Top feeders by total outage minutes')
st.plotly_chart(fig, use_container_width=True)

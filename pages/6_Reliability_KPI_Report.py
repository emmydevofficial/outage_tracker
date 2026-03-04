"""
### FILE: pages/6_Reliability_KPI_Report.py
Computes SAIDI, SAIFI, CAIDI approximations. Requires customers served per station to compute accurate indices.
This sample assumes a 'customers' column is NOT available, so it shows station-level outage summary.
"""

import streamlit as st
from utils.auth import login
import pandas as pd
from utils.db import read_outages, read_tcn_sla_compliance
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

# determine number of days in the selected range (inclusive)
days_span = (end_date - start_date).days + 1

# pivot by station and feeder so that we can join back against SLA data
feeder_party_pivot = out_df.groupby(['station','feeder_33kv', 'party_responsible']).agg(
    total_outage_hour=('duration_min', lambda x: x.sum() / 60)
).reset_index().pivot_table(
    index=['station','feeder_33kv'],
    columns='party_responsible',
    values='total_outage_hour',
    aggfunc='sum',
    fill_value=0
)

feeder_party_pivot.columns.name = None  # clean up column name
feeder_party_pivot = feeder_party_pivot.reset_index()

# merge SLA table (per day) and scale by number of days
sla = read_tcn_sla_compliance()
if not sla.empty:
    sla['maximum_outage_hours'] = sla['maximum_outage_hours'] * days_span
    sla["actual_outage_hours"] = "Yes"

# join on both station and feeder name
feeder_party_pivot = feeder_party_pivot.merge(
    sla,
    left_on=['station','feeder_33kv'],
    right_on=['station','feeder_name'],
    how='left'
)

# drop the redundant feeder_name column added by the merge
if 'feeder_name' in feeder_party_pivot.columns:
    feeder_party_pivot = feeder_party_pivot.drop(columns=['feeder_name'])

# absent entries result in NaN; treat as zero (unknown SLA)
feeder_party_pivot['maximum_outage_hours'] = 4 * days_span  # default to 4 hours per day if SLA data is missing
feeder_party_pivot['maximum_outage_hours'] = feeder_party_pivot['maximum_outage_hours'].fillna(0)
feeder_party_pivot["actual_outage_hours"] = feeder_party_pivot['actual_outage_hours'].fillna("Assumed 4 hours/day (not in db)")

# calculate disco and tcn allowances
feeder_party_pivot['max_hours_disco'] = feeder_party_pivot['maximum_outage_hours'] * 0.7
feeder_party_pivot['max_hours_tcn'] = feeder_party_pivot['maximum_outage_hours'] * 0.3

# ensure the dynamic TCN column exists and default to zero when absent
if 'TCN' not in feeder_party_pivot.columns:
    feeder_party_pivot['TCN'] = 0

# compute the remaining/available hours for TCN
feeder_party_pivot['available_outage_hours_tcn'] = (
    feeder_party_pivot['max_hours_tcn'] - feeder_party_pivot['TCN']
)

feeder_party_pivot.columns.name = None  # clean up column name
# reset_index may introduce an unwanted 'index' column; drop it if present
feeder_party_pivot = feeder_party_pivot.reset_index(drop=True)

# filtering options for available outage hours
status_choice = st.selectbox(
    "Show rows where TCN availability is", 
    options=["All","Positive (≥0)","Negative (<0)"],
    index=0
)

filtered = feeder_party_pivot.copy()
if status_choice == "Positive (≥0)":
    filtered = filtered[filtered['available_outage_hours_tcn'] >= 0]
elif status_choice == "Negative (<0)":
    filtered = filtered[filtered['available_outage_hours_tcn'] < 0]

# apply color styling to available hours column
styler = filtered.style.applymap(
    lambda v: 'color: green' if v > 0 else 'color: red',
    subset=['available_outage_hours_tcn']
)

st.dataframe(styler)

fig = px.bar(feeder_summary.head(20), x='feeder_33kv', y='outage_hrs', title='Top feeders by total outage minutes')
st.plotly_chart(fig, use_container_width=True)

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

# ensure last_load is numeric so load loss can be calculated reliably
out_df['last_load'] = pd.to_numeric(out_df['last_load'], errors='coerce')

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

# Monthly-clipped duration: clips start/end timestamps to calendar month boundaries.
# This ensures cross-month outages (e.g. trip on Feb-28 22:00, restored Mar-01 09:30)
# only count the hours that fall within the month(s) covered by the selected date range.
#   → Viewing March only  → 9.5 hrs  (clipped start = Mar-01 00:00)
#   → Viewing February only → 2.0 hrs  (clipped end   = Feb-28 23:59:59)
#   → Viewing both months  → 11.5 hrs (no clipping needed, full duration counted)
month_start = pd.Timestamp(start_date.replace(day=1))                          # 1st of start month 00:00
import calendar
last_day = calendar.monthrange(end_date.year, end_date.month)[1]
month_end = pd.Timestamp(end_date.replace(day=last_day)) + pd.Timedelta(days=1)  # 1st of next month (exclusive)

out_df['clipped_start'] = out_df['start_ts'].clip(lower=month_start, upper=month_end)
out_df['clipped_end']   = out_df['end_ts'].clip(lower=month_start, upper=month_end)
out_df['duration_min_clipped'] = (out_df['clipped_end'] - out_df['clipped_start']).dt.total_seconds() / 60.0
out_df['duration_min_clipped'] = out_df['duration_min_clipped'].clip(lower=0)  # guard against negatives

# compute load loss from outage duration and last_read load
out_df['duration_hr'] = out_df['duration_min'] / 60.0
out_df['duration_hr_clipped'] = out_df['duration_min_clipped'] / 60.0
out_df['load_loss_mwh'] = out_df['duration_hr'] * out_df['last_load']
out_df['load_loss_mwh_clipped'] = out_df['duration_hr_clipped'] * out_df['last_load']

station_summary = out_df.groupby('station').agg(
    outages_count=('id', 'count'),
    total_outage_min=('duration_min', 'sum'),
    total_load_loss_mwh=('load_loss_mwh', 'sum')
).reset_index().sort_values('total_outage_min', ascending=False)

station_summary['avg_outage_min'] = station_summary['total_outage_min'] / station_summary['outages_count']
station_summary['outage_hour'] = station_summary['total_outage_min'] / 60.0
station_summary['avg_load_loss_mwh'] = station_summary['total_load_loss_mwh'] / station_summary['outages_count']

st.dataframe(station_summary)

fig = px.bar(station_summary.head(20), x='station', y='total_outage_min', title='Top stations by total outage minutes')
st.plotly_chart(fig, use_container_width=True)

st.subheader("📊 Outage Table")
feeder_summary = out_df.groupby('feeder_33kv').agg(
    outages_count=('id', 'count'),
    total_outage_min=('duration_min', 'sum'),
    total_load_loss_mwh=('load_loss_mwh', 'sum')
).reset_index().sort_values('total_outage_min', ascending=False)

feeder_summary['avg_outage_hrs'] = feeder_summary['total_outage_min'] / feeder_summary['outages_count'] / 60.0
feeder_summary['outage_hrs'] = feeder_summary['total_outage_min'] / 60.0
feeder_summary['avg_load_loss_mwh'] = feeder_summary['total_load_loss_mwh'] / feeder_summary['outages_count']
feeder_summary = feeder_summary.drop(columns=["total_outage_min"])

st.dataframe(feeder_summary)

st.subheader("📊 Outage Table By Party Responsible")

# determine number of days in the selected range (inclusive)
days_span = (end_date - start_date).days + 1

# pivot by station and feeder so that we can join back against SLA data
# NOTE: uses duration_min_clipped so cross-month outages only count hours within the selected date range
feeder_party_pivot = out_df.groupby(['station','feeder_33kv', 'party_responsible']).agg(
    total_outage_hour=('duration_min_clipped', lambda x: x.sum() / 60),
    total_load_loss_mwh=('load_loss_mwh_clipped', 'sum')
).reset_index().pivot_table(
    index=['station','feeder_33kv'],
    columns='party_responsible',
    values=['total_outage_hour', 'total_load_loss_mwh'],
    aggfunc='sum',
    fill_value=0
)

# flatten multiindex columns to keep party columns readable
feeder_party_pivot.columns = [f"{metric}_{party}" for metric, party in feeder_party_pivot.columns]
feeder_party_pivot.columns.name = None
feeder_party_pivot = feeder_party_pivot.reset_index()

# merge SLA table (per day) and scale by number of days
sla = read_tcn_sla_compliance()
if not sla.empty:
    sla['maximum_outage_hours'] = sla['maximum_outage_hours'] * days_span
    sla["actual_outage_hours"] = "Yes"
    
    # Create clean columns for merge to prevent mismatch due to whitespace or casing
    feeder_party_pivot['station_clean'] = feeder_party_pivot['station'].astype(str).str.strip().str.upper()
    feeder_party_pivot['feeder_clean'] = feeder_party_pivot['feeder_33kv'].astype(str).str.strip().str.upper()
    
    sla_clean = sla.copy()
    sla_clean['station_clean'] = sla_clean['station'].astype(str).str.strip().str.upper()
    sla_clean['feeder_clean'] = sla_clean['feeder_name'].astype(str).str.strip().str.upper()
    sla_clean = sla_clean.drop(columns=['station', 'feeder_name'], errors='ignore')
    
    # Join on both station and feeder name using clean keys
    feeder_party_pivot = feeder_party_pivot.merge(
        sla_clean,
        on=['station_clean', 'feeder_clean'],
        how='left'
    )
    
    # Drop the temporary clean merge columns
    feeder_party_pivot = feeder_party_pivot.drop(columns=['station_clean', 'feeder_clean'], errors='ignore')

# Handle missing SLA compliance values
if 'maximum_outage_hours' not in feeder_party_pivot.columns:
    feeder_party_pivot['maximum_outage_hours'] = 4.0 * days_span
else:
    feeder_party_pivot['maximum_outage_hours'] = feeder_party_pivot['maximum_outage_hours'].fillna(4.0 * days_span)

if 'actual_outage_hours' not in feeder_party_pivot.columns:
    feeder_party_pivot['actual_outage_hours'] = "Assumed 4 hours/day (not in db)"
else:
    feeder_party_pivot['actual_outage_hours'] = feeder_party_pivot['actual_outage_hours'].fillna("Assumed 4 hours/day (not in db)")

# Calculate disco and tcn allowances
feeder_party_pivot['max_hours_disco'] = feeder_party_pivot['maximum_outage_hours'] * 0.7
feeder_party_pivot['max_hours_tcn'] = feeder_party_pivot['maximum_outage_hours'] * 0.3

# Ensure the dynamic total_outage_hour_TCN column exists and default to zero when absent
if 'total_outage_hour_TCN' not in feeder_party_pivot.columns:
    feeder_party_pivot['total_outage_hour_TCN'] = 0.0
else:
    feeder_party_pivot['total_outage_hour_TCN'] = feeder_party_pivot['total_outage_hour_TCN'].fillna(0.0)

# Compute the remaining/available hours for TCN
feeder_party_pivot['available_outage_hours_tcn'] = (
    feeder_party_pivot['max_hours_tcn'] - feeder_party_pivot['total_outage_hour_TCN']
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

# apply color styling to available hours column (green if positive, red if negative)
def style_available_hours(val):
    if val > 0:
        return 'color: green'
    elif val < 0:
        return 'color: red'
    else:
        return ''

styler = filtered.style.map(
    style_available_hours,
    subset=['available_outage_hours_tcn']
)

st.dataframe(styler)

fig = px.bar(feeder_summary.head(20), x='feeder_33kv', y='outage_hrs', title='Top feeders by total outage minutes')
st.plotly_chart(fig, use_container_width=True)
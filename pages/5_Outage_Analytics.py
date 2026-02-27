"""
### FILE: pages/5_Outage_Analytics.py
Outage analysis page: frequency, duration, cause analysis and simple SAIDI/SAIFI approximation
"""

import streamlit as st
from utils.auth import login
import pandas as pd
import plotly.express as px
from utils.db import read_outages
from datetime import date, timedelta

login()

st.set_page_config(page_title="Outage Analytics", layout="wide")

st.title("Outage Analytics")

today = date.today()
start_default = today - timedelta(days=30)
start_date, end_date = st.date_input("Select date range", value=[start_default, today], key="outage_dates")

out_df = read_outages(str(start_date), str(end_date))
if out_df.empty:
    st.warning("No outage records for this range")
    st.stop()

# filtering controls for region/disco/area/station
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

# Simple KPIs
col1, col2, col3 = st.columns(3)
num_outages = len(out_df)
# compute durations in minutes when date_on/time_on available
out_df['start_ts'] = pd.to_datetime(out_df['date_off'].astype(str) + ' ' + out_df['time_off'].astype(str), errors='coerce')
out_df['end_ts'] = pd.to_datetime(out_df['date_on'].astype(str) + ' ' + out_df['time_on'].astype(str), errors='coerce')
out_df['duration_min'] = (out_df['end_ts'] - out_df['start_ts']).dt.total_seconds() / 60.0

total_outage_minutes = out_df['duration_min'].sum(skipna=True)
avg_duration = out_df['duration_min'].mean()

col1.metric("Number of outages", f"{num_outages}")
col2.metric("Total outage minutes", f"{total_outage_minutes:.1f}")
col3.metric("Avg outage (min)", f"{avg_duration:.1f}")

# Outage cause pie
cause_cnt = out_df['outage_class'].fillna('Unknown').value_counts().reset_index()
cause_cnt.columns = ['outage_class', 'count']
fig = px.pie(cause_cnt, names='outage_class', values='count', title='Outage Causes')
st.plotly_chart(fig, use_container_width=True)

# Party responsible bar
party = out_df['party_responsible'].fillna('Unknown').value_counts().reset_index()
party.columns = ['party', 'count']
fig2 = px.bar(party, x='party', y='count', title='Party Responsible (count)')
st.plotly_chart(fig2, use_container_width=True)

# Outage frequency by feeder
feeder_cnt = out_df.groupby('feeder_33kv').size().reset_index(name='count').sort_values('count', ascending=False).head(20)
fig3 = px.bar(feeder_cnt, x='feeder_33kv', y='count', title='Top feeders by outage count')
st.plotly_chart(fig3, use_container_width=True)
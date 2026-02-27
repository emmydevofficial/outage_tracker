"""
### FILE: pages/2_Station_Load_Analysis.py
Station-level analysis
"""

import streamlit as st
from utils.auth import login
import plotly.express as px
import pandas as pd
from utils.db import read_feeder_load
from datetime import date, timedelta

login()

st.set_page_config(page_title="Station Load Analysis", layout="wide")

st.title("Station Load Analysis")

today = date.today()
start_default = today - timedelta(days=7)
start_date, end_date = st.date_input("Select date range", value=[start_default, today], key="station_dates")

feeder_df = read_feeder_load(str(start_date), str(end_date))
if feeder_df.empty:
    st.warning("No data for this range")
    st.stop()

station = st.selectbox("Select Station", options=sorted(feeder_df["station"].dropna().unique()))
station_df = feeder_df[feeder_df["station"] == station]

# station KPIs
grouped_data = station_df.groupby(['reading_date', 'reading_time'])['load_mw'].sum().reset_index()
grouped_data = grouped_data.sort_values(by=['reading_date', 'reading_time'])

col1, col2, col3, col4 = st.columns(4)
max_load_row = grouped_data.loc[grouped_data['load_mw'].idxmax()]
max_load = max_load_row['load_mw']
max_date = max_load_row['reading_date']
max_time = max_load_row['reading_time']

min_load_row = grouped_data.loc[grouped_data['load_mw'].idxmin()]
min_load = min_load_row['load_mw']
min_date = min_load_row['reading_date']
min_time = min_load_row['reading_time']

unique_station = station_df["feeder_33kv"].nunique()

#col1.metric("Max Load (MW)", f"{station_df['load_mw'].max():.3f}")
col1.metric(f"Max Load (MW)", f"{max_load:.3f}", help=f"Date: {max_date} @ {max_time}")
col2.metric("Avg Load (MW)", f"{grouped_data['load_mw'].mean():.3f}")
col3.metric(f"Min Load (MW) (Date {min_date} at {min_time})", f"{min_load:.3f}")
col4.metric("Feeders", f"{unique_station}")

# plot hourly
station_hourly = station_df.groupby(["reading_time"])["load_mw"].sum().reset_index()
fig = px.line(station_hourly.sort_values("reading_time"), x="reading_time", y="load_mw", title=f"Station hourly load — {station}")
st.plotly_chart(fig, use_container_width=True)

# feeder contributions
feed_contrib = station_df.groupby("feeder_33kv")["load_mw"].mean().reset_index().sort_values("load_mw", ascending=False)
fig2 = px.pie(feed_contrib, names="feeder_33kv", values="load_mw", title="Feeder Contribution (Avg Load)")
st.plotly_chart(fig2, use_container_width=True)
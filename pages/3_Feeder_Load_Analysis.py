"""
### FILE: pages/3_Feeder_Load_Analysis.py
Feeder-level analysis and top feeders
"""

import streamlit as st
from utils.auth import login
import plotly.express as px
import pandas as pd
from utils.db import read_feeder_load
from datetime import date, timedelta

login()

st.set_page_config(page_title="Feeder Load Analysis", layout="wide")

st.title("Feeder Load Analysis")

today = date.today()
start_default = today - timedelta(days=7)
start_date, end_date = st.date_input("Select date range", value=[start_default, today], key="feeder_dates")

feeder_df = read_feeder_load(str(start_date), str(end_date))
if feeder_df.empty:
    st.warning("No data for this range")
    st.stop()

feeder = st.selectbox("Select Feeder", options=sorted(feeder_df["feeder_33kv"].dropna().unique()))
feeder_df_sel = feeder_df[feeder_df["feeder_33kv"] == feeder]

max_idx = feeder_df_sel['load_mw'].idxmax()
max_value = feeder_df_sel.loc[max_idx, 'load_mw']
max_date = feeder_df_sel.loc[max_idx, 'reading_date']
max_time = feeder_df_sel.loc[max_idx, 'reading_time']

k1, k2, k3 = st.columns(3)
k1.metric(
    "Max (MW)",
    f"{max_value:.3f}",
    help=f"Date: {max_date} @ {max_time}"
)
# k1.metric("Max (MW)", f"{feeder_df_sel['load_mw'].max():.3f}")
k2.metric("Avg (MW)", f"{feeder_df_sel['load_mw'].mean():.3f}")
k3.metric("Min (MW)", f"{feeder_df_sel['load_mw'].min():.3f}")

# hourly
feeder_hourly = feeder_df_sel.groupby(["reading_time"])["load_mw"].sum().reset_index()
fig = px.line(feeder_hourly.sort_values("reading_time"), x="reading_time", y="load_mw", title=f"Feeder hourly load — {feeder}")
st.plotly_chart(fig, use_container_width=True)
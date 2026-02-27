"""
### FILE: pages/4_Transformer_Load.py
Transformer-level analysis
"""

import streamlit as st
from utils.auth import login
import plotly.express as px
import pandas as pd
from utils.db import read_transformer_load
from datetime import date, timedelta

login()

st.set_page_config(page_title="Transformer Load", layout="wide")

st.title("Transformer Load Analysis")

today = date.today()
start_default = today - timedelta(days=7)
start_date, end_date = st.date_input("Select date range", value=[start_default, today], key="transformer_dates")

trans_df = read_transformer_load(str(start_date), str(end_date))
if trans_df.empty:
    st.warning("No data for this range")
    st.stop()

station = st.selectbox("Station", options=sorted(trans_df['station'].dropna().unique()))
trans_sel = trans_df[trans_df['station'] == station]

k1, k2 = st.columns(2)
k1.metric("Max Load (MW)", f"{trans_sel['load_mw'].max():.3f}")
k2.metric("Avg Load (MW)", f"{trans_sel['load_mw'].mean():.3f}")

load_by_tx = trans_sel.groupby('transformer_nomenclature')['load_mw'].mean().reset_index().sort_values('load_mw', ascending=False)
fig = px.bar(load_by_tx.head(10), x='transformer_nomenclature', y='load_mw', title=f"Transformer Loading (Avg) — {station}")
st.plotly_chart(fig, use_container_width=True)
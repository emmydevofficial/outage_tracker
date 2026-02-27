
"""
### FILE: pages/1_Region_Load_Analysis.py
Region-level KPIs and charts
"""

import streamlit as st
from utils.auth import login
import plotly.express as px
import pandas as pd
from utils.db import read_feeder_load
from utils.pdf_generator import generate_pdf
from datetime import date, timedelta

# enforce authentication
login()

st.set_page_config(page_title="Region Load Analysis", layout="wide")

st.title("Region Load Analysis")

# Date range picker
today = date.today()
start_default = today - timedelta(days=7)
start_date, end_date = st.date_input("Select date range", value=[start_default, today])

if start_date > end_date:
    st.error("Start date must be before end date")
    st.stop()

# Fetch data
with st.spinner("Loading feeder data..."):
    feeder_df = read_feeder_load(str(start_date), str(end_date))

if feeder_df.empty:
    st.warning("No feeder load data for this date range")
    st.stop()

# Aggregate by region and reading_time
# Group by reading_date and reading_time, summing the 

region_group = (
    feeder_df.groupby(["reading_date", "reading_time", "region"])["load_mw"]
    .sum()
    .reset_index()
)



grouped_data = feeder_df.groupby(['reading_date', 'reading_time'])['load_mw'].sum().reset_index()
grouped_data = grouped_data.sort_values(by=['reading_date', 'reading_time'])

# KPI row
col1, col2, col3, col4 = st.columns(4)
max_load_row = grouped_data.loc[grouped_data['load_mw'].idxmax()]
max_load = max_load_row['load_mw']
max_date = max_load_row['reading_date']
max_time = max_load_row['reading_time']

min_load_row = grouped_data.loc[grouped_data['load_mw'].idxmin()]
min_load = min_load_row['load_mw']
min_date = min_load_row['reading_date']
min_time = min_load_row['reading_time']

avg_load = grouped_data["load_mw"].mean()
unique_regions = feeder_df["region"].nunique()

col1.metric(f"Max Load (MW)", f"{max_load:.3f}", help=f"Date {max_date} at {max_time}")
col2.metric("Avg Load (MW)", f"{avg_load:.3f}")
col3.metric(f"Min Load (MW)", f"{min_load:.3f}", help=f"Date {min_date} at {min_time}")
col4.metric("Regions", f"{unique_regions}")



# Region selector
region = st.selectbox("Select Region", options=sorted(feeder_df["region"].dropna().unique()))
region_df = feeder_df[feeder_df["region"] == region]

# Hourly line plot for selected region (sum across feeders)
region_hourly = region_df.groupby(["reading_time"])["load_mw"].sum().reset_index()
region_hourly = region_hourly.sort_values("reading_time")

fig = px.line(region_hourly, x="reading_time", y="load_mw", title=f"Hourly Load for {region}")
st.plotly_chart(fig, use_container_width=True)

# Top feeders in region
top_feed = region_df.groupby("feeder_33kv")["load_mw"].mean().reset_index().sort_values("load_mw", ascending=False).head(10)
fig2 = px.bar(top_feed, x="feeder_33kv", y="load_mw", title=f"Top 10 Feeders by Avg Load ({region})")
st.plotly_chart(fig2, use_container_width=True)

# Export to PDF
if st.button("Generate PDF Report (Region)"):
    tmp_img1 = "region_hourly.png"
    tmp_img2 = "region_top_feed.png"
    fig.write_image(tmp_img1)
    fig2.write_image(tmp_img2)
    pdf_path = generate_pdf(f"Region Load Report — {region}", [tmp_img1, tmp_img2], out_path=f"region_report_{region}.pdf")
    with open(pdf_path, "rb") as f:
        st.download_button("Download PDF", data=f, file_name=pdf_path)

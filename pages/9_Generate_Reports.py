"""
### FILE: pages/9_Generate_Reports.py
Generate comprehensive outage reports by region in MS-Word and PDF formats.
Combines data from Outage Analytics (page 5) and Reliability KPI Report (page 6).
"""

import streamlit as st
from utils.auth import login
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.db import read_outages, read_tcn_sla_compliance, read_outages_using_date_off
from utils.report_generator import generate_word_report, generate_pdf_report_with_tables
from datetime import date, timedelta
import os
import tempfile
import calendar

login()

st.set_page_config(page_title="Generate Reports", layout="wide")

st.title("📊 Generate Outage Reports by Region")
st.markdown("Generate comprehensive outage analysis reports in MS-Word and PDF formats.")

# ===========================
# DATE RANGE SELECTION
# ===========================
col1, col2 = st.columns(2)

with col1:
    today = date.today()
    start_default = today - timedelta(days=30)
    start_date, end_date = st.date_input(
        "Select date range",
        value=[start_default, today],
        key="report_dates"
    )

# ===========================
# LOAD DATA
# ===========================
with st.spinner("Loading outage data..."):
    out_df = read_outages(str(start_date), str(end_date))
    out_with_date_off_df = read_outages_using_date_off(str(start_date), str(end_date))

if out_df.empty:
    st.warning("No outage records for this range")
    st.stop()

# ===========================
# REGION SELECTION
# ===========================
regions = sorted(out_df["region"].dropna().unique())

with col2:
    selected_regions = st.multiselect(
        "Select regions for report",
        options=regions,
        default=[regions[0]] if regions else [],
        key="report_regions"
    )

if not selected_regions:
    st.warning("Please select at least one region")
    st.stop()

# ===========================
# GENERATE REPORTS
# ===========================

st.subheader("Generate Reports")

# Calculate required columns
out_df['start_ts'] = pd.to_datetime(
    out_df['date_off'].astype(str) + ' ' + out_df['time_off'].astype(str),
    errors='coerce'
)
out_df['end_ts'] = pd.to_datetime(
    out_df['date_on'].astype(str) + ' ' + out_df['time_on'].astype(str),
    errors='coerce'
)
out_df['duration_min'] = (out_df['end_ts'] - out_df['start_ts']).dt.total_seconds() / 60.0
out_df['last_load'] = pd.to_numeric(out_df['last_load'], errors='coerce')
out_df['duration_hr'] = out_df['duration_min'] / 60.0
out_df['load_loss_mwh'] = out_df['duration_hr'] * out_df['last_load']

# Process each region
col_word, col_pdf = st.columns(2)

for region in selected_regions:
    st.markdown(f"### {region}")
    
    # Filter data for this region
    region_df = out_df[out_df['region'] == region].copy()
    region_with_date_off_df = out_with_date_off_df[out_with_date_off_df['region'] == region].copy()
    
    if region_df.empty:
        st.warning(f"No data for {region}")
        continue
    
    # ===========================
    # CALCULATE SUMMARY STATISTICS
    # ===========================
    num_outages = len(region_df)
    total_outage_minutes = region_df['duration_min'].sum(skipna=True)
    avg_duration = region_df['duration_min'].mean()
    total_load_loss_mwh = region_df['load_loss_mwh'].sum(skipna=True)
    avg_load_loss_mwh = region_df['load_loss_mwh'].mean()
    
    summary_stats = {
        'num_outages': num_outages,
        'total_minutes': total_outage_minutes,
        'avg_duration_min': avg_duration,
        'total_load_loss_mwh': total_load_loss_mwh,
        'avg_load_loss_mwh': avg_load_loss_mwh
    }
    
    # Display metrics
    metric_cols = st.columns(5)
    metric_cols[0].metric("Total Outages", num_outages)
    metric_cols[1].metric("Total Minutes", f"{total_outage_minutes:.0f}")
    metric_cols[2].metric("Total Hours", f"{total_outage_minutes / 60:.1f}")
    metric_cols[3].metric("Avg Duration (min)", f"{avg_duration:.1f}")
    metric_cols[4].metric("Total Load Loss (MWh)", f"{total_load_loss_mwh:.2f}")
    
    # ===========================
    # GENERATE SUMMARIES
    # ===========================
    
    # Station summary
    station_summary = region_df.groupby('station').agg(
        outages_count=('id', 'count'),
        total_outage_min=('duration_min', 'sum'),
        total_load_loss_mwh=('load_loss_mwh', 'sum')
    ).reset_index().sort_values('total_outage_min', ascending=False)
    station_summary['avg_outage_min'] = station_summary['total_outage_min'] / station_summary['outages_count']
    station_summary['avg_load_loss_mwh'] = station_summary['total_load_loss_mwh'] / station_summary['outages_count']
    
    # Feeder summary
    feeder_summary = region_df.groupby('feeder_33kv').agg(
        outages_count=('id', 'count'),
        total_outage_min=('duration_min', 'sum'),
        total_load_loss_mwh=('load_loss_mwh', 'sum')
    ).reset_index().sort_values('total_outage_min', ascending=False)
    feeder_summary['avg_outage_hrs'] = feeder_summary['total_outage_min'] / feeder_summary['outages_count'] / 60.0
    feeder_summary['outage_hrs'] = feeder_summary['total_outage_min'] / 60.0
    feeder_summary['avg_load_loss_mwh'] = feeder_summary['total_load_loss_mwh'] / feeder_summary['outages_count']
    
    # Cause summary
    cause_summary = region_df['outage_class'].fillna('Unknown').value_counts().reset_index()
    cause_summary.columns = ['outage_class', 'count']
    cause_summary = cause_summary.sort_values('count', ascending=False)
    
    # Party responsible summary
    party_summary = region_df['party_responsible'].fillna('Unknown').value_counts().reset_index()
    party_summary.columns = ['party_responsible', 'count']
    party_summary = party_summary.sort_values('count', ascending=False)
    
    # ===========================
    # RELIABILITY KPI CALCULATIONS (From Page 6)
    # ===========================
    
    # Calculate month clipping boundaries
    month_start = pd.Timestamp(start_date.replace(day=1))
    last_day = calendar.monthrange(end_date.year, end_date.month)[1]
    month_end = pd.Timestamp(end_date.replace(day=last_day)) + pd.Timedelta(days=1)
    
    # Clip durations to month boundaries
    region_df_clipped = region_df.copy()
    region_df_clipped['clipped_start'] = region_df_clipped['start_ts'].clip(lower=month_start, upper=month_end)
    region_df_clipped['clipped_end'] = region_df_clipped['end_ts'].clip(lower=month_start, upper=month_end)
    region_df_clipped['duration_min_clipped'] = (region_df_clipped['clipped_end'] - region_df_clipped['clipped_start']).dt.total_seconds() / 60.0
    region_df_clipped['duration_min_clipped'] = region_df_clipped['duration_min_clipped'].clip(lower=0)
    
    # Outage Table By Party Responsible
    days_span = (end_date - start_date).days + 1
    
    feeder_party_pivot = region_df_clipped.groupby(['station', 'feeder_33kv', 'party_responsible']).agg(
        total_outage_hour=('duration_min_clipped', lambda x: x.sum() / 60)
    ).reset_index().pivot_table(
        index=['station', 'feeder_33kv'],
        columns='party_responsible',
        values='total_outage_hour',
        aggfunc='sum',
        fill_value=0
    )
    
    feeder_party_pivot.columns.name = None
    feeder_party_pivot = feeder_party_pivot.reset_index()
    
    # Try to merge with SLA data
    try:
        sla = read_tcn_sla_compliance()
        if not sla.empty:
            sla['maximum_outage_hours'] = sla['maximum_outage_hours'] * days_span
            
            feeder_party_pivot = feeder_party_pivot.merge(
                sla,
                left_on=['station', 'feeder_33kv'],
                right_on=['station', 'feeder_name'],
                how='left'
            )
            
            if 'feeder_name' in feeder_party_pivot.columns:
                feeder_party_pivot = feeder_party_pivot.drop(columns=['feeder_name'])
    except:
        pass
    
    # Set default SLA if not available
    if 'maximum_outage_hours' not in feeder_party_pivot.columns:
        feeder_party_pivot['maximum_outage_hours'] = 4 * days_span
    else:
        feeder_party_pivot['maximum_outage_hours'] = feeder_party_pivot['maximum_outage_hours'].fillna(4 * days_span)
    
    # Calculate allocations
    feeder_party_pivot['max_hours_disco'] = feeder_party_pivot['maximum_outage_hours'] * 0.7
    feeder_party_pivot['max_hours_tcn'] = feeder_party_pivot['maximum_outage_hours'] * 0.3
    
    # Ensure TCN column exists
    if 'TCN' not in feeder_party_pivot.columns:
        feeder_party_pivot['TCN'] = 0
    
    # Compute remaining/available hours for TCN
    feeder_party_pivot['available_outage_hours_tcn'] = (
        feeder_party_pivot['max_hours_tcn'] - feeder_party_pivot['TCN']
    )
    
    # Reset index
    feeder_party_pivot = feeder_party_pivot.reset_index(drop=True)
    
    # Filter for negative availability (violations)
    feeder_party_pivot_violations = feeder_party_pivot[feeder_party_pivot['available_outage_hours_tcn'] < 0].copy()
    
    # ===========================
    # ADDITIONAL TABLES FOR REPORT
    # ===========================
    
    # 1. Top 20% most prolonged outages
    prolonged_outages = region_df.sort_values('duration_min', ascending=False)
    top_20_percent_count = max(1, int(len(prolonged_outages) * 0.2))  # At least 1
    top_prolonged_outages = prolonged_outages.head(top_20_percent_count)[['station', 'feeder_33kv', 'date_off', 'time_off', 'duration_min', 'load_loss_mwh', 'outage_class', 'party_responsible']].copy()
    
    # 2. Wrong attribution for party_responsible
    correct_parties = ['DISCO', 'Disco', 'TCN', 'GENCO']
    wrong_attribution = region_df[~region_df['party_responsible'].isin(correct_parties)][['station', 'feeder_33kv', 'date_off', 'time_off', 'party_responsible', 'outage_class']].copy()
    
    # 3. Outages with missing values (excluding date_on and time_on)
    exclude_cols = ['date_on', 'time_on']
    check_cols = [col for col in region_df.columns if col not in exclude_cols]
    missing_rows = region_df[region_df[check_cols].isnull().any(axis=1)].copy()
    
    # Add helper column listing columns with missing values per record
    def get_missing_columns(row):
        missing = []
        for col in check_cols:
            if pd.isna(row[col]) or (isinstance(row[col], str) and row[col].strip() == ""):
                missing.append(col)
        return ", ".join(missing)
    
    missing_rows['missing_columns'] = missing_rows.apply(get_missing_columns, axis=1)
    missing_values_outages = missing_rows[['station', 'feeder_33kv', 'date_off', 'time_off', 'outage_class', 'party_responsible', 'missing_columns']].copy()
    
    # 4. Feeders yet to be restored (date_on and time_on are empty)
    unrestored_feeders = region_with_date_off_df[(region_with_date_off_df['date_on'].isnull() | (region_with_date_off_df['date_on'] == "")) & (region_with_date_off_df['time_on'].isnull() | (region_with_date_off_df['time_on'] == ""))][['station', 'feeder_33kv', 'date_off', 'time_off', 'outage_class', 'party_responsible']].copy()
    
    # ===========================
    # CREATE CHARTS
    # ===========================
    
    with tempfile.TemporaryDirectory() as tmpdir:
        image_paths = []
        
        # Chart 1: Outage Causes Pie Chart
        if not cause_summary.empty:
            fig1 = px.pie(
                cause_summary,
                names='outage_class',
                values='count',
                title=f'{region} - Outage Causes Distribution'
            )
            fig1.update_layout(template="plotly")
            fig1.update_traces(textposition='inside', textinfo='percent+label')
            chart1_path = os.path.join(tmpdir, f"chart_causes_{region}.png")
            fig1.write_image(chart1_path, width=1000, height=600)
            image_paths.append(chart1_path)
            st.plotly_chart(fig1, use_container_width=True)
        
        # Chart 2: Party Responsible Bar Chart
        if not party_summary.empty:
            fig2 = px.bar(
                party_summary,
                x='party_responsible',
                y='count',
                title=f'{region} - Party Responsible (count)',
                labels={'party_responsible': 'Party', 'count': 'Count'}
            )
            fig2.update_layout(template="plotly")
            fig2.update_xaxes(tickangle=-45)
            chart2_path = os.path.join(tmpdir, f"chart_party_{region}.png")
            fig2.write_image(chart2_path, width=1000, height=600)
            image_paths.append(chart2_path)
            st.plotly_chart(fig2, use_container_width=True)
        
        # Chart 3: Top Stations by Outage Minutes
        if not station_summary.empty:
            fig3 = px.bar(
                station_summary.head(15),
                x='station',
                y='total_outage_min',
                title=f'{region} - Top Stations by Outage Minutes',
                labels={'station': 'Station', 'total_outage_min': 'Minutes'}
            )
            fig3.update_layout(template="plotly")
            fig3.update_xaxes(tickangle=-45)
            chart3_path = os.path.join(tmpdir, f"chart_stations_{region}.png")
            fig3.write_image(chart3_path, width=1000, height=600)
            image_paths.append(chart3_path)
            st.plotly_chart(fig3, use_container_width=True)
        
        # Chart 4: Top Feeders by Outage Hours
        if not feeder_summary.empty:
            fig4 = px.bar(
                feeder_summary.head(15),
                x='feeder_33kv',
                y='outage_hrs',
                title=f'{region} - Top Feeders by Outage Hours',
                labels={'feeder_33kv': 'Feeder', 'outage_hrs': 'Hours'}
            )
            fig4.update_layout(template="plotly")
            fig4.update_xaxes(tickangle=-45)
            chart4_path = os.path.join(tmpdir, f"chart_feeders_{region}.png")
            fig4.write_image(chart4_path, width=1000, height=600)
            image_paths.append(chart4_path)
            st.plotly_chart(fig4, use_container_width=True)
        
        # ===========================
        # DOWNLOAD BUTTONS
        # ===========================
        st.markdown("---")
        col_word, col_pdf = st.columns(2)
        
        with col_word:
            st.subheader("📄 Download Word Report")
            
            # Generate Word report
            word_filename = f"Outage_Report_{region}_{start_date}_{end_date}.docx"
            word_path = os.path.join(tmpdir, word_filename)
            
            try:
                generate_word_report(
                    region=region,
                    start_date=str(start_date),
                    end_date=str(end_date),
                    summary_stats=summary_stats,
                    outage_df=region_df,
                    station_summary=station_summary,
                    feeder_summary=feeder_summary,
                    cause_summary=cause_summary,
                    party_summary=party_summary,
                    image_paths=image_paths,
                    output_path=word_path,
                    feeder_party_pivot=feeder_party_pivot,
                    feeder_party_violations=feeder_party_pivot_violations,
                    top_prolonged_outages=top_prolonged_outages,
                    wrong_attribution=wrong_attribution,
                    missing_values_outages=missing_values_outages,
                    unrestored_feeders=unrestored_feeders
                )
                
                with open(word_path, "rb") as f:
                    st.download_button(
                        label="📥 Download Word (.docx)",
                        data=f.read(),
                        file_name=word_filename,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"download_word_{region}"
                    )
                st.success(f"✅ Word report ready for {region}")
            except Exception as e:
                st.error(f"Error generating Word report: {str(e)}")
        
        with col_pdf:
            st.subheader("📋 Download PDF Report")
            
            # Generate PDF report
            pdf_filename = f"Outage_Report_{region}_{start_date}_{end_date}.pdf"
            pdf_path = os.path.join(tmpdir, pdf_filename)
            
            try:
                generate_pdf_report_with_tables(
                    region=region,
                    start_date=str(start_date),
                    end_date=str(end_date),
                    summary_stats=summary_stats,
                    outage_df=region_df,
                    station_summary=station_summary,
                    feeder_summary=feeder_summary,
                    image_paths=image_paths,
                    output_path=pdf_path,
                    feeder_party_pivot=feeder_party_pivot,
                    feeder_party_violations=feeder_party_pivot_violations
                )
                
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        label="📥 Download PDF",
                        data=f.read(),
                        file_name=pdf_filename,
                        mime="application/pdf",
                        key=f"download_pdf_{region}"
                    )
                st.success(f"✅ PDF report ready for {region}")
            except Exception as e:
                st.error(f"Error generating PDF report: {str(e)}")
        
        st.markdown("---")

st.markdown("---")
st.info("💡 Tip: You can generate reports for multiple regions at once and download them all.")

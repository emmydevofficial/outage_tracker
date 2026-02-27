"""
### FILE: pages/7_Upload_Outages.py
Utility page that allows the user to upload a CSV file containing outage
records and push the rows into the PostgreSQL ``outages`` table.  The
uploader expects the CSV to follow the layout described in the project
requirements (hour/minute columns that will be collapsed).
"""

import streamlit as st
from utils.auth import login
import pandas as pd
import numpy as np
from utils.db import insert_outages, insert_outages_from_csv

login()

st.set_page_config(page_title="Upload Outages", layout="wide")

st.title("📁 Upload Outage CSV")

upload = st.file_uploader("Choose outage CSV file", type=["csv"])

EXPECTED_COLUMNS = [
    "disco",
    "region",
    "area",
    "station",
    "feeder_33kv",
    "date_off",
    "hour_off",
    "minute_off",
    "date_on",
    "hour_on",
    "minute_on",
    "duration_outage",
    "outage_class",
    "last_load",
    "event_indication",
    "party_responsible",
    "officer_confirming_interruption",
    "officer_confirming_restoration",
    "weather_condition",
    "remarks",
]

if upload is not None:
    # try a few common encodings since uploaded files may not be utf-8
    encodings = ("utf-8", "utf-8-sig", "cp1252", "latin1")
    df = None
    last_exc = None
    for enc in encodings:
        try:
            upload.seek(0)
            df = pd.read_csv(upload, encoding=enc)
            break
        except Exception as exc:
            last_exc = exc
    if df is None:
        st.error(f"Failed to read CSV: {last_exc}")
        st.stop()

    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        st.error("Uploaded file is missing expected columns: %s" % ", ".join(missing))
        st.stop()

    

    # Custom time handling: safely collapse hour/minute into HH:MM and
    # leave missing values as None/NaN.
    def _assemble_time(df, hour_col, minute_col, out_col):
        # get left-of-colon and right-of-colon parts if the cell contains a hh:mm
        hour_str = df[hour_col].astype("string").str.partition(":")[0]
        minute_str = df[minute_col].astype("string").str.partition(":")[2]

        hour_num = pd.to_numeric(hour_str, errors="coerce")
        minute_num = pd.to_numeric(minute_str, errors="coerce")

        mask = hour_num.notna() & minute_num.notna()

        out = pd.Series([None] * len(df), index=df.index, dtype="object")
        if mask.any():
            hh = hour_num[mask].astype(int).astype(str).str.zfill(2)
            mm = minute_num[mask].astype(int).astype(str).str.zfill(2)
            out.loc[mask] = hh + ":" + mm

        df[out_col] = out

    _assemble_time(df, "hour_off", "minute_off", "time_off")
    _assemble_time(df, "hour_on", "minute_on", "time_on")

    # coerce dates and numeric columns
    df["date_off"] = pd.to_datetime(df["date_off"], errors="coerce").dt.date
    # for date_on, handle None/empty values
    df["date_on"] = pd.to_datetime(df["date_on"], errors="coerce").dt.date
    df["last_load"] = pd.to_numeric(df["last_load"], errors="coerce")

    # final frame for insertion
    insert_df = df[
        [
            "disco",
            "region",
            "area",
            "station",
            "feeder_33kv",
            "date_off",
            "time_off",
            "date_on",
            "time_on",
            "duration_outage",
            "outage_class",
            "last_load",
            "event_indication",
            "party_responsible",
            "officer_confirming_interruption",
            "officer_confirming_restoration",
            "weather_condition",
            "remarks",
        ]
    ]

    st.subheader("Preview of parsed records")
    st.dataframe(insert_df.head())
    st.write(f"Total rows to upload: {len(insert_df)}")

    # write processed dataframe to a temporary file so we can use COPY path
    import tempfile, os
    tmp_path = None
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", encoding="utf-8", newline="")
        # write the already-transformed dataframe rather than raw upload bytes
        insert_df.to_csv(tmp, index=False, encoding="utf-8")
        tmp.flush()
        tmp_path = tmp.name
        tmp.close()
    except Exception:
        tmp_path = None

    if st.button("Upload to database"):
        try:
            if tmp_path and os.path.exists(tmp_path):
                # prefer the faster CSV-based path when available
                insert_outages_from_csv(tmp_path)
            else:
                insert_outages(insert_df)
            st.success("Outage records successfully inserted into database")
        except Exception as e:
            st.error(f"Error inserting records: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

from typing import Tuple
import os
import pandas as pd
from sqlalchemy import create_engine, text
import streamlit as st
import pandas as pd

# if a .env file exists, load variables from it (python-dotenv)
from dotenv import load_dotenv
load_dotenv()

# new helper for writing dataframes to the database

# connection string can be provided through the DATABASE_URL environment
# variable.  This allows the same code to work locally (development) and
# in production without editing the source.  If the variable is missing we
# fall back to a sensible local default but log a warning so the user knows.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # default is convenient for development but should be overridden in
    # staging/production environments.
    DATABASE_URL = "postgresql+psycopg2://postgres:jagrelem@localhost:5432/rcc_test"
    import warnings
    warnings.warn(
        "DATABASE_URL not set; using built-in sqlite default.\n"
        "Set the DATABASE_URL environment variable to point to your PostgreSQL instance.",
        UserWarning,
    )

# -----------------------------
# CACHE ENGINE AS RESOURCE
# -----------------------------
@st.cache_resource
def get_engine():
    return create_engine(DATABASE_URL, pool_pre_ping=True)

# -----------------------------
# CACHE DATA AS DATA (SERIALIZABLE)
# -----------------------------
time_order = [ '01:00', '02:00', '03:00', '04:00', 
              '05:00',     '06:00', '07:00', '08:00', '09:00', 
              '10:00', '11:00',     '12:00', '13:00', '14:00', '15:00', 
              '16:00', '17:00',     '18:00', '19:00', '20:00', 
              '21:00', '22:00', '23:00',     '24:00']
def order_reading_time(data):
    data['reading_time'] = pd.Categorical(data['reading_time'], categories=time_order, ordered=True)
    return data

@st.cache_data(ttl=300)
def read_feeder_load(start_date: str, end_date: str) -> pd.DataFrame:
    engine = get_engine()
    query = text("""
        SELECT reading_date, reading_time, region, area, feeder as feeder_33kv, customer, station, load_mw
        FROM feeder_33kv_load
        WHERE reading_date BETWEEN :start_date AND :end_date
        ORDER BY reading_date, reading_time
    """)
    
    data = pd.read_sql_query(query, engine, params={"start_date": start_date, "end_date": end_date})
    return order_reading_time(data)

@st.cache_data(ttl=300)
def read_line_load(start_date: str, end_date: str) -> pd.DataFrame:
    engine = get_engine()
    query = text("""
        SELECT reading_date, reading_time, region, area, transmission_interface, disco, line_voltage,
               line_nomenclature, load_mw
        FROM line_load
        WHERE reading_date BETWEEN :start_date AND :end_date
        ORDER BY reading_date, reading_time
    """)
    return pd.read_sql_query(query, engine, params={"start_date": start_date, "end_date": end_date})

@st.cache_data(ttl=300)
def read_transformer_load(start_date: str, end_date: str) -> pd.DataFrame:
    engine = get_engine()
    query = text("""
        SELECT reading_date, reading_time, region, area, station, transformer_nomenclature, load_mw
        FROM transformer_load
        WHERE reading_date BETWEEN :start_date AND :end_date
        ORDER BY reading_date, reading_time
    """)

    data = pd.read_sql_query(query, engine, params={"start_date": start_date, "end_date": end_date})
    print(f"The Data\n{data}")
    return order_reading_time(data)
    #return pd.read_sql_query(query, engine, params={"start_date": start_date, "end_date": end_date})

@st.cache_data(ttl=300)
def read_outages(start_date: str, end_date: str) -> pd.DataFrame:
    engine = get_engine()
    query = text("""
        SELECT id, disco, region, area, station, feeder_33kv, date_off, time_off, date_on, time_on,
               duration_outage, outage_class, last_load, event_indication, party_responsible, weather_condition
        FROM outages
        WHERE date_off BETWEEN :start_date AND :end_date
        ORDER BY date_off, time_off
    """)
    return pd.read_sql_query(query, engine, params={"start_date": start_date, "end_date": end_date})


def insert_outages(df: pd.DataFrame) -> None:
    """Insert outage records contained in ``df`` into the permanent table.

    Internally this writes the dataframe to a CSV stream and uses a
    ``COPY`` into a temporary table.  An ``ON CONFLICT`` clause ensures that
    existing rows (keyed by station/feeder/date_off/time_off) are updated when
    certain fields differ.  This mirrors ``insert_outages_from_csv`` but
    operates on an already-loaded dataframe.
    """
    engine = get_engine()
    cols = [
        "disco", "region", "area", "station", "feeder_33kv", "date_off", "time_off",
        "date_on", "time_on", "duration_outage", "outage_class", "last_load",
        "event_indication", "party_responsible", "officer_confirming_interruption",
        "officer_confirming_restoration", "weather_condition", "remarks"
    ]

    # write df to csv buffer
    csv_buffer = df.to_csv(index=False)
    raw_conn = engine.raw_connection()
    try:
        cur = raw_conn.cursor()
        cur.execute("""
            DROP TABLE IF EXISTS temp_outages;
            CREATE TEMP TABLE temp_outages (
                disco TEXT,
                region TEXT,
                area TEXT,
                station TEXT,
                feeder_33kv TEXT,
                date_off DATE,
                time_off TIME,
                date_on DATE,
                time_on TIME,
                duration_outage TEXT,
                outage_class TEXT,
                last_load NUMERIC,
                event_indication TEXT,
                party_responsible TEXT,
                officer_confirming_interruption TEXT,
                officer_confirming_restoration TEXT,
                weather_condition TEXT,
                remarks TEXT
            )
        """)
        # copy from buffer
        from io import StringIO
        buffer = StringIO(csv_buffer)
        next(buffer)  # skip header
        cur.copy_expert("COPY temp_outages FROM STDIN WITH CSV", buffer)

        cur.execute("""
            WITH dedup AS (
                SELECT DISTINCT ON (station, feeder_33kv, date_off, time_off) *
                FROM temp_outages
                ORDER BY station, feeder_33kv, date_off, time_off, date_on DESC NULLS LAST, time_on DESC NULLS LAST
            )
            INSERT INTO outages (
                disco,
                region,
                area,
                station,
                feeder_33kv,
                date_off,
                time_off,
                date_on,
                time_on,
                duration_outage,
                outage_class,
                last_load,
                event_indication,
                party_responsible,
                officer_confirming_interruption,
                officer_confirming_restoration,
                weather_condition,
                remarks
            )
            SELECT
                disco,
                region,
                area,
                station,
                feeder_33kv,
                date_off,
                time_off,
                date_on,
                time_on,
                duration_outage,
                outage_class,
                last_load,
                event_indication,
                party_responsible,
                officer_confirming_interruption,
                officer_confirming_restoration,
                weather_condition,
                remarks
            FROM dedup
            ON CONFLICT (station, feeder_33kv, date_off, time_off)
            DO UPDATE SET
                date_on = EXCLUDED.date_on,
                time_on = EXCLUDED.time_on,
                duration_outage = EXCLUDED.duration_outage,
                outage_class = EXCLUDED.outage_class,
                last_load = EXCLUDED.last_load,
                event_indication = EXCLUDED.event_indication,
                party_responsible = EXCLUDED.party_responsible,
                officer_confirming_interruption = EXCLUDED.officer_confirming_interruption,
                officer_confirming_restoration = EXCLUDED.officer_confirming_restoration,
                weather_condition = EXCLUDED.weather_condition,
                remarks = EXCLUDED.remarks,
                updated_at = CURRENT_TIMESTAMP
            WHERE
                outages.date_on IS DISTINCT FROM EXCLUDED.date_on
                OR outages.time_on IS DISTINCT FROM EXCLUDED.time_on
                OR outages.duration_outage IS DISTINCT FROM EXCLUDED.duration_outage
                OR outages.last_load IS DISTINCT FROM EXCLUDED.last_load
                OR outages.remarks IS DISTINCT FROM EXCLUDED.remarks;
        """)
        raw_conn.commit()
    finally:
        raw_conn.close()



def insert_outages_from_csv(csv_path: str) -> None:
    """Efficiently load a CSV file directly into ``outages`` using COPY.

    The CSV must have a header matching the expected outage columns with
    ``time_off``/``time_on`` already computed (i.e. the output of the
    Streamlit uploader).  Rows are merged on the unique key defined by
    ``(station, feeder_33kv, date_off, time_off)`` with an update-if-changed
    conflict clause.
    """
    engine = get_engine()
    raw_conn = engine.raw_connection()
    try:
        cur = raw_conn.cursor()
        # create temp table
        cur.execute("""
            DROP TABLE IF EXISTS temp_outages;
            CREATE TEMP TABLE temp_outages (
                disco TEXT,
                region TEXT,
                area TEXT,
                station TEXT,
                feeder_33kv TEXT,
                date_off DATE,
                time_off TIME,
                date_on DATE,
                time_on TIME,
                duration_outage TEXT,
                outage_class TEXT,
                last_load NUMERIC,
                event_indication TEXT,
                party_responsible TEXT,
                officer_confirming_interruption TEXT,
                officer_confirming_restoration TEXT,
                weather_condition TEXT,
                remarks TEXT
            )
        """)
        with open(csv_path, 'r', encoding='utf-8') as f:
            next(f)  # skip header
            cur.copy_expert("COPY temp_outages FROM STDIN WITH CSV", f)

        cur.execute("""
            WITH dedup AS (
                SELECT DISTINCT ON (station, feeder_33kv, date_off, time_off) *
                FROM temp_outages
                ORDER BY station, feeder_33kv, date_off, time_off, date_on DESC NULLS LAST, time_on DESC NULLS LAST
            )
            INSERT INTO outages (
                disco,
                region,
                area,
                station,
                feeder_33kv,
                date_off,
                time_off,
                date_on,
                time_on,
                duration_outage,
                outage_class,
                last_load,
                event_indication,
                party_responsible,
                officer_confirming_interruption,
                officer_confirming_restoration,
                weather_condition,
                remarks
            )
            SELECT
                disco,
                region,
                area,
                station,
                feeder_33kv,
                date_off,
                time_off,
                date_on,
                time_on,
                duration_outage,
                outage_class,
                last_load,
                event_indication,
                party_responsible,
                officer_confirming_interruption,
                officer_confirming_restoration,
                weather_condition,
                remarks
            FROM dedup
            ON CONFLICT (station, feeder_33kv, date_off, time_off)
            DO UPDATE SET
                date_on = EXCLUDED.date_on,
                time_on = EXCLUDED.time_on,
                duration_outage = EXCLUDED.duration_outage,
                outage_class = EXCLUDED.outage_class,
                last_load = EXCLUDED.last_load,
                event_indication = EXCLUDED.event_indication,
                party_responsible = EXCLUDED.party_responsible,
                officer_confirming_interruption = EXCLUDED.officer_confirming_interruption,
                officer_confirming_restoration = EXCLUDED.officer_confirming_restoration,
                weather_condition = EXCLUDED.weather_condition,
                remarks = EXCLUDED.remarks,
                updated_at = CURRENT_TIMESTAMP
            WHERE
                outages.date_on IS DISTINCT FROM EXCLUDED.date_on
                OR outages.time_on IS DISTINCT FROM EXCLUDED.time_on
                OR outages.duration_outage IS DISTINCT FROM EXCLUDED.duration_outage
                OR outages.last_load IS DISTINCT FROM EXCLUDED.last_load
                OR outages.remarks IS DISTINCT FROM EXCLUDED.remarks;
        """)
        raw_conn.commit()
    finally:
        raw_conn.close()

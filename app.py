# PROJECT: Streamlit + Plotly Dashboard for Transmission Loads & Outages
# File layout (multiple files concatenated below with clear separators)

"""
### FILE: app.py
Entry point for the Streamlit app. This file provides a home/landing page and links to pages.
Run with: streamlit run app.py
"""

import streamlit as st
from utils.auth import login

# require login before doing anything else
login()

st.set_page_config(page_title="Power Ops Dashboard", layout="wide")

st.title("Power Operations Dashboard — Load & Outage Analytics")
st.markdown(
    """
    This Streamlit app contains multiple pages (use the left sidebar Pages menu).

    Pages included:
    1. Region Load Analysis
    2. Station Load Analysis
    3. Feeder Load Analysis
    4. Transformer Load
    5. Outage Analytics
    6. Reliability KPI Report

    The pages live in the `pages/` folder. Make sure you have a `utils/` folder with
    `db.py` and `pdf_generator.py`.
    """
)

st.sidebar.header("Quick actions")
if st.sidebar.button("Refresh data cache"):
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.write("Developer: Oluwaloni Emmanuel")


# ------------------------------------------------------------------
# Separator for next files
# ------------------------------------------------------------------



# ------------------------------------------------------------------
# Separator for next file
# ------------------------------------------------------------------




# ------------------------------------------------------------------
# Separator for next files (pages)
# ------------------------------------------------------------------












# End of concatenated project files

import streamlit as st
from sqlalchemy import text
import bcrypt

from .db import get_engine


def _hash_password(password: str) -> str:
    # bcrypt operates on bytes, result is bytes; decode to utf-8 for storage
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def authenticate(username: str, password: str) -> bool:
    """Verify the supplied credentials against the users table.

    The password stored in the database is a hashed bcrypt string.
    Returns True on success, False otherwise.
    """
    if not username or not password:
        return False

    engine = get_engine()
    query = text("SELECT password_hash FROM users WHERE username = :u")
    try:
        with engine.connect() as conn:
            row = conn.execute(query, {"u": username}).fetchone()
    except Exception:
        return False

    if row is None:
        return False

    stored_hash = row[0]
    return _verify_password(password, stored_hash)


def login():
    """Render a minimal login form in the sidebar and enforce authentication.

    When called at the top of every page, this helper will display a
    username/password form if the user is not already logged in.  On
    successful authentication the page is rerun and further content is
    shown.  If the user fails or has not yet submitted credentials the
    execution is stopped so that the rest of the app doesn't render.
    """
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = None

    if st.session_state.logged_in:
        # optionally provide a logout button
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.username = None
            # newer Streamlit versions use rerun()
            try:
                st.rerun()
            except Exception:
                pass
        return

    st.sidebar.title("🔐 Login")
    username = st.sidebar.text_input("Username")
    password = st.sidebar.text_input("Password", type="password")

    if st.sidebar.button("Login"):
        if authenticate(username, password):
            st.session_state.logged_in = True
            st.session_state.username = username
            try:
                st.rerun()
            except Exception:
                    pass
    st.stop()

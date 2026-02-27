"""Simple command-line utility to insert a new user into the
PostgreSQL ``users`` table defined for the Streamlit app.

Passwords are hashed with bcrypt before insertion.

Usage (from workspace root, after activating your venv):
    python add_user.py
"""
import getpass
import sys
from sqlalchemy import text
import bcrypt

from utils.db import get_engine


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def add_user(username: str, password: str) -> None:
    # bcrypt only uses the first 72 bytes of a password; enforce that here
    pw_bytes = password.encode("utf-8")
    if len(pw_bytes) > 72:
        pw_bytes = pw_bytes[:72]
        password = pw_bytes.decode("utf-8", "ignore")

    pw_hash = _hash_password(password)

    engine = get_engine()
    query = text(
        """
        INSERT INTO users (username, password_hash)
        VALUES (:u, :p)
        """
    )
    with engine.begin() as conn:
        conn.execute(query, {"u": username, "p": pw_hash})


def main():
    uname = input("Username: ")
    if not uname:
        print("Username cannot be empty", file=sys.stderr)
        sys.exit(1)
    pwd = getpass.getpass("Password: ")
    if not pwd:
        print("Password cannot be empty", file=sys.stderr)
        sys.exit(1)
    if len(pwd.encode("utf-8")) > 72:
        print("Password longer than 72 bytes will be truncated by the system.")
    confirm = getpass.getpass("Confirm password: ")
    if pwd != confirm:
        print("Passwords do not match", file=sys.stderr)
        sys.exit(1)
    try:
        add_user(uname, pwd)
    except Exception as e:
        print(f"Failed to add user: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"User '{uname}' created successfully.")


if __name__ == "__main__":
    main()

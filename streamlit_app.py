import os
import json
import re
import sqlite3
import zipfile

import pandas as pd
import streamlit as st
from google import genai
from google.genai import types

DB_FILE = "pcards.db"
if not os.path.exists(DB_FILE):
    with zipfile.ZipFile("pcards.zip", "r") as archive:
        archive.extract("pcards.db")
OSU_AGENCY_NUMBER = 1000

st.set_page_config(page_title="OSU P-Card Audit", layout="wide")
st.title("Oklahoma State University P-Card Audit")

def connect_db():
    return sqlite3.connect(DB_FILE)

def available_years():
    with connect_db() as con:
        rows = con.execute(
            "SELECT DISTINCT Year FROM pcards "
            "WHERE AgencyNumber = ? AND Year IS NOT NULL "
            "ORDER BY Year DESC",
            (OSU_AGENCY_NUMBER,)
        ).fetchall()
    return [int(row[0]) for row in rows]

def schema_text():
    with connect_db() as con:
        rows = con.execute("PRAGMA table_info(pcards)").fetchall()
    return ", ".join(f"{r[1]} {r[2]}" for r in rows)

def gemini_key():
    try:
        return st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
    except Exception:
        return os.getenv("GEMINI_API_KEY")

def validate_sql(sql, year):
    sql = sql.strip()
    if not re.match(r"^SELECT\b", sql, re.IGNORECASE):
        raise ValueError("Only SELECT queries are allowed.")
    if re.search(
        r";|--|/\*|\*/|\b(INSERT|UPDATE|DELETE|DROP|ALTER|"
        r"CREATE|ATTACH|DETACH|PRAGMA|REPLACE|VACUUM)\b",
        sql, re.IGNORECASE
    ):
        raise ValueError("Unsafe SQL was rejected.")
    if not re.search(r"\bFROM\s+pcards\b", sql, re.IGNORECASE):
        raise ValueError("Only the pcards table is allowed.")
    if not re.search(r"\bAgencyNumber\s*=\s*1000\b", sql, re.IGNORECASE):
        raise ValueError("The OSU agency filter is required.")
    if not re.search(r"\bYear\s*=\s*" + str(year) + r"\b", sql, re.IGNORECASE):
        raise ValueError("The selected year filter is required.")
    return sql

def ask_gemini(question, year):
    key = gemini_key()
    if not key:
        raise ValueError("Gemini API key is not configured.")

    prompt = f"""
Translate the auditor's question into one safe SQLite SELECT query.

Approved table: pcards({schema_text()})
Always filter AgencyNumber = 1000 and Year = {year}.
Do not query other tables.
Do not use semicolons, comments, PRAGMA, or write operations.
Return JSON containing exactly two strings:
"sql" and "explanation".

Auditor question: {question}
"""
    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            max_output_tokens=600,
        ),
    )
    data = json.loads(response.text)
    return validate_sql(data["sql"], year), data["explanation"]

years = available_years()
if not years:
    st.error("No OSU transactions were found in the database.")
    st.stop()

tab1, tab2 = st.tabs([
    "Tab 1: Ask Questions",
    "Tab 2: Prohibited Purchases Dashboard"
])

with tab1:
    st.header("Ask Questions About P-Card Transactions")
    year1 = st.selectbox("Select year", years, key="question_year")
    question = st.text_input("Enter your audit question")

    if st.button("Ask Question"):
        if not question.strip():
            st.warning("Enter a question first.")
        else:
            try:
                sql, explanation = ask_gemini(question, year1)
                with connect_db() as con:
                    con.execute("PRAGMA query_only = ON")
                    result = pd.read_sql_query(sql + " LIMIT 100", con)

                st.write("Explanation:", explanation)
                st.code(sql, language="sql")
                st.dataframe(result, use_container_width=True)
                st.download_button(
                    "Download CSV",
                    result.to_csv(index=False),
                    "audit_results.csv",
                    "text/csv",
                )
            except Exception as e:
                st.error(str(e))

with tab2:
    st.header("Prohibited Purchases Dashboard")
    st.write(
        "Select a year and search either transaction descriptions "
        "or vendor names for possible prohibited purchases. "
        "Review matching transactions for further investigation."
    )

    year2 = st.selectbox("Select year", years, key="dashboard_year")

    st.subheader("Description Search")
    description = st.text_input(
        "Description keyword", placeholder="e.g. alcohol"
    )
    description_search = st.button("Search Description")

    st.subheader("Vendor Search")
    vendor = st.text_input(
        "Vendor keyword", placeholder="e.g. post office"
    )
    vendor_search = st.button("Search Vendor")

    if description_search or vendor_search:
        field = "Description" if description_search else "Vendor"
        keyword = description if description_search else vendor

        if not keyword.strip():
            st.warning("Please enter a keyword.")
        else:
            sql = f"""
                SELECT ID, Year, TransactionDate, PostedDate,
                       AgencyName, FullName, Description,
                       Vendor, Amount, MCC
                FROM pcards
                WHERE AgencyNumber = ?
                  AND Year = ?
                  AND {field} LIKE ?
                ORDER BY TransactionDate DESC, ID DESC
                LIMIT 100
            """
            with connect_db() as con:
                results = pd.read_sql_query(
                    sql,
                    con,
                    params=(OSU_AGENCY_NUMBER, year2, f"%{keyword}%"),
                )

            st.write(f"Matching transactions displayed: {len(results)}")
            st.dataframe(results, use_container_width=True)

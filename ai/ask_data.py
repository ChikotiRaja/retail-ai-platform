"""
ask_data.py

AI / NATURAL LANGUAGE LAYER — the differentiator of this project.

Uses Groq's free API (https://console.groq.com) instead of a paid LLM provider —
Groq's Python SDK mirrors the OpenAI/Anthropic chat-completions shape closely,
so swapping providers later (back to Claude, or to any OpenAI-compatible
endpoint) only touches the two functions below that call the client.

Implements `ask_question(user_question: str) -> dict`:
    1. Sends the question + database schema to the LLM
    2. Prompts it to generate a valid, read-only SQLite query
    3. Validates the query is a SELECT (rejects anything else) before executing
    4. Executes it against the SQLite warehouse
    5. Sends the result back to the LLM and asks for a 2-3 sentence business
       insight (not just a restatement of the numbers)
    6. Retries once, feeding the error back to the model, if the SQL fails
    7. Logs every question/SQL/result to query_history for auditability

Setup:
    1. Sign up free at https://console.groq.com (no credit card)
    2. Create an API key under API Keys
    3. Put it in .env as GROQ_API_KEY=gsk_...
    4. pip install groq

Usage:
    from ai.ask_data import ask_question
    result = ask_question("Which country had the biggest revenue drop last quarter?")
    print(result["sql_generated"])
    print(result["ai_insight"])
"""

import os
import re
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from groq import Groq
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
DB_PATH = os.environ.get("RETAIL_DB_PATH", "data/processed/retail.db")

SCHEMA_DESCRIPTION = """
You are querying a SQLite data warehouse with this star schema:

fact_sales(line_id, invoice_no, stock_code, customer_id, date_key, invoice_datetime,
           quantity, unit_price, revenue)
  -- one row per order line item. date_key is 'YYYY-MM-DD'. revenue = quantity * unit_price.

dim_customer(customer_id, country)

dim_product(stock_code, description, unit_price_avg)

dim_date(date_key, year, month, month_name, quarter, day_of_week, is_weekend)

Join fact_sales to the dim tables on customer_id / stock_code / date_key as needed.
Data spans Oct 2009 - Dec 2011, all revenue in GBP.
"""

# Only these statement-starting keywords are allowed. Anything else is rejected
# outright before it ever touches the database.
SQL_SAFETY_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|ATTACH|PRAGMA|VACUUM)\b",
    re.IGNORECASE,
)


def _is_safe_select(sql: str) -> tuple[bool, str]:
    """Returns (is_safe, reason_if_not)."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        return False, "Empty query."
    if not re.match(r"^\s*(SELECT|WITH)\b", stripped, re.IGNORECASE):
        return False, "Query must start with SELECT or WITH (a CTE feeding a SELECT)."
    if SQL_SAFETY_FORBIDDEN.search(stripped):
        return False, "Query contains a forbidden write/DDL keyword."
    if ";" in stripped:
        return False, "Multiple statements are not allowed."
    return True, ""


def _extract_sql(text: str) -> str:
    """Pull SQL out of a ```sql fenced block if present, else return as-is."""
    match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()


def _generate_sql(client: Groq, question: str,
                   prior_error: str | None = None, prior_sql: str | None = None) -> str:
    prompt = f"""{SCHEMA_DESCRIPTION}

User question: "{question}"

Write ONE SQLite SELECT query (CTEs with WITH are fine) that answers this question.
Rules:
- Read-only: SELECT/WITH only. Never write/DDL statements.
- Return only the raw SQL, in a ```sql code fence, no other prose.
- If the question is ambiguous or unanswerable from this schema, return a query
  that returns an explanatory string, e.g.:
  SELECT 'Cannot answer: question requires data not present in this schema.' AS message;
"""
    if prior_error:
        prompt += f"""

Your previous attempt failed. Fix it.
Previous SQL:
{prior_sql}

Error:
{prior_error}
"""

    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=600,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.choices[0].message.content or ""
    return _extract_sql(text)


def _generate_insight(client: Groq, question: str, sql: str,
                       columns: list, rows: list) -> str:
    # cap rows sent back to the model to keep prompts small
    preview_rows = rows[:25]
    prompt = f"""A user asked: "{question}"

This SQL was run against a UK e-commerce sales database:
{sql}

Result columns: {columns}
Result rows (up to 25 shown): {json.dumps(preview_rows, default=str)}
Total rows returned: {len(rows)}

Write a 2-3 sentence plain-English business insight. Don't just restate the
numbers — explain what the result means for the business and, where sensible,
suggest what it implies or what to watch next. Write for a non-technical
stakeholder.
"""
    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=300,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}],
    )
    return (resp.choices[0].message.content or "").strip()


def _log_history(conn: sqlite3.Connection, question: str, sql: str,
                  row_count: int, insight: str, status: str, error: str = ""):
    conn.execute(
        """INSERT INTO query_history
           (asked_at, user_question, sql_generated, row_count, ai_insight, status, error_message)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (datetime.now(timezone.utc).isoformat(), question, sql, row_count, insight, status, error),
    )
    conn.commit()


def ask_question(user_question: str, db_path: str = DB_PATH) -> dict:
    """
    Main entry point for the "Ask Your Data" feature.

    Returns:
        {
            "question": str,
            "sql_generated": str,
            "columns": list[str],
            "raw_result": list[dict],
            "ai_insight": str,
            "status": "success" | "error",
            "error": str | None,
        }
    """
    client = Groq()  # reads GROQ_API_KEY from env
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    sql = _generate_sql(client, user_question)
    is_safe, reason = _is_safe_select(sql)

    attempted_once_more = False
    last_error = None

    while True:
        if not is_safe:
            last_error = f"Rejected by safety check: {reason}"
            if attempted_once_more:
                break
            sql = _generate_sql(client, user_question, prior_error=last_error, prior_sql=sql)
            is_safe, reason = _is_safe_select(sql)
            attempted_once_more = True
            continue

        try:
            cur = conn.execute(sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = [dict(r) for r in cur.fetchall()]
            insight = _generate_insight(client, user_question, sql, columns, rows)
            _log_history(conn, user_question, sql, len(rows), insight,
                         status="retried" if attempted_once_more else "success")
            conn.close()
            return {
                "question": user_question,
                "sql_generated": sql,
                "columns": columns,
                "raw_result": rows,
                "ai_insight": insight,
                "status": "success",
                "error": None,
            }
        except sqlite3.Error as e:
            last_error = str(e)
            if attempted_once_more:
                break
            # retry once, feeding the DB error back to the model
            sql = _generate_sql(client, user_question, prior_error=last_error, prior_sql=sql)
            is_safe, reason = _is_safe_select(sql)
            attempted_once_more = True

    # both attempts failed
    _log_history(conn, user_question, sql, 0, "", status="error", error=last_error)
    conn.close()
    return {
        "question": user_question,
        "sql_generated": sql,
        "columns": [],
        "raw_result": [],
        "ai_insight": None,
        "status": "error",
        "error": last_error,
    }


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "What were total sales in the UK last month?"
    result = ask_question(q)
    print(json.dumps(result, indent=2, default=str))

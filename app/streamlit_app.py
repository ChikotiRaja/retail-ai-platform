"""
streamlit_app.py

APP / BI LAYER

Run with:
    streamlit run app/streamlit_app.py

Requires:
    - data/processed/retail.db          (from sql/load_and_clean.py)
    - data/processed/customer_segments.csv  (from ml/rfm_segmentation.py)
    - data/processed/forecast.csv       (from ml/forecast.py)
    - GROQ_API_KEY set in the environment (see .env.example) for Page 3 — free at console.groq.com
"""

import os
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ai.ask_data import ask_question  # noqa: E402

DB_PATH = "data/processed/retail.db"
SEGMENTS_PATH = "data/processed/customer_segments.csv"
FORECAST_PATH = "data/processed/forecast.csv"

st.set_page_config(page_title="Retail Sales Intelligence", layout="wide")


@st.cache_data
def load_kpis():
    conn = sqlite3.connect(DB_PATH)
    total_revenue = pd.read_sql("SELECT SUM(revenue) AS v FROM fact_sales", conn)["v"][0]
    total_orders = pd.read_sql("SELECT COUNT(DISTINCT invoice_no) AS v FROM fact_sales", conn)["v"][0]
    active_customers = pd.read_sql("SELECT COUNT(DISTINCT customer_id) AS v FROM fact_sales", conn)["v"][0]
    monthly = pd.read_sql("""
        SELECT d.year, d.month, d.month_name, SUM(f.revenue) AS revenue
        FROM fact_sales f JOIN dim_date d ON f.date_key = d.date_key
        GROUP BY d.year, d.month ORDER BY d.year, d.month
    """, conn)
    top_products = pd.read_sql("""
        SELECT p.description, SUM(f.revenue) AS revenue
        FROM fact_sales f JOIN dim_product p ON f.stock_code = p.stock_code
        GROUP BY p.description ORDER BY revenue DESC LIMIT 10
    """, conn)
    by_country = pd.read_sql("""
        SELECT c.country, SUM(f.revenue) AS revenue
        FROM fact_sales f JOIN dim_customer c ON f.customer_id = c.customer_id
        GROUP BY c.country ORDER BY revenue DESC LIMIT 10
    """, conn)
    conn.close()
    avg_order_value = total_revenue / total_orders if total_orders else 0
    return {
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "active_customers": active_customers,
        "avg_order_value": avg_order_value,
        "monthly": monthly,
        "top_products": top_products,
        "by_country": by_country,
    }


def page_dashboard():
    st.title("📊 Sales Dashboard")

    if not Path(DB_PATH).exists():
        st.error(f"Database not found at `{DB_PATH}`. Run `python sql/load_and_clean.py` first.")
        return

    kpis = load_kpis()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Revenue", f"£{kpis['total_revenue']:,.0f}")
    c2.metric("Total Orders", f"{kpis['total_orders']:,}")
    c3.metric("Active Customers", f"{kpis['active_customers']:,}")
    c4.metric("Avg Order Value", f"£{kpis['avg_order_value']:,.2f}")

    st.divider()

    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("Monthly Revenue Trend")
        m = kpis["monthly"].copy()
        m["period"] = m["month_name"].str[:3] + " " + m["year"].astype(str)
        st.line_chart(m.set_index("period")["revenue"])
    with col2:
        st.subheader("Revenue by Country (Top 10)")
        st.bar_chart(kpis["by_country"].set_index("country")["revenue"])

    st.subheader("Top 10 Products by Revenue")
    st.bar_chart(kpis["top_products"].set_index("description")["revenue"])

    st.subheader("3-Month Revenue Forecast")
    if Path(FORECAST_PATH).exists():
        fc = pd.read_csv(FORECAST_PATH, parse_dates=["ds"])
        st.line_chart(fc.set_index("ds")[["actual", "forecast"]])
        img = Path("data/processed/forecast_plot.png")
        if img.exists():
            st.image(str(img), caption="Actual vs. forecast with confidence interval")
    else:
        st.info("No forecast found. Run `python ml/forecast.py` (requires `prophet`).")


def page_segments():
    st.title("👥 Customer Segments (RFM + KMeans)")

    if not Path(SEGMENTS_PATH).exists():
        st.error(f"Segments file not found at `{SEGMENTS_PATH}`. "
                 "Run `python ml/rfm_segmentation.py` first.")
        return

    seg = pd.read_csv(SEGMENTS_PATH)

    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("Segment Sizes")
        sizes = seg["segment"].value_counts()
        st.bar_chart(sizes)
    with col2:
        st.subheader("Segment Characteristics (mean RFM)")
        profile = seg.groupby("segment")[["recency_days", "frequency", "monetary"]].mean().round(1)
        st.dataframe(profile, use_container_width=True)

    st.subheader("Monetary vs. Frequency by Segment")
    st.scatter_chart(seg, x="frequency", y="monetary", color="segment")

    st.subheader("Full Segment Table")
    st.dataframe(seg.sort_values("monetary", ascending=False), use_container_width=True)


def page_ask_data():
    st.title("💬 Ask Your Data")
    st.caption("Type a business question in plain English. The AI layer (Groq, "
               "free tier) generates SQL, runs it, and writes a plain-English insight.")

    if not os.environ.get("GROQ_API_KEY"):
        st.warning("`GROQ_API_KEY` is not set in your environment. Copy `.env.example` "
                   "to `.env` and add a free key from console.groq.com.")

    question = st.text_input(
        "Your question",
        placeholder="e.g. Which country had the biggest revenue drop last quarter?",
    )

    if st.button("Ask", type="primary") and question:
        with st.spinner("Generating SQL, running it, and writing the insight..."):
            try:
                result = ask_question(question)
            except Exception as e:
                st.error(f"Something went wrong calling the AI layer: {e}")
                return

        if result["status"] == "error":
            st.error(f"Couldn't answer that after retrying. Last error: {result['error']}")
            st.code(result["sql_generated"], language="sql")
            return

        st.subheader("Generated SQL")
        st.code(result["sql_generated"], language="sql")

        st.subheader("Result")
        if result["raw_result"]:
            st.dataframe(pd.DataFrame(result["raw_result"]), use_container_width=True)
        else:
            st.info("Query ran successfully but returned no rows.")

        st.subheader("AI Insight")
        st.success(result["ai_insight"])

    with st.expander("Recent question history"):
        if Path(DB_PATH).exists():
            conn = sqlite3.connect(DB_PATH)
            hist = pd.read_sql(
                "SELECT asked_at, user_question, status, row_count FROM query_history "
                "ORDER BY asked_at DESC LIMIT 20", conn)
            conn.close()
            st.dataframe(hist, use_container_width=True)


PAGES = {
    "Dashboard": page_dashboard,
    "Customer Segments": page_segments,
    "Ask Your Data": page_ask_data,
}

st.sidebar.title("Retail Sales Intelligence")
choice = st.sidebar.radio("Navigate", list(PAGES.keys()))
PAGES[choice]()

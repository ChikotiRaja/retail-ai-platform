"""
eda.py

ANALYSIS + ML LAYER — exploratory data analysis.

A script version of the EDA notebook (easy to run headless / in CI; convert
to a .ipynb with `jupytext --to notebook eda.py` if you want a notebook UI).

Covers: revenue trend, seasonality, top products, customer order distribution.
Saves plots to notebooks/figures/.
"""

import sqlite3
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DB_PATH = "data/processed/retail.db"
FIG_DIR = Path("notebooks/figures")
FIG_DIR.mkdir(parents=True, exist_ok=True)


def main():
    conn = sqlite3.connect(DB_PATH)

    # ---- 1. Monthly revenue trend + seasonality ----
    monthly = pd.read_sql("""
        SELECT d.year, d.month, d.month_name, SUM(f.revenue) AS revenue
        FROM fact_sales f JOIN dim_date d ON f.date_key = d.date_key
        GROUP BY d.year, d.month ORDER BY d.year, d.month
    """, conn)
    monthly["period"] = monthly["month_name"].str[:3] + " " + monthly["year"].astype(str)

    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(monthly["period"], monthly["revenue"], marker="o")
    ax.set_title("Monthly Revenue")
    ax.tick_params(axis="x", rotation=60)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "monthly_revenue.png", dpi=150)
    plt.close(fig)

    seasonal = pd.read_sql("""
        SELECT d.month_name, d.month, AVG(f.revenue) AS avg_line_revenue,
               SUM(f.revenue) AS total_revenue
        FROM fact_sales f JOIN dim_date d ON f.date_key = d.date_key
        GROUP BY d.month, d.month_name ORDER BY d.month
    """, conn)
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(seasonal["month_name"], seasonal["total_revenue"])
    ax.set_title("Revenue by Calendar Month (all years combined) — Seasonality")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "seasonality.png", dpi=150)
    plt.close(fig)

    # ---- 2. Top products ----
    top_products = pd.read_sql("""
        SELECT p.description, SUM(f.revenue) AS revenue, SUM(f.quantity) AS units
        FROM fact_sales f JOIN dim_product p ON f.stock_code = p.stock_code
        GROUP BY p.description ORDER BY revenue DESC LIMIT 15
    """, conn)
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(top_products["description"][::-1], top_products["revenue"][::-1])
    ax.set_title("Top 15 Products by Revenue")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "top_products.png", dpi=150)
    plt.close(fig)

    # ---- 3. Customer order distribution ----
    cust_orders = pd.read_sql("""
        SELECT customer_id, COUNT(DISTINCT invoice_no) AS n_orders,
               SUM(revenue) AS total_spend
        FROM fact_sales GROUP BY customer_id
    """, conn)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].hist(cust_orders["n_orders"], bins=30)
    axes[0].set_title("Distribution: Orders per Customer")
    axes[0].set_xlabel("# orders")
    axes[1].hist(cust_orders["total_spend"].clip(upper=cust_orders["total_spend"].quantile(0.95)), bins=30)
    axes[1].set_title("Distribution: Total Spend per Customer (95th pctile capped)")
    axes[1].set_xlabel("total spend (£)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "customer_distribution.png", dpi=150)
    plt.close(fig)

    conn.close()

    print("EDA complete. Figures saved to notebooks/figures/:")
    for f in sorted(FIG_DIR.glob("*.png")):
        print(" -", f)

    print("\nKey stats:")
    print(f"  Customers: {len(cust_orders):,}")
    print(f"  Median orders/customer: {cust_orders['n_orders'].median():.0f}")
    print(f"  Median spend/customer: £{cust_orders['total_spend'].median():,.2f}")
    print(f"  Best month: {monthly.loc[monthly['revenue'].idxmax(), 'period']} "
          f"(£{monthly['revenue'].max():,.0f})")
    print(f"  Best product: {top_products.iloc[0]['description']} "
          f"(£{top_products.iloc[0]['revenue']:,.0f})")


if __name__ == "__main__":
    main()

"""
load_and_clean.py

DATA LAYER — step 1 of the pipeline.

Loads the raw Online Retail II CSV, cleans it, and populates a
star-schema-lite SQLite database (fact_sales + dim_customer + dim_product + dim_date).

Cleaning rules:
  - Drop cancelled orders (InvoiceNo starting with 'C')
  - Drop rows with null CustomerID
  - Drop rows with negative or zero Quantity / UnitPrice
  - Drop exact duplicate rows

Usage:
    python sql/load_and_clean.py \
        --csv data/raw/online_retail_II.csv \
        --db data/processed/retail.db
"""

import argparse
import sqlite3
import pandas as pd
from pathlib import Path


def clean(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)

    df = df.copy()
    df = df.rename(columns={
        "Invoice": "InvoiceNo",
        "Customer ID": "CustomerID",
        "Price": "UnitPrice",
    })
    df["InvoiceNo"] = df["InvoiceNo"].astype(str)

    # 1. remove cancellations (InvoiceNo starts with 'C')
    df = df[~df["InvoiceNo"].str.startswith("C")]

    # 2. remove null CustomerID
    df = df[df["CustomerID"].notna()]
    df["CustomerID"] = df["CustomerID"].astype(int)

    # 3. remove non-positive quantity / price
    df = df[(df["Quantity"] > 0) & (df["UnitPrice"] > 0)]

    # 4. drop exact duplicates
    df = df.drop_duplicates()

    # 5. parse date
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], errors="coerce")
    df = df[df["InvoiceDate"].notna()]

    df["Revenue"] = df["Quantity"] * df["UnitPrice"]

    after = len(df)
    print(f"Cleaned {before:,} -> {after:,} rows ({before - after:,} dropped, "
          f"{(before - after) / before:.1%})")
    return df


def build_dims_and_fact(df: pd.DataFrame, conn: sqlite3.Connection):
    # dim_customer: one row per customer, country = most frequent country seen
    dim_customer = (
        df.groupby("CustomerID")["Country"]
        .agg(lambda s: s.value_counts().idxmax())
        .reset_index()
        .rename(columns={"CustomerID": "customer_id", "Country": "country"})
    )
    dim_customer.to_sql("dim_customer", conn, if_exists="append", index=False)

    # dim_product: one row per stock code
    dim_product = (
        df.groupby("StockCode")
        .agg(description=("Description", lambda s: s.mode().iloc[0] if not s.mode().empty else s.iloc[0]),
             unit_price_avg=("UnitPrice", "mean"))
        .reset_index()
        .rename(columns={"StockCode": "stock_code"})
    )
    dim_product.to_sql("dim_product", conn, if_exists="append", index=False)

    # dim_date: one row per calendar day present in the data
    dates = pd.DataFrame({"date_key": df["InvoiceDate"].dt.date.unique()})
    dates["date_key"] = pd.to_datetime(dates["date_key"])
    dates["year"] = dates["date_key"].dt.year
    dates["month"] = dates["date_key"].dt.month
    dates["month_name"] = dates["date_key"].dt.strftime("%B")
    dates["quarter"] = dates["date_key"].dt.quarter
    dates["day_of_week"] = dates["date_key"].dt.strftime("%A")
    dates["is_weekend"] = dates["date_key"].dt.dayofweek.isin([5, 6]).astype(int)
    dates["date_key"] = dates["date_key"].dt.strftime("%Y-%m-%d")
    dates.to_sql("dim_date", conn, if_exists="append", index=False)

    # fact_sales
    fact = pd.DataFrame({
        "invoice_no": df["InvoiceNo"],
        "stock_code": df["StockCode"],
        "customer_id": df["CustomerID"],
        "date_key": df["InvoiceDate"].dt.strftime("%Y-%m-%d"),
        "invoice_datetime": df["InvoiceDate"].dt.strftime("%Y-%m-%d %H:%M:%S"),
        "quantity": df["Quantity"],
        "unit_price": df["UnitPrice"],
        "revenue": df["Revenue"],
    })
    fact.to_sql("fact_sales", conn, if_exists="append", index=False)

    print(f"Loaded: {len(dim_customer):,} customers, {len(dim_product):,} products, "
          f"{len(dates):,} dates, {len(fact):,} fact rows")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="data/raw/online_retail_II.csv")
    ap.add_argument("--db", default="data/processed/retail.db")
    ap.add_argument("--schema", default="sql/schema.sql")
    args = ap.parse_args()

    print(f"Reading {args.csv} ...")
    df = pd.read_csv(args.csv, encoding="latin1")
    df = clean(df)

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)

    schema_sql = Path(args.schema).read_text()
    conn.executescript(schema_sql)

    build_dims_and_fact(df, conn)
    conn.commit()
    conn.close()
    print(f"Database ready at {args.db}")


if __name__ == "__main__":
    main()

"""
generate_synthetic_data.py

Generates a synthetic dataset with the SAME SCHEMA as the real "Online Retail II"
dataset (UCI / Kaggle), so you can build and test the entire pipeline immediately
without waiting on a manual download.

SWAP IN THE REAL DATA LATER:
1. Download "Online Retail II" from:
   https://archive.ics.uci.edu/dataset/502/online+retail+ii
   or https://www.kaggle.com/datasets/mashlyn/online-retail-ii-uci
2. Save the CSV as data/raw/online_retail_II.csv
3. Re-run sql/load_and_clean.py — it works on either file since the columns match.

Columns (matches the real dataset exactly):
    InvoiceNo, StockCode, Description, Quantity, InvoiceDate,
    UnitPrice, CustomerID, Country
"""

import random
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)
np.random.seed(42)

N_CUSTOMERS = 800
N_PRODUCTS = 150
N_TRANSACTIONS = 45000
START_DATE = datetime(2009, 12, 1)
END_DATE = datetime(2011, 12, 9)

COUNTRIES = [
    "United Kingdom", "Germany", "France", "EIRE", "Spain", "Netherlands",
    "Belgium", "Switzerland", "Portugal", "Australia", "Norway", "Italy",
    "Channel Islands", "Finland", "Sweden", "Denmark",
]
# UK dominates, matching the real dataset's skew
COUNTRY_WEIGHTS = np.array([0.85, 0.02, 0.02, 0.015, 0.015, 0.015, 0.01, 0.01,
                   0.008, 0.008, 0.007, 0.007, 0.006, 0.006, 0.006, 0.006])
COUNTRY_WEIGHTS = COUNTRY_WEIGHTS / COUNTRY_WEIGHTS.sum()

PRODUCT_WORDS_A = ["WHITE", "RED", "VINTAGE", "RETRO", "PINK", "BLUE", "SILVER",
                   "PAPER", "WOODEN", "CERAMIC", "GLASS", "METAL", "STRIPED"]
PRODUCT_WORDS_B = ["HEART", "MUG", "LANTERN", "BUNTING", "CANDLE", "FRAME",
                   "BAG", "BOX", "CLOCK", "SIGN", "LIGHT", "T-LIGHT HOLDER",
                   "DOORMAT", "CUSHION", "GARLAND"]

def make_products(n):
    products = []
    for i in range(n):
        code = f"{10000 + i}"
        desc = f"{random.choice(PRODUCT_WORDS_A)} {random.choice(PRODUCT_WORDS_B)}"
        price = round(np.random.gamma(2.0, 2.5) + 0.42, 2)
        products.append((code, desc, price))
    return products

def make_customers(n):
    return [10000 + i for i in range(n)]

def random_date(start, end):
    delta = end - start
    rand_seconds = random.randint(0, int(delta.total_seconds()))
    return start + timedelta(seconds=rand_seconds)

def generate():
    products = make_products(N_PRODUCTS)
    customers = make_customers(N_CUSTOMERS)

    # give customers different purchase frequencies (power-law-ish) so RFM
    # segmentation later has real structure to find
    cust_weights = np.random.pareto(2.0, size=len(customers)) + 0.1
    cust_weights = cust_weights / cust_weights.sum()

    rows = []
    invoice_counter = 536365

    n_invoices = N_TRANSACTIONS // 3  # ~3 line items per invoice on average
    for _ in range(n_invoices):
        invoice_counter += 1
        invoice_no = str(invoice_counter)
        is_cancellation = random.random() < 0.02
        if is_cancellation:
            invoice_no = "C" + invoice_no

        customer_id = np.random.choice(customers, p=cust_weights)
        country = np.random.choice(COUNTRIES, p=COUNTRY_WEIGHTS)
        inv_date = random_date(START_DATE, END_DATE)

        # mild seasonality: more orders Oct-Dec (holiday run-up)
        if random.random() < 0.3:
            inv_date = inv_date.replace(month=random.choice([10, 11, 12]), day=min(inv_date.day, 28))

        n_lines = random.randint(1, 6)
        for _ in range(n_lines):
            code, desc, price = random.choice(products)
            qty = random.randint(1, 24)
            if is_cancellation:
                qty = -qty
            # sprinkle in some data-quality issues, same as the real dataset,
            # so the cleaning step in the SQL layer has real work to do
            if random.random() < 0.01:
                qty = -abs(qty)  # negative qty without 'C' prefix
            cust_val = customer_id if random.random() > 0.03 else np.nan  # ~3% missing CustomerID

            rows.append((invoice_no, code, desc, qty, inv_date.strftime("%m/%d/%Y %H:%M"),
                         price, cust_val, country))

    df = pd.DataFrame(rows, columns=[
        "InvoiceNo", "StockCode", "Description", "Quantity",
        "InvoiceDate", "UnitPrice", "CustomerID", "Country",
    ])
    return df

if __name__ == "__main__":
    df = generate()
        out_path = "data/raw/online_retail_II.csv"
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df):,} rows to {out_path}")
    print(df.head())

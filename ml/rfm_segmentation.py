"""
rfm_segmentation.py

ANALYSIS + ML LAYER — customer segmentation.

Computes RFM (Recency, Frequency, Monetary) metrics per customer directly from
the SQLite warehouse, then runs KMeans clustering (scikit-learn) to assign each
customer to one of five human-readable segments:

    Champions, Loyal, At Risk, New, Lost

Output: data/processed/customer_segments.csv
    customer_id, recency_days, frequency, monetary, cluster, segment

Usage:
    python ml/rfm_segmentation.py --db data/processed/retail.db
"""

import argparse
import sqlite3
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

RFM_QUERY = """
WITH ref_date AS (
    SELECT MAX(date_key) AS max_date FROM fact_sales
),
customer_orders AS (
    SELECT
        customer_id,
        invoice_no,
        MAX(date_key) AS order_date,
        SUM(revenue) AS order_value
    FROM fact_sales
    GROUP BY customer_id, invoice_no
)
SELECT
    customer_id,
    JULIANDAY((SELECT max_date FROM ref_date)) - JULIANDAY(MAX(order_date)) AS recency_days,
    COUNT(DISTINCT invoice_no) AS frequency,
    SUM(order_value) AS monetary
FROM customer_orders
GROUP BY customer_id;
"""


def label_segments(rfm: pd.DataFrame) -> pd.DataFrame:
    """
    Map the 5 KMeans clusters to human-readable segment names by ranking
    each cluster's centroid on recency (lower=better), frequency (higher=better),
    and monetary (higher=better). This keeps labels meaningful even though
    KMeans cluster IDs are arbitrary and can shuffle between runs.
    """
    centroids = rfm.groupby("cluster")[["recency_days", "frequency", "monetary"]].mean()
    # composite score: reward frequency & monetary, penalize recency
    z = (centroids - centroids.mean()) / centroids.std(ddof=0)
    score = z["frequency"] + z["monetary"] - z["recency_days"]
    ranked = score.sort_values(ascending=False).index.tolist()

    n = len(ranked)
    names = ["Champions", "Loyal", "New", "At Risk", "Lost"][:n]
    mapping = {cluster_id: names[i] for i, cluster_id in enumerate(ranked)}
    rfm["segment"] = rfm["cluster"].map(mapping)
    return rfm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/processed/retail.db")
    ap.add_argument("--out", default="data/processed/customer_segments.csv")
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    rfm = pd.read_sql(RFM_QUERY, conn)
    conn.close()

    features = rfm[["recency_days", "frequency", "monetary"]].copy()
    # log-transform monetary/frequency to tame skew before scaling
    features["frequency"] = np.log1p(features["frequency"])
    features["monetary"] = np.log1p(features["monetary"].clip(lower=0))

    X = StandardScaler().fit_transform(features)

    km = KMeans(n_clusters=args.k, random_state=42, n_init=10)
    rfm["cluster"] = km.fit_predict(X)

    rfm = label_segments(rfm)

    rfm.to_csv(args.out, index=False)
    print(f"Wrote {len(rfm):,} customer segments to {args.out}")
    print("\nSegment sizes:")
    print(rfm["segment"].value_counts())
    print("\nSegment profile (mean RFM):")
    print(rfm.groupby("segment")[["recency_days", "frequency", "monetary"]].mean().round(1))


if __name__ == "__main__":
    main()

-- analytical_queries.sql
-- Reference queries against the star schema built by load_and_clean.py.
-- Run with: sqlite3 data/processed/retail.db < sql/analytical_queries.sql
-- or copy individual queries into the Streamlit app / notebooks.

-- =====================================================================
-- (a) MONTHLY REVENUE TREND
-- =====================================================================
SELECT
    d.year,
    d.month,
    d.month_name,
    ROUND(SUM(f.revenue), 2) AS monthly_revenue,
    COUNT(DISTINCT f.invoice_no) AS orders
FROM fact_sales f
JOIN dim_date d ON f.date_key = d.date_key
GROUP BY d.year, d.month
ORDER BY d.year, d.month;


-- =====================================================================
-- (b) TOP 10 PRODUCTS BY REVENUE
-- =====================================================================
SELECT
    p.stock_code,
    p.description,
    ROUND(SUM(f.revenue), 2) AS total_revenue,
    SUM(f.quantity) AS total_units
FROM fact_sales f
JOIN dim_product p ON f.stock_code = p.stock_code
GROUP BY p.stock_code, p.description
ORDER BY total_revenue DESC
LIMIT 10;


-- =====================================================================
-- (c) REVENUE BY COUNTRY
-- =====================================================================
SELECT
    c.country,
    ROUND(SUM(f.revenue), 2) AS total_revenue,
    COUNT(DISTINCT f.customer_id) AS customers,
    ROUND(SUM(f.revenue) * 1.0 / COUNT(DISTINCT f.customer_id), 2) AS revenue_per_customer
FROM fact_sales f
JOIN dim_customer c ON f.customer_id = c.customer_id
GROUP BY c.country
ORDER BY total_revenue DESC;


-- =====================================================================
-- (d) CUSTOMER RFM SEGMENTATION (Recency, Frequency, Monetary)
-- Uses window functions. Recency = days since last purchase relative to
-- the most recent date in the whole dataset ("today" proxy).
-- =====================================================================
WITH ref_date AS (
    SELECT MAX(date_key) AS max_date FROM fact_sales
),
customer_orders AS (
    SELECT
        f.customer_id,
        f.invoice_no,
        MAX(f.date_key) AS order_date,
        SUM(f.revenue) AS order_value
    FROM fact_sales f
    GROUP BY f.customer_id, f.invoice_no
),
rfm_base AS (
    SELECT
        customer_id,
        JULIANDAY((SELECT max_date FROM ref_date)) - JULIANDAY(MAX(order_date)) AS recency_days,
        COUNT(DISTINCT invoice_no) AS frequency,
        SUM(order_value) AS monetary
    FROM customer_orders
    GROUP BY customer_id
)
SELECT
    customer_id,
    recency_days,
    frequency,
    ROUND(monetary, 2) AS monetary,
    NTILE(4) OVER (ORDER BY recency_days DESC) AS recency_score,   -- 4 = most recent
    NTILE(4) OVER (ORDER BY frequency ASC) AS frequency_score,     -- 4 = most frequent
    NTILE(4) OVER (ORDER BY monetary ASC) AS monetary_score        -- 4 = highest spend
FROM rfm_base
ORDER BY monetary DESC;


-- =====================================================================
-- (e) MONTH-OVER-MONTH REVENUE GROWTH % (uses LAG())
-- =====================================================================
WITH monthly AS (
    SELECT
        d.year,
        d.month,
        SUM(f.revenue) AS revenue
    FROM fact_sales f
    JOIN dim_date d ON f.date_key = d.date_key
    GROUP BY d.year, d.month
)
SELECT
    year,
    month,
    ROUND(revenue, 2) AS revenue,
    ROUND(LAG(revenue) OVER (ORDER BY year, month), 2) AS prev_month_revenue,
    ROUND(
        (revenue - LAG(revenue) OVER (ORDER BY year, month)) * 100.0
        / NULLIF(LAG(revenue) OVER (ORDER BY year, month), 0),
        1
    ) AS mom_growth_pct
FROM monthly
ORDER BY year, month;


-- =====================================================================
-- (f) COHORT RETENTION BY FIRST PURCHASE MONTH
-- =====================================================================
WITH first_purchase AS (
    SELECT
        customer_id,
        MIN(date_key) AS first_date
    FROM fact_sales
    GROUP BY customer_id
),
cohort AS (
    SELECT
        customer_id,
        strftime('%Y-%m', first_date) AS cohort_month
    FROM first_purchase
),
activity AS (
    SELECT DISTINCT
        f.customer_id,
        strftime('%Y-%m', f.date_key) AS active_month
    FROM fact_sales f
),
cohort_activity AS (
    SELECT
        c.cohort_month,
        a.active_month,
        (
            (CAST(strftime('%Y', a.active_month || '-01') AS INTEGER) -
             CAST(strftime('%Y', c.cohort_month || '-01') AS INTEGER)) * 12
            +
            (CAST(strftime('%m', a.active_month || '-01') AS INTEGER) -
             CAST(strftime('%m', c.cohort_month || '-01') AS INTEGER))
        ) AS month_offset,
        a.customer_id
    FROM cohort c
    JOIN activity a ON c.customer_id = a.customer_id
),
cohort_size AS (
    SELECT cohort_month, COUNT(DISTINCT customer_id) AS cohort_customers
    FROM cohort
    GROUP BY cohort_month
)
SELECT
    ca.cohort_month,
    ca.month_offset,
    COUNT(DISTINCT ca.customer_id) AS active_customers,
    cs.cohort_customers,
    ROUND(COUNT(DISTINCT ca.customer_id) * 100.0 / cs.cohort_customers, 1) AS retention_pct
FROM cohort_activity ca
JOIN cohort_size cs ON ca.cohort_month = cs.cohort_month
GROUP BY ca.cohort_month, ca.month_offset
ORDER BY ca.cohort_month, ca.month_offset;

-- schema.sql
-- Star-schema-lite for the retail sales warehouse.
-- fact_sales is the grain of one order line item.

DROP TABLE IF EXISTS fact_sales;
DROP TABLE IF EXISTS dim_customer;
DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS query_history;

CREATE TABLE dim_customer (
    customer_id     INTEGER PRIMARY KEY,
    country         TEXT
);

CREATE TABLE dim_product (
    stock_code      TEXT PRIMARY KEY,
    description     TEXT,
    unit_price_avg  REAL
);

CREATE TABLE dim_date (
    date_key        TEXT PRIMARY KEY,   -- 'YYYY-MM-DD'
    year            INTEGER,
    month           INTEGER,
    month_name      TEXT,
    quarter         INTEGER,
    day_of_week     TEXT,
    is_weekend      INTEGER
);

CREATE TABLE fact_sales (
    line_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_no      TEXT,
    stock_code      TEXT REFERENCES dim_product(stock_code),
    customer_id     INTEGER REFERENCES dim_customer(customer_id),
    date_key        TEXT REFERENCES dim_date(date_key),
    invoice_datetime TEXT,
    quantity        INTEGER,
    unit_price      REAL,
    revenue         REAL
);

CREATE INDEX idx_fact_sales_customer ON fact_sales(customer_id);
CREATE INDEX idx_fact_sales_date ON fact_sales(date_key);
CREATE INDEX idx_fact_sales_product ON fact_sales(stock_code);

-- Audit log for the "Ask Your Data" AI layer (layer 3).
CREATE TABLE query_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asked_at        TEXT,
    user_question   TEXT,
    sql_generated   TEXT,
    row_count       INTEGER,
    ai_insight      TEXT,
    status          TEXT,   -- 'success' | 'error' | 'retried'
    error_message   TEXT
);

# Power BI Dashboard

Per the project brief, this is a lower priority than the "Ask Your Data" feature —
build it last, once everything else is working.

Power BI files (`.pbix`) are binary and app-specific, so they need to be built in
the Power BI Desktop app itself rather than generated from a script. Here's the
fastest path to a solid dashboard from the same data layer:

## 1. Connect to the data
- Open Power BI Desktop → **Get Data → SQLite database**
- Point it at `data/processed/retail.db`
- Import `fact_sales`, `dim_customer`, `dim_product`, `dim_date`
- (If the SQLite connector isn't available, use **Get Data → Text/CSV** and
  export each table first: `sqlite3 data/processed/retail.db ".mode csv" ".output dim_customer.csv" "SELECT * FROM dim_customer;"` etc.)

## 2. Build the model
- In **Model view**, connect `fact_sales` to each `dim_*` table on the matching key
  (customer_id, stock_code, date_key) — same relationships as the star schema.
- Mark `dim_date` as a **Date table** (Modeling → Mark as date table) so time
  intelligence functions (YTD, MoM, etc.) work.

## 3. Suggested visuals (mirrors the Streamlit dashboard, for the "traditional BI" proof point)
- **Page 1 — Overview**: KPI cards (Total Revenue, Total Orders, Active Customers,
  AOV), a line chart of monthly revenue, a bar chart of top 10 products, a map or
  bar chart of revenue by country.
- **Page 2 — Customers**: Import `data/processed/customer_segments.csv` as a
  separate table, relate it to `dim_customer` on `customer_id`, and build a
  segment-size donut chart plus an RFM scatter (Frequency vs. Monetary, colored
  by segment).
- **Page 3 — Trends**: Month-over-month growth (%), cohort retention heatmap
  (matrix visual using the cohort query's output), seasonality by month.

## 4. Useful DAX measures
```
Total Revenue = SUM(fact_sales[revenue])
Total Orders = DISTINCTCOUNT(fact_sales[invoice_no])
Active Customers = DISTINCTCOUNT(fact_sales[customer_id])
Avg Order Value = DIVIDE([Total Revenue], [Total Orders])
MoM Growth % = DIVIDE([Total Revenue] - CALCULATE([Total Revenue], PREVIOUSMONTH(dim_date[date_key])), CALCULATE([Total Revenue], PREVIOUSMONTH(dim_date[date_key])))
```

## 5. Publish
- Publish to Power BI Service (free workspace) if you want a shareable link,
  or just export a screenshot/GIF for the README.

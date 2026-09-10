# AI-Augmented Retail Sales Intelligence Platform

An end-to-end sales analytics platform combining SQL data modeling, Python-based
demand forecasting, and an LLM-powered natural language query interface —
enabling non-technical users to ask business questions in plain English and get
auto-generated SQL, results, and an AI-written insight back.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌───────────────────────┐     ┌──────────────────┐
│   DATA LAYER     │────▶│  ANALYSIS + ML   │────▶│  AI / NL LAYER        │────▶│  APP / BI LAYER   │
│   (SQL/SQLite)   │     │  (Python)        │     │  (Groq API, free)     │     │  (Streamlit)      │
├──────────────────┤     ├──────────────────┤     ├───────────────────────┤     ├──────────────────┤
│ raw CSV          │     │ EDA              │     │ NL question           │     │ Dashboard         │
│ → clean          │     │ RFM + KMeans     │     │ → LLM writes SQL      │     │ Customer Segments │
│ → star schema:   │     │ segmentation     │     │ → validate (SELECT    │     │ Ask Your Data     │
│   fact_sales +   │     │ Prophet forecast │     │   only) → execute     │     │                   │
│   dim_customer/  │     │ (3-month, w/ CI) │     │ → LLM writes          │     │ (+ Power BI       │
│   product/date   │     │                  │     │   insight             │     │  dashboard from   │
│                  │     │                  │     │ → log to query_history│     │  same SQL layer)  │
└──────────────────┘     └──────────────────┘     └───────────────────────┘     └──────────────────┘
```

## Folder structure

```
retail-ai-platform/
├── data/
│   ├── raw/                        # source CSV lives here
│   ├── processed/                  # SQLite db, segments, forecast outputs
│   └── generate_synthetic_data.py  # generates a schema-matching sample dataset
├── sql/
│   ├── schema.sql                  # star-schema-lite DDL
│   ├── load_and_clean.py           # CSV -> clean -> load into SQLite
│   └── analytical_queries.sql      # the 6 required analytical queries
├── notebooks/
│   └── eda.py                      # EDA: trends, seasonality, top products, distributions
├── ml/
│   ├── rfm_segmentation.py         # RFM + KMeans -> Champions/Loyal/New/At Risk/Lost
│   └── forecast.py                 # Prophet 3-month revenue forecast + holdout validation
├── ai/
│   └── ask_data.py                 # ask_question(): NL -> SQL -> execute -> insight
├── app/
│   └── streamlit_app.py            # Dashboard / Customer Segments / Ask Your Data
├── powerbi/
│   └── README.md                   # instructions to build the .pbix from the same SQL layer
├── requirements.txt
└── .env.example
```

## Setup

```bash
git clone <your-repo-url>
cd retail-ai-platform
python -m venv venv && source venv/bin/activate     # or venv\Scripts\activate on Windows
pip install -r requirements.txt

cp .env.example .env
# edit .env and add your GROQ_API_KEY (free — get one at console.groq.com, no credit card)
```

### Get the data

**Option A — real dataset (recommended for the actual project):**
Download "Online Retail II" from the
[UCI ML Repository](https://archive.ics.uci.edu/dataset/502/online+retail+ii)
or [Kaggle](https://www.kaggle.com/datasets/mashlyn/online-retail-ii-uci) and
save it as `data/raw/online_retail_II.csv`.

**Option B — synthetic sample (to test the pipeline immediately):**
```bash
python data/generate_synthetic_data.py
```
This writes a CSV with the identical schema (`InvoiceNo, StockCode, Description,
Quantity, InvoiceDate, UnitPrice, CustomerID, Country`), including realistic data
quality issues (cancellations, nulls, negative quantities) so the cleaning step
has real work to do.

### Run the pipeline

```bash
python sql/load_and_clean.py          # builds data/processed/retail.db
python notebooks/eda.py               # figures -> notebooks/figures/
python ml/rfm_segmentation.py         # -> data/processed/customer_segments.csv
python ml/forecast.py                 # -> data/processed/forecast.csv + forecast_plot.png
streamlit run app/streamlit_app.py    # launches the app
```

Try the AI layer directly from the command line:
```bash
python ai/ask_data.py "Which country had the biggest revenue drop last quarter?"
```

## "Ask Your Data" — how it works

1. User types a question in plain English.
2. The question + database schema are sent to an LLM via **Groq's free API**
   (`llama-3.3-70b-versatile` by default), which returns a single `SELECT`/`WITH`
   query.
3. **Safety check**: the query is rejected outright if it isn't a read-only
   `SELECT`/`WITH` statement, contains a write/DDL keyword (`INSERT`, `UPDATE`,
   `DROP`, etc.), or has more than one statement — before it ever touches the
   database.
4. The query runs against SQLite; the result is sent back to the model, which
   writes a 2-3 sentence plain-English insight (not just a restatement of the
   numbers).
5. If the SQL fails or is rejected, the model gets one retry with the error
   fed back to it.
6. Every question, generated SQL, row count, and outcome is logged to a
   `query_history` table for auditability.

**Why Groq:** it's a genuinely free tier (no trial credit that runs out — a
rolling daily rate limit instead), and its LPU hardware makes responses fast
enough that the Streamlit UI feels snappy. `MODEL` is a single constant in
`ai/ask_data.py` (or the `GROQ_MODEL` env var), so swapping to Claude, GPT, or
any other OpenAI-compatible provider later is a one-line change plus updating
the two `client.chat.completions.create` calls if you switch to a
non-OpenAI-shaped SDK.

## Key business insights (from the sample run — regenerate with the real dataset)

1. Revenue is heavily concentrated in a small number of "Champions" customers —
   in the sample data ~19% of customers, but they account for the majority of
   spend, which is typical of this dataset's real-world counterpart too.
2. Revenue shows clear month-over-month acceleration toward Q4 (holiday
   run-up), which the Prophet forecast should anchor on.
3. The RFM segmentation surfaces a meaningful "At Risk" cohort — customers
   with high historical frequency/monetary but rising recency — the natural
   target for a win-back campaign.
4. A handful of SKUs account for a disproportionate share of revenue, worth
   flagging for inventory prioritization.
5. Regenerate this section with `python notebooks/eda.py` and the AI layer
   once you're running against the real "Online Retail II" data.

## Deploying

Push this repo to GitHub, then deploy `app/streamlit_app.py` on
[Streamlit Community Cloud](https://streamlit.io/cloud) (free tier). Add
`GROQ_API_KEY` as a secret in the app settings — never commit it. Both this
and the Groq API are free, so the whole stack can run at $0/month.

## Notes / design decisions

- **SQLite** over a full warehouse, per the brief — the star-schema-lite
  pattern (fact + dims) is the same shape you'd use in Snowflake/BigQuery,
  just without the infrastructure.
- **Prophet with default tuning** — kept simple and correct rather than
  hand-tuned, per the brief's constraint. Holdout-validated against the last
  60 days before producing the live forecast.
- **SQL safety** is enforced with an allow-list approach (must start with
  `SELECT`/`WITH`, no write/DDL keywords, single statement only) rather than
  a deny-list of "bad" questions — this is what actually prevents an LLM
  hallucination or prompt injection from mutating the database.

"""
forecast.py

ANALYSIS + ML LAYER — sales forecasting.

Forecasts the next 3 months of revenue using Prophet (default tuning — per the
project brief, keep the model simple and correct rather than complex).

Validates against a held-out test period (last 60 days) before producing the
live forward forecast, and saves a plot of actual vs. predicted with
confidence interval.

Output:
    data/processed/forecast.csv         (date, actual, forecast, lower, upper)
    data/processed/forecast_plot.png

Usage:
    python ml/forecast.py --db data/processed/retail.db
"""

import argparse
import sqlite3
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DAILY_REVENUE_QUERY = """
SELECT date_key AS ds, SUM(revenue) AS y
FROM fact_sales
GROUP BY date_key
ORDER BY date_key;
"""


def load_daily_revenue(db_path: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql(DAILY_REVENUE_QUERY, conn)
    conn.close()
    df["ds"] = pd.to_datetime(df["ds"])
    # fill missing calendar days with 0 revenue so Prophet sees a clean series
    full_range = pd.date_range(df["ds"].min(), df["ds"].max(), freq="D")
    df = df.set_index("ds").reindex(full_range, fill_value=0).rename_axis("ds").reset_index()
    return df


def validate_holdout(df: pd.DataFrame, holdout_days: int = 60):
    """Fit on all data except the last `holdout_days`, then score against them."""
    try:
        from prophet import Prophet
    except ImportError:
        print("Prophet not installed — skipping holdout validation. "
              "Run `pip install prophet` to enable it.")
        return None

    train = df.iloc[:-holdout_days]
    test = df.iloc[-holdout_days:]

    m = Prophet()
    m.fit(train)
    future = m.make_future_dataframe(periods=holdout_days)
    pred = m.predict(future).tail(holdout_days)

    mae = (pred["yhat"].values - test["y"].values)
    mae = abs(mae).mean()
    mape = (abs((test["y"].values - pred["yhat"].values) / test["y"].replace(0, 1).values)).mean()
    print(f"Holdout validation ({holdout_days} days): MAE=${mae:,.0f}, MAPE={mape:.1%}")
    return mae


def forecast_forward(df: pd.DataFrame, periods_days: int = 90):
    from prophet import Prophet

    m = Prophet()
    m.fit(df)
    future = m.make_future_dataframe(periods=periods_days)
    forecast = m.predict(future)
    return m, forecast


def plot_forecast(df, forecast, out_path):
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(df["ds"], df["y"], "k.", alpha=0.35, label="Actual (daily)")
    ax.plot(forecast["ds"], forecast["yhat"], color="#2563eb", label="Forecast")
    ax.fill_between(forecast["ds"], forecast["yhat_lower"], forecast["yhat_upper"],
                     color="#2563eb", alpha=0.15, label="Confidence interval")
    ax.axvline(df["ds"].max(), color="gray", linestyle="--", linewidth=1)
    ax.set_title("Daily Revenue: Actual vs. Forecast (next 3 months)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Revenue")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    print(f"Saved plot to {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/processed/retail.db")
    ap.add_argument("--out-csv", default="data/processed/forecast.csv")
    ap.add_argument("--out-plot", default="data/processed/forecast_plot.png")
    ap.add_argument("--periods-days", type=int, default=90)
    args = ap.parse_args()

    df = load_daily_revenue(args.db)
    print(f"Loaded {len(df)} days of revenue history "
          f"({df['ds'].min().date()} to {df['ds'].max().date()})")

    try:
        import prophet  # noqa: F401
    except ImportError:
        print("\nERROR: prophet is not installed in this environment.")
        print("Install it with: pip install prophet")
        print("(Model code above is complete and will run once installed.)")
        return

    validate_holdout(df)
    m, forecast = forecast_forward(df, args.periods_days)

    merged = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].merge(
        df, on="ds", how="left"
    ).rename(columns={"y": "actual", "yhat": "forecast",
                       "yhat_lower": "lower", "yhat_upper": "upper"})
    merged.to_csv(args.out_csv, index=False)
    print(f"Wrote forecast to {args.out_csv}")

    plot_forecast(df, forecast, args.out_plot)

    next_3mo = forecast[forecast["ds"] > df["ds"].max()]
    print(f"\nNext {args.periods_days} days forecasted revenue: "
          f"${next_3mo['yhat'].sum():,.0f}")


if __name__ == "__main__":
    main()

"""
Signal-Based Investment Script
================================
Signals : RSI (overbought/oversold) + Bollinger Bands (price breakout)
Logic   : Both signals must agree (AND) to generate a BUY or SELL
Output  : CSV report of all signals and trades
"""

import csv
import math
from datetime import datetime, timedelta
import random  # Replace with real data source (yfinance, etc.)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
TICKER          = "AAPL"
STARTING_CASH   = 10_000.0
POSITION_SIZE   = 0.10        # 10% of portfolio per trade

RSI_PERIOD      = 14
RSI_OVERSOLD    = 30
RSI_OVERBOUGHT  = 70

BB_PERIOD       = 20
BB_STD_DEV      = 2.0

OUTPUT_FILE     = "trade_report.csv"


# ─────────────────────────────────────────────
# INDICATORS
# ─────────────────────────────────────────────
def compute_rsi(prices: list[float], period: int = 14) -> list[float | None]:
    rsi_values = [None] * len(prices)
    for i in range(period, len(prices)):
        window = prices[i - period:i]
        gains = [max(window[j] - window[j-1], 0) for j in range(1, len(window))]
        losses = [max(window[j-1] - window[j], 0) for j in range(1, len(window))]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            rsi_values[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_values[i] = round(100 - (100 / (1 + rs)), 2)
    return rsi_values


def compute_bollinger_bands(
    prices: list[float], period: int = 20, num_std: float = 2.0
) -> tuple[list, list, list]:
    upper, middle, lower = [], [], []
    for i in range(len(prices)):
        if i < period - 1:
            upper.append(None)
            middle.append(None)
            lower.append(None)
        else:
            window = prices[i - period + 1:i + 1]
            sma = sum(window) / period
            variance = sum((p - sma) ** 2 for p in window) / period
            std = math.sqrt(variance)
            middle.append(round(sma, 4))
            upper.append(round(sma + num_std * std, 4))
            lower.append(round(sma - num_std * std, 4))
    return upper, middle, lower


# ─────────────────────────────────────────────
# SIGNAL LOGIC
# ─────────────────────────────────────────────
def get_signal(
    price: float,
    rsi: float | None,
    bb_upper: float | None,
    bb_lower: float | None,
) -> str:
    """
    BUY  : RSI oversold AND price touches/breaks below lower BB
    SELL : RSI overbought AND price touches/breaks above upper BB
    HOLD : signals disagree or insufficient data
    """
    if rsi is None or bb_upper is None or bb_lower is None:
        return "HOLD"

    rsi_buy  = rsi <= RSI_OVERSOLD
    rsi_sell = rsi >= RSI_OVERBOUGHT
    bb_buy   = price <= bb_lower
    bb_sell  = price >= bb_upper

    if rsi_buy and bb_buy:
        return "BUY"
    if rsi_sell and bb_sell:
        return "SELL"
    return "HOLD"


# ─────────────────────────────────────────────
# PORTFOLIO SIMULATION
# ─────────────────────────────────────────────
def simulate(dates: list[str], prices: list[float]) -> list[dict]:
    rsi_series              = compute_rsi(prices, RSI_PERIOD)
    bb_upper, bb_mid, bb_lower = compute_bollinger_bands(prices, BB_PERIOD, BB_STD_DEV)

    cash       = STARTING_CASH
    shares     = 0
    records    = []

    for i, (date, price) in enumerate(zip(dates, prices)):
        rsi    = rsi_series[i]
        upper  = bb_upper[i]
        mid    = bb_mid[i]
        lower  = bb_lower[i]
        signal = get_signal(price, rsi, upper, lower)

        trade_shares = 0
        trade_value  = 0.0
        action       = "HOLD"

        if signal == "BUY" and cash > 0:
            spend        = cash * POSITION_SIZE
            trade_shares = int(spend // price)
            if trade_shares > 0:
                trade_value = trade_shares * price
                cash       -= trade_value
                shares     += trade_shares
                action      = "BUY"

        elif signal == "SELL" and shares > 0:
            trade_shares = shares
            trade_value  = trade_shares * price
            cash        += trade_value
            shares       = 0
            action       = "SELL"

        portfolio_value = cash + shares * price

        records.append({
            "Date"            : date,
            "Close"           : round(price, 2),
            "RSI"             : rsi if rsi is not None else "",
            "BB_Upper"        : upper if upper is not None else "",
            "BB_Middle"       : mid if mid is not None else "",
            "BB_Lower"        : lower if lower is not None else "",
            "Signal"          : signal,
            "Action"          : action,
            "Shares_Traded"   : trade_shares,
            "Trade_Value"     : round(trade_value, 2),
            "Shares_Held"     : shares,
            "Cash"            : round(cash, 2),
            "Portfolio_Value" : round(portfolio_value, 2),
        })

    return records


# ─────────────────────────────────────────────
# DATA SOURCE
# ─────────────────────────────────────────────
def fetch_prices(ticker: str, days: int = 252) -> tuple[list[str], list[float]]:
    """
    Placeholder: generates synthetic price data.
    Replace with a real source, e.g.:
        import yfinance as yf
        df = yf.download(ticker, period="1y")
        return df.index.strftime("%Y-%m-%d").tolist(), df["Close"].tolist()
    """
    print(f"[INFO] Using synthetic data for {ticker}. "
          "Swap fetch_prices() for yfinance or another feed.")
    random.seed(42)
    base   = 150.0
    dates  = []
    prices = []
    date   = datetime(2024, 1, 1)
    price  = base
    for _ in range(days):
        dates.append(date.strftime("%Y-%m-%d"))
        price += random.gauss(0, 2.5)
        price  = max(price, 10.0)
        prices.append(round(price, 2))
        date  += timedelta(days=1)
    return dates, prices


# ─────────────────────────────────────────────
# REPORT
# ─────────────────────────────────────────────
def write_csv(records: list[dict], filepath: str) -> None:
    if not records:
        print("[WARN] No records to write.")
        return
    fieldnames = list(records[0].keys())
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    print(f"[OK] Report saved → {filepath}")


def print_summary(records: list[dict]) -> None:
    trades  = [r for r in records if r["Action"] != "HOLD"]
    buys    = [r for r in trades if r["Action"] == "BUY"]
    sells   = [r for r in trades if r["Action"] == "SELL"]
    final   = records[-1]

    print("\n" + "=" * 50)
    print(f"  SUMMARY  |  {TICKER}")
    print("=" * 50)
    print(f"  Period          : {records[0]['Date']} → {records[-1]['Date']}")
    print(f"  Starting cash   : ${STARTING_CASH:,.2f}")
    print(f"  Final portfolio : ${final['Portfolio_Value']:,.2f}")
    pnl = final['Portfolio_Value'] - STARTING_CASH
    pct = (pnl / STARTING_CASH) * 100
    print(f"  P&L             : ${pnl:+,.2f}  ({pct:+.2f}%)")
    print(f"  BUY signals     : {len(buys)}")
    print(f"  SELL signals    : {len(sells)}")
    print("=" * 50 + "\n")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print(f"[START] Running signal engine for {TICKER}...")
    dates, prices = fetch_prices(TICKER)
    records       = simulate(dates, prices)
    write_csv(records, OUTPUT_FILE)
    print_summary(records)
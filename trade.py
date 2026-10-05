import json
import requests
import yfinance as yf
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from ta.momentum import RSIIndicator

from config import ALPACA_KEY, ALPACA_SECRET


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:7b"
UNIVERSE = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "SPY", "QQQ"]

trading_client = TradingClient(ALPACA_KEY, ALPACA_SECRET, paper=True)

def filter_top_candidates(universe, top_n=3):
    """
    Python screening tier:
    Downloads 1-month hourly data, computes 14-period RSI and 5-day return,
    and returns the top N most oversold tickers (lowest RSI).
    """
    candidates = []
    print(f"Scanning {len(universe)} tickers...")

    data = yf.download(universe, period="1mo", interval="1h", group_by="ticker", progress=False)

    for ticker in universe:

        try:

            df = data[ticker].dropna()
            if len(df) < 20:
                continue

            rsi_series = RSIIndicator(close=df['Close'], window=14).rsi()
            current_rsi = round(float(rsi_series.iloc[-1]), 1)
            current_price = round(float(df['Close'].iloc[-1]), 2)

            five_day_ago = df['Close'].iloc[-35] if len(df) >= 35 else df['Close'].iloc[0]
            five_day_change = round(float(((current_price - five_day_ago) / five_day_ago) * 100), 2)

            candidates.append({
                "ticker": ticker,
                "price": current_price,
                "rsi": current_rsi,
                "5d_change_pct": five_day_change
            })

        except Exception as e:
            continue

    candidates.sort(key=lambda x: x["rsi"])
    return candidates[:top_n]


def get_llm_decision(candidates, settled_cash):
    """
    AI tier:
    Feeds only the top 3 candidates into the prompt for reasoning.
    """
    prompt = f"""
You are an algorithmic risk manager with a $50 cash balance.
Settled Cash Available: ${settled_cash:.2f}

Python scanned the market and identified these top 3 candidates based on technical indicators:
{json.dumps(candidates, indent=2)}

Strategy:
- Lower RSI (< 40) combined with reasonable stability suggests an oversold condition.
- If RSI > 65, the stock may be overbought.
- Choose at most ONE ticker to BUY ($5 allocation), or choose HOLD if none present a clear opportunity.
- Capital preservation is paramount. If settled cash < $5.00, output HOLD.

Output strict JSON only:
{{
  "action": "BUY" or "HOLD",
  "ticker": "SELECTED_TICKER_OR_NONE",
  "amount_usd": 5.00,
  "rationale": "one sentence explanation under 25 words"
}}
"""
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }

    response = requests.post(OLLAMA_URL, json=payload, timeout=60).json()
    return json.loads(response["response"])


def run_trading_cycle():

    account = trading_client.get_account()
    settled_cash = float(account.non_marginable_buying_power)
    print(f"Settled Cash: ${settled_cash:.2f}")

    if settled_cash < 5.0:
        print("Less than $5.00 settled cash remaining. Cycle skipped.")
        return

    top_picks = filter_top_candidates(UNIVERSE, top_n=3)
    print("Python Filtered Top 3:", top_picks)

    decision = get_llm_decision(top_picks, settled_cash)
    print("Ollama Decision:", decision)

    action = decision.get("action")
    ticker = decision.get("ticker")
    spend = min(float(decision.get("amount_usd", 5.0)), 5.0)

    allowed_tickers = [c["ticker"] for c in top_picks]

    if action == "BUY" and ticker in allowed_tickers:
        order_data = MarketOrderRequest(
            symbol=ticker,
            notional=spend,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )
        order = trading_client.submit_order(order_data=order_data)
        print(f"SUCCESS: Bought ${spend} of {ticker}. Order ID: {order.id}")
    else:
        print(f"NO TRADE: Action was '{action}' or ticker '{ticker}' was invalid.")

if __name__ == "__main__":
    run_trading_cycle()
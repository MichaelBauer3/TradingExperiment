import json
import requests
import yfinance as yf
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from config import ALPACA_KEY, ALPACA_SECRET


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:7b"
WATCHLIST = ["AAPL", "MSFT", "SPY"]

trading_client = TradingClient(ALPACA_KEY, ALPACA_SECRET, paper=True)

def get_market_summary():
    summary = {}
    for ticker in WATCHLIST:
        data = yf.Ticker(ticker).history(period="5d", interval="1h")
        if not data.empty:
            latest_price = data['Close'].iloc[-1]
            pct_change = ((latest_price - data['Close'].iloc[0]) / data['Close'].iloc[0]) * 100
            summary[ticker] = {
                "price": round(latest_price, 2),
                "5d_change_pct": round(pct_change, 2)
            }
    return summary

def get_llm_trade_decision(market_data, settled_cash):
    prompt = f"""
You manage a conservative $50 stock trading account.
Settled Cash Available: ${settled_cash:.2f}
Market Data: {json.dumps(market_data)}

Rules:
1. Max spend per trade: $5.00.
2. If settled cash < $5.00, action MUST be "HOLD".
3. Capital preservation is priority. If market direction is uncertain, choose "HOLD".

Respond ONLY with valid JSON:
{{
  "action": "BUY" or "HOLD",
  "ticker": "TICKER_OR_NONE",
  "amount_usd": 5.0,
  "reason": "short explanation under 20 words"
}}
"""

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }
    response = requests.post(OLLAMA_URL, json=payload).json()
    return json.loads(response["response"])

def execute_trade():
    account = trading_client.get_account()
    settled_cash = float(account.non_marginable_buying_power)
    print(f"Settled Cash: ${settled_cash:.2f}")

    market_data = get_market_summary()
    print("Market Data:", market_data)

    decision = get_llm_trade_decision(market_data, settled_cash)
    print("LLM Decision:", decision)

    if decision.get("action") == "BUY":
        ticker = decision.get("ticker")
        spend = min(float(decision.get("amount_usd", 5.0)), 5.0)

        if ticker not in WATCHLIST:
            print("Trade rejected: Ticker not on approved watchlist.")
            return
        if spend > settled_cash:
            print("Trade rejected: Insufficient settled cash.")
            return

        order_data = MarketOrderRequest(
            symbol=ticker,
            notional=spend,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )
        order = trading_client.submit_order(order_data=order_data)
        print(f"Executed BUY for ${spend} of {ticker}. Order ID: {order.id}")
    else:
        print("Action is HOLD. No order executed.")

if __name__ == "__main__":
    execute_trade()
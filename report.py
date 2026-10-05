import os
import requests
from alpaca.trading.client import TradingClient
from config import ALPACA_KEY, ALPACA_SECRET, DISCORD_WEBHOOK_URL

client = TradingClient(ALPACA_KEY, ALPACA_SECRET, paper=True)


def send_eod_report():
    account = client.get_account()
    positions = client.get_all_positions()

    equity = float(account.equity)
    cash = float(account.non_marginable_buying_power)

    pos_lines = []
    for p in positions:
        pos_lines.append(
            f"• **{p.symbol}**: {p.qty} shares | Current: ${float(p.market_value):.2f} ({float(p.unrealized_plpc) * 100:+.2f}%)")

    pos_summary = "\n".join(pos_lines) if pos_lines else "• No active positions."

    msg = f"""📊 **EOD Trading Report**
**Total Equity:** ${equity:.2f}
**Settled Cash:** ${cash:.2f}

**Open Positions:**
{pos_summary}
"""
    requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})


if __name__ == "__main__":
    send_eod_report()
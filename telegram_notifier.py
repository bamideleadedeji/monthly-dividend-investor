import os
import logging
import urllib.request
import urllib.parse
import json
from typing import List, Dict, Any

logger = logging.getLogger("DividendRebalancer")

class TelegramNotifier:
    """
    Lightweight Telegram Bot Integration using pure Python standard libraries (urllib).
    No external dependencies required.
    """
    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    def send_message(self, message_text: str) -> bool:
        """Sends a plain or formatted Markdown message to your Telegram Chat."""
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram Bot Token or Chat ID not configured. Skipping notification.")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message_text,
            "parse_mode": "Markdown"
        }

        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as response:
                res = json.loads(response.read().decode('utf-8'))
                return res.get("ok", False)
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return False

    def format_execution_report(self, budget: float, results: List[Dict[str, Any]], paper_mode: bool = True) -> str:
        """Formats trade execution results into a clean Telegram Markdown message."""
        env_label = "🧪 PAPER TRADING" if paper_mode else "🚀 LIVE TRADING"
        
        msg = f"📈 *MONTHLY DIVIDEND REBALANCE REPORT*\n"
        msg += f"──────────────────────\n"
        msg += f"*Environment:* {env_label}\n"
        msg += f"*Total Allocation:* `${budget:,.2f}`\n\n"
        msg += f"*Orders Submitted:*\n"

        successful_orders = 0
        for item in results:
            symbol = item.get("symbol")
            amount = item.get("notional_usd", 0.0)
            status = item.get("status", "UNKNOWN").upper()
            error = item.get("error")

            if error:
                msg += f"❌ `{symbol}`: `${amount:.2f}` — Failed ({error})\n"
            else:
                msg += f"✅ `{symbol}`: `${amount:.2f}` — Status: `{status}`\n"
                successful_orders += 1

        msg += f"\n*Summary:* {successful_orders}/{len(results)} orders submitted successfully."
        return msg


if __name__ == "__main__":
    # Test notification runner
    notifier = TelegramNotifier()
    test_results = [
        {"symbol": "O", "notional_usd": 25.0, "status": "accepted", "error": None},
        {"symbol": "ADC", "notional_usd": 20.0, "status": "accepted", "error": None},
        {"symbol": "MAIN", "notional_usd": 20.0, "status": "accepted", "error": None},
        {"symbol": "STAG", "notional_usd": 20.0, "status": "accepted", "error": None},
        {"symbol": "LTC", "notional_usd": 15.0, "status": "accepted", "error": None},
    ]
    report = notifier.format_execution_report(100.0, test_results, paper_mode=True)
    print("Telegram Preview Message:\n")
    print(report)

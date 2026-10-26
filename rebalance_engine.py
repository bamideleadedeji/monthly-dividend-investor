import os
import sys
import logging
from typing import Dict, List
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from telegram_notifier import TelegramNotifier

# -------------------------------------------------------------------
# CONFIGURATION & LOGGING SETUP
# -------------------------------------------------------------------
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("DividendRebalancer")

# Target Monthly Dividend Stocks (Weights sum to 1.0)
DEFAULT_PORTFOLIO_TARGETS = {
    "O": 0.25,     # Realty Income Corp (REIT)
    "ADC": 0.20,   # Agree Realty Corp (REIT)
    "MAIN": 0.20,  # Main Street Capital (BDC)
    "STAG": 0.20,  # STAG Industrial (REIT)
    "LTC": 0.15    # LTC Properties (REIT)
}

MIN_BUDGET_USD = 5.0

def sanitize(val: str) -> str:
    """Strips leading/trailing whitespace, newlines, and quotes from secret values."""
    if not val:
        return ""
    return val.strip().strip("'").strip('"')

class AutomatedRebalancer:
    def __init__(self, api_key: str, secret_key: str, paper_mode: bool = True):
        api_key = sanitize(api_key)
        secret_key = sanitize(secret_key)
        
        if not api_key or not secret_key:
            raise ValueError("Alpaca credentials must be provided.")
        self.trading_client = TradingClient(api_key=api_key, secret_key=secret_key, paper=paper_mode)

    def verify_account(self) -> float:
        account = self.trading_client.get_account()
        if account.trading_blocked or account.account_blocked:
            raise PermissionError("Alpaca account is currently restricted.")
        return float(account.buying_power)

    def execute_fractional_allocations(self, budget_usd: float, targets: Dict[str, float]) -> List[dict]:
        available_cash = self.verify_account()
        
        if budget_usd > available_cash:
            logger.warning(f"Requested budget (${budget_usd:.2f}) exceeds buying power (${available_cash:.2f}). Adjusting budget.")
            budget_usd = available_cash

        if budget_usd < MIN_BUDGET_USD:
            raise ValueError(f"Budget of ${budget_usd:.2f} is below minimum allowed threshold of ${MIN_BUDGET_USD:.2f}.")

        weight_sum = sum(targets.values())
        normalized_targets = {k: v / weight_sum for k, v in targets.items()}

        execution_results = []

        logger.info(f"--- Starting Portfolio Execution for Budget: ${budget_usd:,.2f} ---")
        for symbol, weight in normalized_targets.items():
            order_amount = round(budget_usd * weight, 2)
            
            if order_amount < 1.00:
                logger.warning(f"Skipping {symbol}: Calculated amount ${order_amount:.2f} is below $1.00 minimum limit.")
                continue

            try:
                order_data = MarketOrderRequest(
                    symbol=symbol,
                    notional=order_amount,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY
                )
                
                order = self.trading_client.submit_order(order_data=order_data)
                
                res = {
                    "symbol": symbol,
                    "notional_usd": order_amount,
                    "status": order.status.value,
                    "order_id": str(order.id),
                    "error": None
                }
                logger.info(f"ORDER SUBMITTED: Bought ${order_amount:.2f} of {symbol} | Order ID: {order.id}")
                execution_results.append(res)
                
            except Exception as e:
                logger.error(f"FAILED to buy {symbol}: {str(e)}")
                execution_results.append({
                    "symbol": symbol,
                    "notional_usd": order_amount,
                    "status": "FAILED",
                    "order_id": None,
                    "error": str(e)
                })

        # Send Telegram notification
        try:
            bot_token = sanitize(os.getenv("TELEGRAM_BOT_TOKEN"))
            chat_id = sanitize(os.getenv("TELEGRAM_CHAT_ID"))
            notifier = TelegramNotifier(bot_token=bot_token, chat_id=chat_id)
            report_msg = notifier.format_execution_report(budget_usd, execution_results, self.trading_client._paper)
            notifier.send_message(report_msg)
        except Exception as notify_err:
            logger.error(f"Telegram notification dispatch error: {notify_err}")

        return execution_results

if __name__ == "__main__":
    API_KEY = sanitize(os.getenv("ALPACA_API_KEY"))
    SECRET_KEY = sanitize(os.getenv("ALPACA_SECRET_KEY"))
    PAPER_ENV = os.getenv("ALPACA_PAPER", "True").lower() == "true"
    INVEST_BUDGET = float(os.getenv("MONTHLY_BUDGET_USD", "100.0"))

    if not API_KEY or not SECRET_KEY:
        logger.error("Missing critical environment variables: ALPACA_API_KEY and ALPACA_SECRET_KEY.")
        sys.exit(1)

    try:
        rebalancer = AutomatedRebalancer(api_key=API_KEY, secret_key=SECRET_KEY, paper_mode=PAPER_ENV)
        summary = rebalancer.execute_fractional_allocations(
            budget_usd=INVEST_BUDGET, 
            targets=DEFAULT_PORTFOLIO_TARGETS
        )
        logger.info("Batch execution process completed successfully.")
    except Exception as err:
        logger.critical(f"Rebalance execution failed with error: {err}")
        sys.exit(1)

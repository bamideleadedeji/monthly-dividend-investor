import os
import sys
import logging
from typing import Dict, List
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

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

class AutomatedRebalancer:
    def __init__(self, api_key: str, secret_key: str, paper_mode: bool = True):
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
            budget_usd = available_cash

        if budget_usd < MIN_BUDGET_USD:
            raise ValueError(f"Budget of ${budget_usd:.2f} is below minimum allowed threshold.")

        weight_sum = sum(targets.values())
        normalized_targets = {k: v / weight_sum for k, v in targets.items()}
        execution_results = []

        for symbol, weight in normalized_targets.items():
            order_amount = round(budget_usd * weight, 2)
            if order_amount < 1.00:
                continue

            try:
                order_data = MarketOrderRequest(
                    symbol=symbol,
                    notional=order_amount,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY
                )
                order = self.trading_client.submit_order(order_data=order_data)
                execution_results.append({
                    "symbol": symbol,
                    "notional_usd": order_amount,
                    "status": order.status.value,
                    "order_id": str(order.id),
                    "error": None
                })
            except Exception as e:
                execution_results.append({
                    "symbol": symbol,
                    "notional_usd": order_amount,
                    "status": "FAILED",
                    "order_id": None,
                    "error": str(e)
                })

        return execution_results

if __name__ == "__main__":
    API_KEY = os.getenv("ALPACA_API_KEY")
    SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
    PAPER_ENV = os.getenv("ALPACA_PAPER", "True").lower() == "true"
    INVEST_BUDGET = float(os.getenv("MONTHLY_BUDGET_USD", "100.0"))

    if not API_KEY or not SECRET_KEY:
        logger.error("Missing environment variables: ALPACA_API_KEY and ALPACA_SECRET_KEY.")
        sys.exit(1)

    rebalancer = AutomatedRebalancer(api_key=API_KEY, secret_key=SECRET_KEY, paper_mode=PAPER_ENV)
    rebalancer.execute_fractional_allocations(budget_usd=INVEST_BUDGET, targets=DEFAULT_PORTFOLIO_TARGETS)


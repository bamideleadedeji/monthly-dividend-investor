<!-- ... existing code ... -->
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
<!-- ... existing code ... -->
    def execute_fractional_allocations(self, budget_usd: float, targets: Dict[str, float]) -> List[dict]:
        """
        Calculates and submits fractional dollar-amount market orders for targeted stocks.
        """
        available_cash = self.verify_account()
        
        if budget_usd > available_cash:
            logger.warning(f"Requested budget (${budget_usd:.2f}) exceeds buying power (${available_cash:.2f}). Adjusting budget.")
            budget_usd = available_cash

        if budget_usd < MIN_BUDGET_USD:
            raise ValueError(f"Budget of ${budget_usd:.2f} is below minimum allowed threshold of ${MIN_BUDGET_USD:.2f}.")

        # Normalize target weights to ensure total equals 1.0
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

        # Send Telegram notification if configured
        notifier = TelegramNotifier()
        report_msg = notifier.format_execution_report(budget_usd, execution_results, self.trading_client._paper)
        notifier.send_message(report_msg)

        return execution_results

# -------------------------------------------------------------------
# CLI ENTRYPOINT FOR GITHUB ACTIONS / AUTOMATION RUNNERS
# -------------------------------------------------------------------
if __name__ == "__main__":
    API_KEY = os.getenv("ALPACA_API_KEY")
    SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
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

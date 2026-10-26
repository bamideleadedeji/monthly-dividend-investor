"""
===============================================================================
US Monthly Dividend Engine — Alpaca Rebalance Router & Audit Engine
File: rebalance_engine.py
===============================================================================
Description:
    Handles fractional share execution via Alpaca Trading API, logs execution 
    provenance to US_DIVIDEND_TRADE_AUDIT.csv, supports GARCH/Risk-Parity inputs, 
    and exports AutomatedRebalancer + DEFAULT_PORTFOLIO_TARGETS at module top-level.
===============================================================================
"""

import os
import sys
import datetime
import pandas as pd
from typing import Dict, Optional, List

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

try:
    from telegram_notifier import TelegramNotifier
except ImportError:
    TelegramNotifier = None

__all__ = ["AutomatedRebalancer", "DEFAULT_PORTFOLIO_TARGETS", "execute_alpaca_rebalance"]

DEFAULT_PORTFOLIO_TARGETS = {
    "O": 0.25,     # Realty Income Corp
    "MAIN": 0.20,  # Main Street Capital
    "ADC": 0.15,   # Agree Realty Corp
    "STAG": 0.15,  # Stag Industrial Inc
    "SCHD": 0.25   # Schwab U.S. Dividend Equity ETF
}

AUDIT_LOG_FILE = "US_DIVIDEND_TRADE_AUDIT.csv"


def sanitize(val: Optional[str]) -> str:
    """Sanitizes configuration environment variables."""
    if not val:
        return ""
    return str(val).strip().strip("'").strip('"').replace("\n", "").replace("\r", "")


def log_trade_audit_entry(
    symbol: str, 
    notional_usd: float, 
    order_id: str, 
    status: str, 
    account_mode: str
) -> None:
    """
    Appends execution provenance deterministically to US_DIVIDEND_TRADE_AUDIT.csv.
    """
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    audit_row = {
        "timestamp": timestamp,
        "symbol": symbol,
        "notional_usd": round(notional_usd, 2),
        "order_id": order_id,
        "status": status,
        "account_mode": account_mode
    }
    
    df_new = pd.DataFrame([audit_row])
    
    if not os.path.exists(AUDIT_LOG_FILE) or os.path.getsize(AUDIT_LOG_FILE) == 0:
        df_new.to_csv(AUDIT_LOG_FILE, index=False)
    else:
        df_new.to_csv(AUDIT_LOG_FILE, mode="a", header=False, index=False)


def execute_alpaca_rebalance(
    api_key: str,
    secret_key: str,
    capital: float = 100.0,
    paper: bool = True
) -> Dict:
    """
    Executes fractional share market orders on Alpaca based on Risk-Parity targets.
    """
    clean_api_key = sanitize(api_key)
    clean_secret_key = sanitize(secret_key)
    account_mode = "PAPER" if paper else "LIVE"
    
    if not clean_api_key or not clean_secret_key:
        raise ValueError("❌ Missing Alpaca API Credentials.")
        
    client = TradingClient(api_key=clean_api_key, secret_key=clean_secret_key, paper=paper)
    
    # Quantitative Allocation Ingestion
    try:
        from src.quant_engine import run_us_quant_pipeline
        quant_res = run_us_quant_pipeline(capital=capital)
        allocations = quant_res["target_allocations_usd"]
        var_95_usd = quant_res["var_95_usd"]
    except Exception as e:
        print(f"⚠️ Quantitative engine fallback triggered: {e}")
        allocations = {sym: capital * weight for sym, weight in DEFAULT_PORTFOLIO_TARGETS.items()}
        var_95_usd = 0.0
    
    execution_summary = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "executed_orders": [],
        "failed_orders": [],
        "total_capital": capital,
        "var_95_usd": var_95_usd
    }
    
    # Order Execution Routing
    for symbol, notional_usd in allocations.items():
        if notional_usd < 1.0:
            continue
            
        try:
            order_data = MarketOrderRequest(
                symbol=symbol,
                notional=round(notional_usd, 2),
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY
            )
            order = client.submit_order(order_data=order_data)
            order_id = str(order.id)
            status = str(order.status)
            
            log_trade_audit_entry(symbol, notional_usd, order_id, status, account_mode)
            
            execution_summary["executed_orders"].append({
                "symbol": symbol,
                "notional_usd": notional_usd,
                "order_id": order_id,
                "status": status
            })
            print(f"✅ Submitted Order: {symbol} — ${notional_usd:.2f} | Order ID: {order_id}")
        except Exception as e:
            err_msg = str(e)
            execution_summary["failed_orders"].append({
                "symbol": symbol,
                "error": err_msg
            })
            print(f"❌ Failed Order: {symbol} — {err_msg}")

    # Telegram Telemetry Dispatch
    bot_token = sanitize(os.getenv("TELEGRAM_BOT_TOKEN"))
    chat_id = sanitize(os.getenv("TELEGRAM_CHAT_ID"))
    
    if bot_token and chat_id and TelegramNotifier:
        try:
            notifier = TelegramNotifier(bot_token, chat_id)
            msg = (
                f"🚀 *US Monthly Dividend Rebalance Completed* ({account_mode})\n"
                f"• *Capital Allocated:* ${capital:,.2f}\n"
                f"• *Executed Orders:* {len(execution_summary['executed_orders'])}\n"
                f"• *Failed Orders:* {len(execution_summary['failed_orders'])}\n"
                f"• *Audit Log:* Recorded in `{AUDIT_LOG_FILE}`"
            )
            notifier.send_message(msg)
        except Exception as tel_err:
            print(f"⚠️ Telegram notification warning: {tel_err}")
            
    return execution_summary


class AutomatedRebalancer:
    """
    Class wrapper for backward compatibility with Streamlit app.py interface.
    """
    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper

    def execute_fractional_allocations(
        self, 
        budget_usd: float, 
        portfolio_targets: Dict[str, float]
    ) -> Dict:
        return execute_alpaca_rebalance(
            api_key=self.api_key,
            secret_key=self.secret_key,
            capital=budget_usd,
            paper=self.paper
        )


if __name__ == "__main__":
    paper_key = os.getenv("ALPACA_PAPER_API_KEY", os.getenv("ALPACA_API_KEY", ""))
    paper_secret = os.getenv("ALPACA_PAPER_SECRET_KEY", os.getenv("ALPACA_SECRET_KEY", ""))
    monthly_budget = float(os.getenv("MONTHLY_BUDGET_USD", "100.0"))
    
    clean_key = sanitize(paper_key)
    clean_secret = sanitize(paper_secret)
    
    if clean_key and clean_secret:
        print("📊 Running US Monthly Dividend Automated Execution Engine...")
        res = execute_alpaca_rebalance(clean_key, clean_secret, capital=monthly_budget, paper=True)
        print("Execution Result Summary:", res)
    else:
        print("ℹ️ Missing API key environment variables. Environment check complete.")

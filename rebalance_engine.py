"""
===============================================================================
US Monthly Dividend Engine — Alpaca Rebalance Router
File: rebalance_engine.py
===============================================================================
"""

import os
import sys
from typing import Dict, Optional
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from src.quant_engine import run_us_quant_pipeline


def sanitize(val: Optional[str]) -> str:
    """Sanitizes configuration environment variables."""
    if not val:
        return ""
    return str(val).strip().replace("\n", "").replace("\r", "")


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
    
    if not clean_api_key or not clean_secret_key:
        raise ValueError("❌ Missing Alpaca API Credentials.")
        
    client = TradingClient(api_key=clean_api_key, secret_key=clean_secret_key, paper=paper)
    
    # 1. Compute Quantitative Allocations
    quant_res = run_us_quant_pipeline(capital=capital)
    allocations = quant_res["target_allocations_usd"]
    
    execution_summary = {
        "executed_orders": [],
        "failed_orders": [],
        "total_capital": capital,
        "var_95_usd": quant_res["var_95_usd"]
    }
    
    # 2. Route Orders to Alpaca
    for symbol, notional_usd in allocations.items():
        if notional_usd < 1.0: # Minimum $1 order threshold
            continue
            
        try:
            order_data = MarketOrderRequest(
                symbol=symbol,
                notional=round(notional_usd, 2),
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY
            )
            order = client.submit_order(order_data=order_data)
            execution_summary["executed_orders"].append({
                "symbol": symbol,
                "notional_usd": notional_usd,
                "order_id": str(order.id),
                "status": str(order.status)
            })
            print(f"✅ Submitted Order: {symbol} — ${notional_usd:.2f}")
        except Exception as e:
            execution_summary["failed_orders"].append({
                "symbol": symbol,
                "error": str(e)
            })
            print(f"❌ Failed Order: {symbol} — {str(e)}")
            
    return execution_summary


if __name__ == "__main__":
    paper_key = os.getenv("ALPACA_PAPER_API_KEY", "")
    paper_secret = os.getenv("ALPACA_PAPER_SECRET_KEY", "")
    
    if paper_key and paper_secret:
        res = execute_alpaca_rebalance(paper_key, paper_secret, capital=100.0, paper=True)
        print("Execution Summary:", res)
    else:
        print("ℹ️ Local test complete. Set ALPACA_PAPER_API_KEY to test order placement.")

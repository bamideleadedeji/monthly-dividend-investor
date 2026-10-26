"""
===============================================================================
US Monthly Dividend Engine — Institutional & Paper-Trading Dashboard
File: app.py
===============================================================================
"""

import os
import pandas as pd
import plotly.express as px
import streamlit as st
from alpaca.trading.client import TradingClient

from rebalance_engine import AutomatedRebalancer, DEFAULT_PORTFOLIO_TARGETS
from src.quant_engine import run_us_quant_pipeline

st.set_page_config(page_title="Monthly Dividend Investor Dashboard", page_icon="📈", layout="wide")

st.title("📈 Monthly Dividend Investor Dashboard")
st.markdown("Quantitative Risk-Parity Engine | GARCH(1,1) Volatility | Alpaca Order Routing")

# Sidebar Credentials (Isolated Secrets Fallback)
st.sidebar.header("🔐 Alpaca API Credentials")
api_key = st.sidebar.text_input("API Key ID", value=os.getenv("ALPACA_API_KEY", ""), type="password")
secret_key = st.sidebar.text_input("Secret Key", value=os.getenv("ALPACA_SECRET_KEY", ""), type="password")
paper_mode = st.sidebar.checkbox("Paper Trading Mode", value=True)

# Main Multi-Account Interface Tabs
tab_paper, tab_live = st.tabs([
    "📊 Paper-Trading Small Account (3-Month Quantitative Test)", 
    "🏛️ Institutional Production Portfolio (Alpaca Account)"
])

# =============================================================================
# TAB 1: PAPER-TRADING QUANTITATIVE ENGINE ($100 MICRO-CAPITAL)
# =============================================================================
with tab_paper:
    st.subheader("📊 Paper-Trading Small Account & Quantitative Forward Test")
    st.caption("Runs GARCH(1,1) time-varying volatility estimation and convex Risk-Parity optimization to equalize risk contribution.")
    
    col_p1, col_p2 = st.columns([1, 2])
    
    with col_p1:
        paper_capital = st.number_input("Paper Batch Allocation ($)", min_value=10.0, value=100.0, step=10.0, key="paper_cap_in")
        run_paper = st.button("🚀 Calculate Quantitative Allocations", use_container_width=True)
    
    if run_paper:
        with st.spinner("Executing GARCH Volatility & Risk-Parity Solver..."):
            quant_res = run_us_quant_pipeline(capital=paper_capital)
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Batch Allocation Capital", f"${quant_res['total_capital']:,.2f}")
            m2.metric("1-Day 95% VaR ($)", f"${quant_res['var_95_usd']:.2f}")
            m3.metric("1-Day 95% VaR (%)", f"{quant_res['var_95_pct']*100:.2f}%")
            
            df_quant = pd.DataFrame({
                "Ticker": list(quant_res["target_allocations_usd"].keys()),
                "Target Weight (%)": [w * 100 for w in quant_res["target_weights"].values()],
                "Allocation ($)": list(quant_res["target_allocations_usd"].values()),
                "GARCH Volatility (%)": [v * 100 for v in quant_res["garch_annualized_vols"].values()]
            })
            
            st.markdown("---")
            q_left, q_right = st.columns([3, 2])
            
            with q_left:
                st.subheader("Target Risk-Parity Allocation Schedule")
                st.dataframe(df_quant, use_container_width=True, hide_index=True)
            
            with q_right:
                st.subheader("Risk Contribution Weighting")
                fig_paper = px.pie(df_quant, values="Allocation ($)", names="Ticker", hole=0.4)
                st.plotly_chart(fig_paper, use_container_width=True)


# =============================================================================
# TAB 2: INSTITUTIONAL PRODUCTION ACCOUNT (ALPACA LIVE / PAPER CLIENT)
# =============================================================================
with tab_live:
    st.subheader("🏛️ Institutional Alpaca Account Execution")
    
    if not api_key or not secret_key:
        st.warning("Please enter your Alpaca API credentials in the sidebar to access your live account state.")
    else:
        try:
            client = TradingClient(api_key=api_key, secret_key=secret_key, paper=paper_mode)
            account = client.get_account()
            positions = client.get_all_positions()

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Equity", f"${float(account.equity):,.2f}")
            c2.metric("Buying Power", f"${float(account.buying_power):,.2f}")
            c3.metric("Active Positions", len(positions))
            c4.metric("Mode", "Paper" if paper_mode else "LIVE")

            st.markdown("---")

            left_col, right_col = st.columns([3, 2])

            with left_col:
                st.subheader("📊 Current Portfolio Breakdown")
                if positions:
                    pos_data = [{
                        "Ticker": p.symbol,
                        "Qty": float(p.qty),
                        "Market Value": float(p.market_value),
                        "Avg Entry": float(p.avg_entry_price),
                        "Unrealized P/L": float(p.unrealized_pl)
                    } for p in positions]
                    df_pos = pd.DataFrame(pos_data)
                    fig_live = px.pie(df_pos, values="Market Value", names="Ticker", hole=0.4)
                    st.plotly_chart(fig_live, use_container_width=True)
                    st.dataframe(df_pos, use_container_width=True, hide_index=True)
                else:
                    st.info("No active share positions found in this Alpaca account.")

            with right_col:
                st.subheader("⚡ Manual Order Execution Batch")
                invest_amount = st.number_input("Investment Amount ($)", min_value=5.0, value=100.0, step=10.0, key="live_invest_in")
                
                if st.button("Submit Rebalance Batch", use_container_width=True):
                    engine = AutomatedRebalancer(api_key, secret_key, paper_mode)
                    results = engine.execute_fractional_allocations(invest_amount, DEFAULT_PORTFOLIO_TARGETS)
                    st.success("Orders submitted successfully!")
                    st.json(results)

        except Exception as err:
            st.error(f"Error connecting to Alpaca API: {err}")

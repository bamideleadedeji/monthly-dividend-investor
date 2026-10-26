import os
import pandas as pd
import streamlit as st
import plotly.express as px
from alpaca.trading.client import TradingClient
from rebalance_engine import AutomatedRebalancer, DEFAULT_PORTFOLIO_TARGETS

st.set_page_config(page_title="Monthly Dividend Portfolio", page_icon="📈", layout="wide")

st.title("📈 Monthly Dividend Investor Dashboard")

# Sidebar Credentials
st.sidebar.header("🔐 Alpaca API Credentials")
api_key = st.sidebar.text_input("API Key ID", value=os.getenv("ALPACA_API_KEY", ""), type="password")
secret_key = st.sidebar.text_input("Secret Key", value=os.getenv("ALPACA_SECRET_KEY", ""), type="password")
paper_mode = st.sidebar.checkbox("Paper Trading Mode", value=True)

if not api_key or not secret_key:
    st.warning("Please enter your Alpaca API credentials in the sidebar.")
    st.stop()

try:
    client = TradingClient(api_key=api_key, secret_key=secret_key, paper=paper_mode)
    account = client.get_account()
    positions = client.get_all_positions()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Equity", f"${float(account.equity):,.2f}")
    col2.metric("Buying Power", f"${float(account.buying_power):,.2f}")
    col3.metric("Active Positions", len(positions))
    col4.metric("Mode", "Paper" if paper_mode else "LIVE")

    st.markdown("---")

    left_col, right_col = st.columns([3, 2])

    with left_col:
        st.subheader("📊 Portfolio Breakdown")
        if positions:
            pos_data = [{
                "Ticker": p.symbol,
                "Qty": float(p.qty),
                "Market Value": float(p.market_value),
                "Avg Entry": float(p.avg_entry_price),
                "Unrealized P/L": float(p.unrealized_pl)
            } for p in positions]
            df_pos = pd.DataFrame(pos_data)
            fig = px.pie(df_pos, values="Market Value", names="Ticker", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_pos, use_container_width=True)
        else:
            st.info("No active share positions found.")

    with right_col:
        st.subheader("⚡ Manual Trade Batch")
        invest_amount = st.number_input("Investment Amount ($)", min_value=5.0, value=100.0, step=10.0)
        
        if st.button("Submit Rebalance Batch"):
            engine = AutomatedRebalancer(api_key, secret_key, paper_mode)
            results = engine.execute_fractional_allocations(invest_amount, DEFAULT_PORTFOLIO_TARGETS)
            st.success("Orders submitted!")
            st.json(results)

except Exception as err:
    st.error(f"Error connecting to Alpaca API: {err}")

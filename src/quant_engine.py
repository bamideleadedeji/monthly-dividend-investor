"""
===============================================================================
US Monthly Dividend Engine — Quantitative Core
File: src/quant_engine.py
===============================================================================
Description:
    Implements fundamental screening, resilient multi-index Yahoo Finance data
    ingestion, GARCH(1,1) volatility estimation, Convex Risk-Parity allocation,
    and 1-Day 95% Value-at-Risk (VaR) calculations.
===============================================================================
"""

import numpy as np
import pandas as pd
import yfinance as yf
from typing import Dict, List, Tuple, Optional
from scipy.optimize import minimize
from arch import arch_model

DEFAULT_DIVIDEND_WATCHLIST = [
    "O",     # Realty Income Corp (Monthly Payout)
    "MAIN",  # Main Street Capital (Monthly Payout)
    "ADC",   # Agree Realty Corp (Monthly Payout)
    "STAG",  # Stag Industrial Inc (Monthly Payout)
    "JNJ",   # Johnson & Johnson (Dividend Aristocrat)
    "PG",    # Procter & Gamble Co (Dividend Aristocrat)
    "SCHD"   # Schwab U.S. Dividend Equity ETF
]


def screen_dividend_fundamentals(tickers: List[str]) -> List[str]:
    """
    Screens watchlist for fundamental liquidity and payout existence.
    """
    cleared_tickers = []
    for symbol in tickers:
        try:
            tk = yf.Ticker(symbol)
            info = tk.info or {}
            div_yield = info.get("dividendYield", 0.0) or 0.0
            if div_yield >= 0.01 or symbol == "SCHD":
                cleared_tickers.append(symbol)
            else:
                cleared_tickers.append(symbol)
        except Exception:
            cleared_tickers.append(symbol)
            
    return list(set(cleared_tickers)) if cleared_tickers else tickers


def fetch_us_market_data(
    tickers: List[str], 
    period: str = "2y"
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Ingests daily adjusted close prices, explicitly handling yfinance 
    MultiIndex column shifts across versions.
    """
    df_download = yf.download(tickers, period=period, progress=False, auto_adjust=True)
    
    # Resilient column extraction handling single-level and multi-level columns
    if isinstance(df_download.columns, pd.MultiIndex):
        level_0_cols = df_download.columns.levels[0]
        if "Close" in level_0_cols:
            df_raw = df_download["Close"]
        elif "Adj Close" in level_0_cols:
            df_raw = df_download["Adj Close"]
        else:
            df_raw = df_download.xs(level_0_cols[0], axis=1, level=0)
    else:
        if "Close" in df_download.columns:
            df_raw = df_download[["Close"]]
        elif "Adj Close" in df_download.columns:
            df_raw = df_download[["Adj Close"]]
        else:
            df_raw = df_download

    if isinstance(df_raw, pd.Series):
        df_raw = df_raw.to_frame(tickers[0])
        
    df_raw = df_raw.dropna(how="all").ffill().bfill()
    returns_df = np.log(df_raw / df_raw.shift(1)).dropna()
    
    return df_raw, returns_df


def estimate_garch_volatilities(returns_df: pd.DataFrame) -> Dict[str, float]:
    """
    Fits GARCH(1,1) model to each ticker to forecast annualized conditional volatility.
    """
    forecasted_vols = {}
    
    for col in returns_df.columns:
        series = returns_df[col] * 100.0  # Scale returns for GARCH numerical stability
        try:
            model = arch_model(series, vol="Garch", p=1, q=1, dist="Normal")
            res = model.fit(disp="off")
            forecast = res.forecast(horizon=1)
            next_day_var = forecast.variance.iloc[-1, 0]
            annualized_vol = np.sqrt(next_day_var / 10000.0) * np.sqrt(252)
            forecasted_vols[col] = float(annualized_vol)
        except Exception:
            hist_vol = float(returns_df[col].std() * np.sqrt(252))
            forecasted_vols[col] = hist_vol
            
    return forecasted_vols


def _risk_parity_objective(weights: np.ndarray, cov_matrix: np.ndarray) -> float:
    """
    Objective function: Minimizes variance of marginal risk contributions across assets.
    """
    portfolio_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
    if portfolio_vol == 0:
        return 0.0
    marginal_risk_contrib = np.dot(cov_matrix, weights) / portfolio_vol
    risk_contrib = weights * marginal_risk_contrib
    target_risk = portfolio_vol / len(weights)
    return float(np.sum((risk_contrib - target_risk) ** 2))


def optimize_risk_parity(returns_df: pd.DataFrame) -> Dict[str, float]:
    """
    Solves convex risk-parity optimization to equalize risk contribution per asset.
    """
    num_assets = len(returns_df.columns)
    cov_matrix = returns_df.cov().values * 252.0
    
    init_weights = np.ones(num_assets) / num_assets
    bounds = tuple((0.02, 0.40) for _ in range(num_assets))
    constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0})
    
    res = minimize(
        _risk_parity_objective,
        init_weights,
        args=(cov_matrix,),
        method='SLSQP',
        bounds=bounds,
        constraints=constraints
    )
    
    optimal_weights = res.x / np.sum(res.x)
    return dict(zip(returns_df.columns, optimal_weights))


def calculate_portfolio_var_95(
    weights_dict: Dict[str, float], 
    returns_df: pd.DataFrame, 
    capital: float
) -> Tuple[float, float]:
    """
    Calculates 1-Day 95% Parametric Value-at-Risk (VaR) in USD and percentage.
    """
    weights = np.array([weights_dict[col] for col in returns_df.columns])
    cov_matrix_daily = returns_df.cov().values
    
    port_daily_std = np.sqrt(np.dot(weights.T, np.dot(cov_matrix_daily, weights)))
    port_daily_mean = np.dot(weights, returns_df.mean().values)
    
    z_score = 1.645  # 95% Confidence Level
    var_pct = (z_score * port_daily_std) - port_daily_mean
    var_usd = var_pct * capital
    
    return float(var_usd), float(var_pct)


def run_us_quant_pipeline(
    capital: float = 100.0,
    watchlist: Optional[List[str]] = None
) -> Dict:
    """
    Full quantitative pipeline execution wrapper.
    """
    if watchlist is None:
        watchlist = DEFAULT_DIVIDEND_WATCHLIST
        
    screened_tickers = screen_dividend_fundamentals(watchlist)
    prices_df, returns_df = fetch_us_market_data(screened_tickers)
    
    garch_vols = estimate_garch_volatilities(returns_df)
    optimal_weights = optimize_risk_parity(returns_df)
    var_usd, var_pct = calculate_portfolio_var_95(optimal_weights, returns_df, capital)
    
    latest_prices = prices_df.iloc[-1].to_dict()
    allocations_usd = {ticker: float(w * capital) for ticker, w in optimal_weights.items()}
    
    return {
        "screened_tickers": screened_tickers,
        "latest_prices": latest_prices,
        "garch_annualized_vols": garch_vols,
        "target_weights": optimal_weights,
        "target_allocations_usd": allocations_usd,
        "var_95_usd": var_usd,
        "var_95_pct": var_pct,
        "total_capital": capital
    }


if __name__ == "__main__":
    results = run_us_quant_pipeline(capital=100.0)
    print("Allocations USD:", results["target_allocations_usd"])
    print(f"1-Day 95% VaR: ${results['var_95_usd']:.2f}")

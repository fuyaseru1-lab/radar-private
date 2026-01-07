from __future__ import annotations
from typing import Dict, List, Any, Optional
import math
import time
import random
import re
import pandas as pd
import numpy as np
import streamlit as st
import requests  # 和名取得用に追加

try:
    import yfinance as yf
except Exception:
    yf = None

# ==========================================
# ⚙️ 設定（執念のリトライ設定）
# ==========================================
MAX_RETRIES = 3       # 失敗しても3回までやり直す
RETRY_DELAY = 5.0     # やり直す前に5秒待つ

# 和名取得用の偽装ヘッダー
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_sleep_time():
    # 普段の待機時間（ゆらぎを持たせる）
    return random.uniform(2.0, 4.0)

def _safe_float(x, default=None):
    try:
        if x is None: return default
        return float(x)
    except Exception: return default

def _get_weather_icon(roe: Optional[float], roa: Optional[float]) -> str:
    if roe is None: return "—"
    if roe < 0: return "☔（赤字）"
    if roa is not None and roe >= 0.08 and roa >= 0.05: return "☀（優良）"
    return "☁（普通）"

def _calc_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def _calc_bollinger_bands(series, window=20, num_std=2):
    rolling_mean = series.rolling(window=window).mean()
    rolling_std = series.rolling(window=window).std()
    upper_band = rolling_mean + (rolling_std * num_std)
    lower_band = rolling_mean - (rolling_std * num_std)
    return upper_band, lower_band

def _calc_volume_profile_wall(hist, current_price, bins=50):
    try:
        if hist is None or hist.empty:
            return "—"
        
        p_min = min(hist['Close'].min(), current_price * 0.9)
        p_max = max(hist['Close'].max(), current_price * 1.1)
        
        bin_edges = np.linspace(p_min, p_max, bins)
        hist['bin'] = pd.cut(hist['Close'], bins=bin_edges)
        
        vol_profile = hist.groupby('bin', observed=False)['Volume'].sum()
        
        wall_df = pd.DataFrame({
            'price': [b.mid for b in vol_profile.index],
            'volume': vol_profile.values
        })

        upper_zone = wall_df[wall_df['price'] > current_price]
        lower_zone = wall_df[wall_df['price'] < current_price]
        
        upper_wall = None
        lower_wall = None
        
        if not upper_zone.empty:
            upper_wall = upper_zone.loc[upper_zone['volume'].idxmax(), 'price']
        if not lower_zone.empty:
            lower_wall = lower_zone.loc[lower_zone['volume'].idxmax(), 'price']
            
        threshold = 0.03
        is_upper_battle = False
        if upper_wall:
            diff = abs(upper_wall - current_price) / current_price
            if diff < threshold: is_upper_battle = True
            
        is_lower_battle = False
        if lower_wall:
            diff = abs(lower_wall - current_price) / current_price
            if diff < threshold: is_lower_battle = True
        
        if is_upper_battle:
            return f"🔥上壁激戦中 ({upper_wall:,.0f}円)"
        elif is_lower_battle:
            return f"⚠️下壁激戦中 ({lower_wall:,.0f}円)"
        else:
            parts = []
            if upper_wall:
                parts.append(f"🚧上壁 {upper_wall:,.0f}円")
            if lower_wall:
                parts.append(f"🛡️下壁 {lower_wall:,.0f}円")
            if not parts: return "壁なし"
            return " / ".join(parts)

    except Exception:
        return "—"

def _calc_big_player_score(market_cap, pbr, volume_ratio):
    score = 0
    if market_cap is not None:
        mc_oku = market_cap / 100000000 
        if 1000 <= mc_oku <= 2000: score += 50
        elif 500 <= mc_oku < 1000: score += 40
        elif 2000 < mc_oku <= 3000: score += 35
        elif 300 <= mc_oku < 500: score += 20
        elif 3000 < mc_oku <= 10000: score += 10
    
    if pbr is not None and 0 < pbr < 1.0: score += 20
    if volume_ratio is not None:
        if volume_ratio >= 3.0: score += 30
        elif volume_ratio >= 2.0: score += 20
        elif volume_ratio >= 1.5: score += 10
    return min(95, score)

def _fetch_with_retry(ticker_symbol):
    """執念のリトライロジック"""
    for attempt in range(MAX_RETRIES):
        try:
            t = yf.Ticker(ticker_symbol)
            hist = t.history(period="6mo")
            if hist is not None and not hist.empty:
                return t, hist
            else:
                raise ValueError("Empty Data")
        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)

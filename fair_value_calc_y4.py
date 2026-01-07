from __future__ import annotations
from typing import Dict, List, Any, Optional
import math
import streamlit as st
import time
import pandas as pd
import numpy as np

try:
    import yfinance as yf
except Exception:
    yf = None

def _safe_float(x, default=None):
    try:
        if x is None: return default
        v = float(x)
        if math.isnan(v): return default
        return v
    except Exception: return default

def _get_weather_icon(roe: Optional[float], roa: Optional[float]) -> str:
    if roe is None: return "—"
    if roe < 0: return "☔（赤字）"
    if roa is not None and roe >= 0.08 and roa >= 0.05: return "☀（優良）"
    return "☁（普通）"

def _calc_rsi(series, period=14):
    if len(series) < period + 1: return pd.Series([50]*len(series))
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def _calc_bollinger_bands(series, window=20, num_std=2):
    if len(series) < window: return series, series
    rolling_mean = series.rolling(window=window).mean()
    rolling_std = series.rolling(window=window).std()
    upper_band = rolling_mean + (rolling_std * num_std)
    lower_band = rolling_mean - (rolling_std * num_std)
    return upper_band, lower_band

def _calc_volume_profile_wall(hist, current_price, bins=50):
    """
    需給の壁（価格帯別出来高）を計算
    """
    try:
        if hist is None or hist.empty: return "—"
        
        # データコピー
        df = hist.copy()
        
        # 最低限のデータチェック
        if len(df) < 3: return "—"
        if 'Close' not in df.columns or 'Volume' not in df.columns: return "—"

        # 価格帯ビンの作成
        if df['Close'].max() == df['Close'].min():
             return "🧱値動きなし"

        df['price_bin'] = pd.cut(df['Close'], bins=bins)
        
        # 出来高集計
        vol_profile = df.groupby('price_bin', observed=False)['Volume'].sum()
        
        # 上の壁
        upper_candidates = vol_profile[vol_profile.index.map(lambda x: x.mid) > current_price]
        upper_wall = None
        if not upper_candidates.empty and upper_candidates.sum() > 0:
            upper_wall = upper_candidates.idxmax().mid

        # 下の壁
        lower_candidates = vol_profile[vol_profile.index.map(lambda x: x.mid) < current_price]
        lower_wall = None
        if not lower_candidates.empty and lower_candidates.sum() > 0:
            lower_wall = lower_candidates.idxmax().mid
            
        # --- 3%ルール判定 ---
        if upper_wall and (upper_wall - current_price) / current_price <= 0.03:
             return f"🔥上壁激戦中 ({upper_wall:,.0f}円)"
             
        if lower_wall and (current_price - lower_wall) / current_price <= 0.03:
             return f"⚠️下壁激戦中 ({lower_wall:,.0f}円)"
        
        u_text = f"🚧上 {upper_wall:,.0f}円" if upper_wall else "🟦青天井"
        l_text = f"🛡️下 {lower_wall:,.0f}円" if lower_wall else "🕳️底なし"
        
        return f"{u_text} / {l_text}"

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

def _fetch_single_stock(code4: str) -> dict:
    # 安定のために3秒待機（これは必須）
    time.sleep(3.0)

    ticker = f"{code4}.T"
    
    # ---------------------------------------------------------
    # 1. 株価データ (History) の取得 【最優先】
    # ---------------------------------------------------------
    hist = None
    try:
        t = yf.Ticker(ticker)
        # まず6ヶ月
        hist = t.history(period="6mo")
        # ダメなら1ヶ月
        if hist.empty:
            time.sleep(1)
            hist = t.history(period="1mo")
            
    except Exception:
        hist = None

    # 株価すら取れない＝本当に存在しないか通信遮断
    if hist is None or hist.empty:
        return {
            "code": code4, "name": "取得失敗", "weather": "—", "price": None, 
            "fair_value": None, "upside_pct": None, "note": "アクセス不可", 
            "dividend": None, "dividend_amount": None, "growth": None, 
            "market_cap": None, "big_prob": None,
            "signal_icon": "—", "volume_wall": "—"
        }

    # ---------------------------------------------------------
    # 2. テクニカル & 壁 計算 (財務データがなくても計算する)
    # ---------------------------------------------------------
    price = _safe_float(hist["Close"].iloc[-1], 0)
    current_volume = _safe_float(hist["Volume"].iloc[-1], 0)
    
    # ★需給の壁 (ここで計算！)
    volume_wall = _calc_volume_profile_wall(hist, price)

    # シグナル
    signal_icon = "—"
    try:
        if len(hist) > 0:
            rsi_series = _calc_rsi(hist["Close"])
            rsi_val = rsi_series.iloc[-1]
            
            # ボリンジャー
            ma = hist["Close"].rolling(20).mean()
            std = hist["Close"].rolling(20).std()
            ub = ma + 2 * std
            lb = ma - 2 * std
            
            score = 0
            if rsi_val <= 30: score += 2
            elif rsi_val >= 70: score -= 2
            
            if price <= lb.iloc[-1]: score += 2
            elif price >= ub.iloc[-1]: score -= 2
            
            if score >= 3: signal_icon = "↑◎"
            elif score >= 1: signal_icon = "↗〇"
            elif score == 0: signal_icon = "→△"
            elif score <= -3: signal_icon = "↓✖"
            else: signal_icon = "↘▲"
    except:
        pass

    # ---------------------------------------------------------
    # 3. 財務データ (Info) の取得 【失敗してもOKにする】
    # ---------------------------------------------------------
    info = {}
    try:
        info = t.info
    except:
        pass # 財務が取れなくてもエラーにしない

    # 名前 (Infoがダメならコードを入れる)
    long_name = info.get("longName", "")
    short_name = info.get("shortName", "")
    if long_name: name = long_name
    elif short_name: name = short_name
    else: name = f"({code4})"

    # 各種指標
    eps = _safe_float(info.get("trailingEps"), info.get("forwardEps", None))
    bps = _safe_float(info.get("bookValue"), None)
    roe = _safe_float(info.get("returnOnEquity"), None)
    roa = _safe_float(info.get("returnOnAssets"), None)
    mcap = _safe_float(info.get("marketCap"), None)
    avg_vol = _safe_float(info.get("averageVolume"), None)
    
    # 天気
    weather = _get_weather_icon(roe, roa)

    # 理論株価
    fair_value = None
    note = "OK"
    if bps is None:
        note = "財務データ不足"
    elif eps is None or eps < 0:
        note = "赤字/算出不可"
    else:
        try:
            val = 22.5 * eps * bps
            if val > 0:
                fair_value = round(math.sqrt(val), 0)
                note = f"EPS{eps:.1f}×BPS{bps:.0f}"
        except: pass

    upside_pct = None
    if fair_value and price:
        upside_pct = round((fair_value / price - 1) * 100, 2)

    # 配当・成長性
    div_rate = None
    raw_div = info.get("dividendRate")
    if raw_div and price: div_rate = (raw_div / price) * 100
    
    growth = _safe_float(info.get("revenueGrowth"), None)
    if growth: growth *= 100
    
    # 大口期待度
    pbr = (price / bps) if (price and bps and bps > 0) else None
    vol_ratio = (current_volume / avg_vol) if (avg_vol and avg_vol > 0) else 0
    big_prob = _calc_big_player_score(mcap, pbr, vol_ratio)

    return {
        "code": code4, "name": name, "weather": weather, "price": price,
        "fair_value": fair_value, "upside_pct": upside_pct, "note": note, 
        "dividend": div_rate, "dividend_amount": raw_div,
        "growth": growth, "market_cap": mcap, "big_prob": big_prob,
        "signal_icon": signal_icon,
        "volume_wall": volume_wall # ここ重要
    }

@st.cache_data(ttl=3600, show_spinner=False)
def calc_fuyaseru_bundle(codes: List[str]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for code in codes:
        try:
            res = _fetch_single_stock(code)
            out[code] = res
        except:
            pass
    return out

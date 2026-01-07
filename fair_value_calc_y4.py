from __future__ import annotations
from typing import Dict, List, Any, Optional
import math
import time
import random
import pandas as pd
import numpy as np
import streamlit as st

try:
    import yfinance as yf
except Exception:
    yf = None

# ==========================================
# ⚙️ 設定（執念のリトライ設定）
# ==========================================
MAX_RETRIES = 3       # 失敗しても3回までやり直す
RETRY_DELAY = 5.0     # やり直す前に5秒待つ（Yahooを怒らせないため）

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
        
        # ★表記修正：円と壁を追加
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
    """執念のリトライロジック：取れるまで3回粘る"""
    for attempt in range(MAX_RETRIES):
        try:
            t = yf.Ticker(ticker_symbol)
            # まずHistoryをとってみる
            hist = t.history(period="6mo")
            if hist is not None and not hist.empty:
                return t, hist # 成功したら返す
            else:
                raise ValueError("Empty Data")
        except Exception:
            # 失敗したら待機してリトライ
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                return None, None
    return None, None

def _fetch_single_stock(code4: str) -> dict:
    # 最初の待機
    time.sleep(get_sleep_time())
    
    ticker = f"{code4}.T"
    
    # ★リトライ機能付きでデータ取得
    t, hist = _fetch_with_retry(ticker)
    
    # それでもダメならエラー
    if t is None or hist is None:
         return {
            "code": code4, "name": "エラー", "weather": "—", "price": None, 
            "fair_value": None, "upside_pct": None, "note": "データ取得不可(Yahoo拒否)", 
            "dividend": None, "dividend_amount": None, "growth": None, 
            "market_cap": None, "big_prob": None,
            "signal_icon": "—", "volume_wall": "—"
        }

    # ここから先はデータが取れた前提の処理
    try:
        price = _safe_float(hist["Close"].dropna().iloc[-1], None)
        current_volume = _safe_float(hist["Volume"].dropna().iloc[-1], 0)
        
        volume_wall = "—"
        if len(hist) > 30 and price:
            volume_wall = _calc_volume_profile_wall(hist, price)

        signal_icon = "—"
        if len(hist) > 75:
            score = 0
            rsi_series = _calc_rsi(hist["Close"])
            rsi_val = rsi_series.iloc[-1] if not rsi_series.empty else 50
            if rsi_val <= 30: score += 2
            elif rsi_val <= 40: score += 1
            elif rsi_val >= 70: score -= 2
            elif rsi_val >= 60: score -= 1
            
            ma75 = hist["Close"].rolling(window=75).mean().iloc[-1]
            if price > ma75: score += 1
            else: score -= 1
            
            upper, lower = _calc_bollinger_bands(hist["Close"])
            ub_val = upper.iloc[-1]
            lb_val = lower.iloc[-1]
            
            if price <= lb_val: score += 2
            elif price >= ub_val: score -= 2
            
            if score >= 3: signal_icon = "↑◎"
            elif score >= 1: signal_icon = "↗〇"
            elif score == 0: signal_icon = "→△"
            elif score >= -2: signal_icon = "↘▲"
            else: signal_icon = "↓✖"
            
    except Exception:
        # 万が一計算でコケた場合
        return {
            "code": code4, "name": "計算エラー", "weather": "—", "price": None, 
            "fair_value": None, "upside_pct": None, "note": "計算失敗", 
            "dividend": None, "dividend_amount": None, "growth": None, 
            "market_cap": None, "big_prob": None,
            "signal_icon": "—", "volume_wall": "—"
        }

    # ----------------------------------------
    # Phase 2: 財務データ（Info vs FastInfo）
    # ----------------------------------------
    info = {}
    try:
        info = t.info
    except Exception:
        info = {}

    fast_info = {}
    try:
        fast_info = t.fast_info
    except:
        pass

    def get_val(key_info, key_fast=None):
        val = info.get(key_info)
        if val is None and key_fast and fast_info:
            try:
                val = getattr(fast_info, key_fast, None)
            except:
                val = None
        return _safe_float(val, None)

    eps_trail  = get_val("trailingEps")
    eps_fwd    = get_val("forwardEps")
    bps        = get_val("bookValue")
    roe        = get_val("returnOnEquity")
    roa        = get_val("returnOnAssets")
    market_cap = get_val("marketCap", "market_cap")
    avg_volume = get_val("averageVolume")
    
    long_name = info.get("longName", info.get("shortName", f"({code4})"))
    
    pbr = (price / bps) if (price and bps and bps > 0) else None
    
    volume_ratio = 0
    if avg_volume and avg_volume > 0:
        volume_ratio = current_volume / avg_volume
    
    big_prob = _calc_big_player_score(market_cap, pbr, volume_ratio)
    
    div_rate = None
    raw_div = info.get("dividendRate")
    if raw_div is not None and price and price > 0:
        div_rate = (raw_div / price) * 100.0

    rev_growth = get_val("revenueGrowth")
    if rev_growth: rev_growth *= 100.0

    weather = _get_weather_icon(roe, roa)

    # ----------------------------------------
    # Phase 3: 理論株価計算
    # ----------------------------------------
    fair_value = None
    note = "OK"
    calc_eps = None
    is_forecast = False
    
    q_type = info.get("quoteType", "").upper()
    short_name = info.get("shortName", "").upper()
    is_fund = False
    if q_type in ["ETF", "MUTUALFUND"]: is_fund = True
    elif "ETF" in short_name or "REIT" in short_name or "リート" in long_name: is_fund = True

    if is_fund:
        note = "ETF/REIT対象外"
    elif not price: 
        note = "現在値不明"
    elif bps is None: 
        note = "財務データ取得失敗"
    else:
        if eps_trail is not None and eps_trail > 0:
            calc_eps = eps_trail
        elif eps_fwd is not None and eps_fwd > 0:
            calc_eps = eps_fwd
            is_forecast = True
        
        if calc_eps is None: 
            if eps_trail is not None and eps_trail < 0:
                 note = "赤字のため算出不可"
            else:
                 note = "算出不能"
        else:
            product = 22.5 * calc_eps * bps
            if product > 0:
                fair_value = round(math.sqrt(product), 0)
                if is_forecast:
                    note = f"※予想EPS {calc_eps:,.1f} × BPS {bps:,.0f}"
                else:
                    note = f"EPS {calc_eps:,.1f} × BPS {bps:,.0f}"
            else:
                note = "資産毀損リスクあり"
    
    upside_pct = None
    if price and fair_value:
         upside_pct = round((fair_value / price - 1.0) * 100.0, 2)

    return {
        "code": code4, "name": long_name, "weather": weather, "price": price,
        "fair_value": fair_value, "upside_pct": upside_pct, "note": note, 
        "dividend": div_rate, "dividend_amount": raw_div,
        "growth": rev_growth, "market_cap": market_cap, "big_prob": big_prob,
        "signal_icon": signal_icon,
        "volume_wall": volume_wall
    }

@st.cache_data(ttl=43200, show_spinner=False)
def calc_fuyaseru_bundle(codes: List[str]) -> Dict[str, Dict[str, Any]]:
    out = {}
    total = len(codes)
    progress_bar = None
    try:
        if total > 1:
            progress_bar = st.progress(0)
    except: pass

    for i, code in enumerate(codes):
        try:
            res = _fetch_single_stock(code)
            out[code] = res
        except Exception:
            out[code] = {
                "code": code, "name": "エラー", "weather": "—", "price": None,
                "fair_value": None, "upside_pct": None, "note": "処理失敗",
                "dividend": None, "dividend_amount": None, "growth": None,
                "market_cap": None, "big_prob": None, "signal_icon": "—", "volume_wall": "—"
            }
        
        if progress_bar:
            progress_bar.progress((i + 1) / total)

    if progress_bar:
        progress_bar.empty()
        
    return out

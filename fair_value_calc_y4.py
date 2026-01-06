from __future__ import annotations
from typing import Dict, List, Any, Optional
import math
import concurrent.futures
import streamlit as st

try:
    import yfinance as yf
except Exception:
    yf = None

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
    """1銘柄分の取得ロジック"""
    ticker = f"{code4}.T"
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist is None or hist.empty:
            return {"code": code4, "name": "存在しない銘柄", "note": "—"}
        
        info = t.info
        price = _safe_float(hist["Close"].dropna().iloc[-1], None)
        current_volume = _safe_float(hist["Volume"].dropna().iloc[-1], 0)
        eps = _safe_float(info.get("trailingEps"), None) 
        bps = _safe_float(info.get("bookValue"), None)
        roe = _safe_float(info.get("returnOnEquity"), None) 
        roa = _safe_float(info.get("returnOnAssets"), None) 
        market_cap = _safe_float(info.get("marketCap"), None)
        avg_volume = _safe_float(info.get("averageVolume"), None)
        
        pbr = (price / bps) if (price and bps and bps > 0) else None
        volume_ratio = (current_volume / avg_volume) if (avg_volume and avg_volume > 0) else 0
        big_prob = _calc_big_player_score(market_cap, pbr, volume_ratio)
        div_rate = (_safe_float(info.get("dividendRate"), 0) / price * 100) if (price and price > 0) else None
        rev_growth = _safe_float(info.get("revenueGrowth"), None)
        if rev_growth: rev_growth *= 100.0

        name = info.get("longName", info.get("shortName", f"({code4})"))
        weather = _get_weather_icon(roe, roa)

        fair_value = None
        note = "OK"
        if not price: note = "現在値取得不可"
        elif eps is None or bps is None: note = "財務データ不足"
        elif eps < 0: note = "赤字のため算出不可"
        else:
            product = 22.5 * eps * bps
            if product > 0:
                fair_value = round(math.sqrt(product), 0)
                note = f"EPS {eps:,.1f} × BPS {bps:,.0f}"
            else: note = "算出不可"
        
        # 上昇余地計算
        upside_pct = None
        if price and fair_value:
             upside_pct = round((fair_value / price - 1.0) * 100.0, 2)

        return {
            "code": code4, "name": name, "weather": weather, "price": price,
            "fair_value": fair_value, "upside_pct": upside_pct, "note": note, 
            "dividend": div_rate, "growth": rev_growth, 
            "market_cap": market_cap, "big_prob": big_prob
        }
    except Exception as e:
        return {"code": code4, "name": "エラー", "note": str(e)}

@st.cache_data(ttl=3600, show_spinner=False)
def calc_fuyaseru_bundle(codes: List[str]) -> Dict[str, Dict[str, Any]]:
    """並列処理で一括計算"""
    out = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_fetch_single_stock, code): code for code in codes}
        for f in concurrent.futures.as_completed(futures):
            try:
                res = f.result()
                out[futures[f]] = res
            except: pass
    return out

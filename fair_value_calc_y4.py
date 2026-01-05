# fair_value_calc_y4.py
# ============================================
# フヤセルブレイン：理論株価・上昇余地・星レーティング（並列処理・爆速版）
# ============================================

from __future__ import annotations
from typing import Dict, List, Any, Optional
import math
import concurrent.futures # ★並列処理用
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

def _calc_rating_from_upside(upside_pct: Optional[float]) -> Optional[int]:
    if upside_pct is None: return None
    if upside_pct >= 50: return 5
    if upside_pct >= 30: return 4
    if upside_pct >= 15: return 3
    if upside_pct >= 5: return 2
    if upside_pct >= 0: return 1
    return 0

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
    
    if pbr is not None and 0 < pbr < 1.0:
        score += 20
        
    if volume_ratio is not None:
        if volume_ratio >= 3.0: score += 30
        elif volume_ratio >= 2.0: score += 20
        elif volume_ratio >= 1.5: score += 10

    return min(95, score)

# ★キャッシュ設定：1時間有効
@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_single_stock(code4: str) -> dict:
    """1銘柄分のデータを取得・計算する関数"""
    if yf is None:
        return {"code": code4, "note": "ライブラリ不足"}

    ticker = f"{code4}.T"
    try:
        t = yf.Ticker(ticker)
        
        # 1. 財務データ (info)
        info = t.info
        
        # 2. 現在値 & 出来高 (history)
        hist = t.history(period="5d")
        if hist is None or hist.empty:
            return {"code": code4, "name": "取得失敗", "note": "データなし"}
        
        price = _safe_float(hist["Close"].dropna().iloc[-1], None)
        current_volume = _safe_float(hist["Volume"].dropna().iloc[-1], 0)
        
        eps = _safe_float(info.get("trailingEps"), None) 
        bps = _safe_float(info.get("bookValue"), None)
        roe = _safe_float(info.get("returnOnEquity"), None) 
        roa = _safe_float(info.get("returnOnAssets"), None) 
        market_cap = _safe_float(info.get("marketCap"), None)
        avg_volume = _safe_float(info.get("averageVolume"), None)
        
        pbr = None
        if price and bps and bps > 0:
            pbr = price / bps

        volume_ratio = 0
        if avg_volume and avg_volume > 0:
            volume_ratio = current_volume / avg_volume

        big_prob = _calc_big_player_score(market_cap, pbr, volume_ratio)
        div_rate = _safe_float(info.get("dividendRate"), None)
        if div_rate and price: div_rate = (div_rate / price) * 100.0
        
        rev_growth = _safe_float(info.get("revenueGrowth"), None)
        if rev_growth: rev_growth *= 100.0

        name = info.get("longName", info.get("shortName", f"({code4})"))
        weather = _get_weather_icon(roe, roa)

        # 理論株価計算
        fair_value = None
        note = "OK"
        if not price: note = "現在値不明"
        elif eps is None or bps is None: note = "財務データ不足"
        elif eps < 0: note = "赤字"
        elif bps < 0: note = "債務超過"
        else:
            product = 22.5 * eps * bps
            if product < 0: note = "計算不可"
            else:
                fair_value = round(math.sqrt(product), 0)
                note = f"EPS{eps:.0f}×BPS{bps:.0f}"

        # 上昇余地計算
        upside_pct = None
        rating = None
        if price and fair_value:
            upside_pct = round((fair_value / price - 1.0) * 100.0, 2)
            rating = _calc_rating_from_upside(upside_pct)

        return {
            "code": code4,
            "name": name,
            "weather": weather,
            "price": price,
            "fair_value": fair_value,
            "upside_pct": upside_pct,
            "rating": rating,
            "dividend": div_rate,
            "growth": rev_growth,
            "market_cap": market_cap,
            "big_prob": big_prob,
            "note": note,
        }

    except Exception as e:
        return {"code": code4, "name": "エラー", "note": str(e)}

def calc_fuyaseru_bundle(codes: List[str]) -> Dict[str, Dict[str, Any]]:
    """並列処理で一気にデータ取得する親関数"""
    out: Dict[str, Dict[str, Any]] = {}
    
    # ★ここが高速化のキモ：ThreadPoolExecutor
    # max_workers=8 程度で同時にYahooへアクセスします
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_code = {executor.submit(_fetch_single_stock, code): code for code in codes}
        
        for future in concurrent.futures.as_completed(future_to_code):
            try:
                data = future.result()
                code = data["code"]
                out[code] = data
            except Exception:
                pass
                
    return out

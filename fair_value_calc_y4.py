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
    # 時価総額スコア
    if market_cap is not None:
        mc_oku = market_cap / 100000000 
        if 1000 <= mc_oku <= 2000: score += 50
        elif 500 <= mc_oku < 1000: score += 40
        elif 2000 < mc_oku <= 3000: score += 35
        elif 300 <= mc_oku < 500: score += 20
        elif 3000 < mc_oku <= 10000: score += 10
    
    # PBRスコア
    if pbr is not None and 0 < pbr < 1.0: score += 20
    
    # 出来高スコア
    if volume_ratio is not None:
        if volume_ratio >= 3.0: score += 30
        elif volume_ratio >= 2.0: score += 20
        elif volume_ratio >= 1.5: score += 10
        
    return min(95, score)

def _fetch_single_stock(code4: str) -> dict:
    ticker = f"{code4}.T"
    try:
        t = yf.Ticker(ticker)
        # 過去5日分取得（土日対策）
        hist = t.history(period="5d")
        
        # データが全く取れない場合
        if hist is None or hist.empty:
            return {"code": code4, "name": "データ取得失敗", "note": "Yahooにデータなし"}
        
        info = t.info
        
        # 終値と出来高
        price = _safe_float(hist["Close"].dropna().iloc[-1], None)
        current_volume = _safe_float(hist["Volume"].dropna().iloc[-1], 0)
        
        # 財務データ（None対策済み）
        eps = _safe_float(info.get("trailingEps"), None) 
        bps = _safe_float(info.get("bookValue"), None)
        roe = _safe_float(info.get("returnOnEquity"), None) 
        roa = _safe_float(info.get("returnOnAssets"), None) 
        market_cap = _safe_float(info.get("marketCap"), None)
        avg_volume = _safe_float(info.get("averageVolume"), None)
        
        # PBR計算
        pbr = None
        if price and bps and bps > 0:
            pbr = price / bps

        # 出来高倍率
        volume_ratio = 0
        if avg_volume and avg_volume > 0:
            volume_ratio = current_volume / avg_volume

        # 大口スコア
        big_prob = _calc_big_player_score(market_cap, pbr, volume_ratio)
        
        name = info.get("longName", info.get("shortName", f"({code4})"))
        weather = _get_weather_icon(roe, roa)

        # 理論株価計算（赤字対応）
        fair_value = None
        note = "OK"
        
        if not price: 
            note = "株価不明"
        elif eps is None or bps is None: 
            note = "財務情報なし"
        elif eps < 0: 
            note = "赤字のため算出不可" # ★7777はここで処理される
        else:
            product = 22.5 * eps * bps
            if product > 0:
                fair_value = round(math.sqrt(product), 0)
            else:
                note = "計算不能"
        
        # 上昇余地
        upside_pct = None
        if price and fair_value:
             upside_pct = round((fair_value / price - 1.0) * 100.0, 2)

        return {
            "code": code4, "name": name, "weather": weather, "price": price,
            "fair_value": fair_value, "upside_pct": upside_pct, "note": note, 
            "market_cap": market_cap, "big_prob": big_prob
        }
    except Exception as e:
        return {"code": code4, "name": "エラー", "note": str(e)}

@st.cache_data(ttl=3600, show_spinner=False)
def calc_fuyaseru_bundle(codes: List[str]) -> Dict[str, Dict[str, Any]]:
    out = {}
    # 並列処理
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_fetch_single_stock, code): code for code in codes}
        for f in concurrent.futures.as_completed(futures):
            try:
                res = f.result()
                out[futures[f]] = res
            except:
                pass
    return out

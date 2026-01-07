from __future__ import annotations
from typing import Dict, List, Any, Optional
import math
import streamlit as st
import time
import random
import pandas as pd

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
    現在値より「上」の最強壁と、「下」の最強壁をそれぞれ特定し、
    距離（3%ルール）に応じて表示内容を切り替える
    """
    try:
        if hist.empty or len(hist) < 5: return "—"
        hist = hist.copy()
        
        # 価格帯ビンの作成
        hist['price_bin'] = pd.cut(hist['Close'], bins=bins)
        vol_profile = hist.groupby('price_bin', observed=False)['Volume'].sum()
        
        # 上の壁（現在値より上にあるビンの中で最大出来高のもの）
        upper_candidates = vol_profile[vol_profile.index.map(lambda x: x.mid) > current_price]
        upper_wall = None
        if not upper_candidates.empty:
            upper_wall = upper_candidates.idxmax().mid

        # 下の壁（現在値より下にあるビンの中で最大出来高のもの）
        lower_candidates = vol_profile[vol_profile.index.map(lambda x: x.mid) < current_price]
        lower_wall = None
        if not lower_candidates.empty:
            lower_wall = lower_candidates.idxmax().mid
            
        # --- 判定ロジック (3%ルール) ---
        
        # 1. 上の壁に接近中 (乖離3%以内)
        if upper_wall and (upper_wall - current_price) / current_price <= 0.03:
             return f"🔥上壁激戦中 ({upper_wall:,.0f}円)"
             
        # 2. 下の壁に接近中 (乖離3%以内)
        if lower_wall and (current_price - lower_wall) / current_price <= 0.03:
             return f"⚠️下壁激戦中 ({lower_wall:,.0f}円)"
        
        # 3. どちらの壁とも距離がある（レンジ内） -> 両方表示
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
    time.sleep(random.uniform(1.5, 3.0)) # 丁寧なアクセス

    ticker = f"{code4}.T"
    hist = None
    info = {}
    error_msg = "取得失敗"
    
    # リトライロジック
    for attempt in range(3):
        try:
            t = yf.Ticker(ticker)
            temp_hist = t.history(period="6mo")
            if not temp_hist.empty:
                hist = temp_hist
                try: info = t.info
                except: pass
                break
            else:
                time.sleep(3)
        except Exception as e:
            time.sleep(3)
            error_msg = str(e)

    if hist is None or hist.empty:
        try:
            t = yf.Ticker(ticker)
            temp_hist = t.history(period="1mo")
            if not temp_hist.empty:
                hist = temp_hist
                error_msg = "データ不足(1moのみ)"
                try: info = t.info
                except: pass
        except: pass

    if hist is None or hist.empty:
        note_text = "アクセス不可" if "404" not in str(error_msg) else "存在しない銘柄"
        if "429" in str(error_msg): note_text = "制限中(429)"

        return {
            "code": code4, "name": "取得エラー", "weather": "—", "price": None, 
            "fair_value": None, "upside_pct": None, "note": note_text, 
            "dividend": None, "dividend_amount": None, "growth": None, 
            "market_cap": None, "big_prob": None,
            "signal_icon": "—", "volume_wall": "—"
        }
    
    try:
        price = _safe_float(hist["Close"].dropna().iloc[-1], None)
        current_volume = _safe_float(hist["Volume"].dropna().iloc[-1], 0)
        
        # ★ここが重要：データ数に応じて壁計算を呼ぶ
        volume_wall = "—"
        if len(hist) > 10 and price:
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
        elif len(hist) > 0:
            signal_icon = "データ不足"
        
        eps_trail = _safe_float(info.get("trailingEps"), None) 
        eps_fwd   = _safe_float(info.get("forwardEps"), None)
        bps       = _safe_float(info.get("bookValue"), None)
        roe = _safe_float(info.get("returnOnEquity"), None) 
        roa = _safe_float(info.get("returnOnAssets"), None) 
        market_cap = _safe_float(info.get("marketCap"), None)
        avg_volume = _safe_float(info.get("averageVolume"), None)
        
        q_type = info.get("quoteType", "").upper()
        long_name = info.get("longName", "").upper()
        short_name = info.get("shortName", "").upper()

        pbr = (price / bps) if (price and bps and bps > 0) else None
        volume_ratio = (current_volume / avg_volume) if (avg_volume and avg_volume > 0) else 0
        big_prob = _calc_big_player_score(market_cap, pbr, volume_ratio)
        
        div_rate = None
        raw_div = info.get("dividendRate")
        if raw_div is not None and price and price > 0:
            div_rate = (raw_div / price) * 100.0

        rev_growth = _safe_float(info.get("revenueGrowth"), None)
        if rev_growth: rev_growth *= 100.0

        name = info.get("longName", info.get("shortName", f"({code4})"))
        weather = _get_weather_icon(roe, roa)

        fair_value = None
        note = "OK"
        calc_eps = None
        is_forecast = False
        is_fund = False

        if q_type in ["ETF", "MUTUALFUND"]:
            is_fund = True
        elif "ETF" in short_name or "REIT" in short_name or "リート" in long_name:
            is_fund = True

        if is_fund:
            note = "ETF/REIT等のため対象外"
        elif not price: 
            note = "現在値取得不可"
        elif bps is None: 
            note = "財務データ不足"
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
            "code": code4, "name": name, "weather": weather, "price": price,
            "fair_value": fair_value, "upside_pct": upside_pct, "note": note, 
            "dividend": div_rate, "dividend_amount": raw_div,
            "growth": rev_growth, "market_cap": market_cap, "big_prob": big_prob,
            "signal_icon": signal_icon,
            "volume_wall": volume_wall
        }
    except Exception as e:
        return {
            "code": code4, "name": "処理エラー", "weather": "—", "price": None,
            "fair_value": None, "upside_pct": None, "note": str(e),
            "dividend": None, "dividend_amount": None, "growth": None,
            "market_cap": None, "big_prob": None, "signal_icon": "—", "volume_wall": "—"
        }

@st.cache_data(ttl=43200, show_spinner=False)
def calc_fuyaseru_bundle(codes: List[str]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for code in codes:
        try:
            res = _fetch_single_stock(code)
            out[code] = res
        except: pass
    return out

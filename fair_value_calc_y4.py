from __future__ import annotations
from typing import Dict, List, Any, Optional
import math
import streamlit as st
import time
import random
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
    エラーハンドリングを強化し、株価さえあれば必ず計算するように修正
    """
    try:
        if hist is None or hist.empty or len(hist) < 3: return "—"
        
        # 必要なカラムがあるか確認
        if 'Close' not in hist.columns or 'Volume' not in hist.columns:
            return "—"
            
        # データコピーとクリーニング
        df = hist.copy()
        df = df.dropna(subset=['Close', 'Volume'])
        
        if df.empty: return "—"

        # 価格帯ビンの作成（エラー回避のため qcut ではなく cut を使用）
        # 価格幅がない（ストップ高張り付き等）場合の対策
        if df['Close'].max() == df['Close'].min():
             return "🧱値動きなし"

        df['price_bin'] = pd.cut(df['Close'], bins=bins)
        
        # 出来高集計
        vol_profile = df.groupby('price_bin', observed=False)['Volume'].sum()
        
        # 上の壁（現在値より上）
        upper_mask = vol_profile.index.map(lambda x: x.mid) > current_price
        upper_candidates = vol_profile[upper_mask]
        
        upper_wall = None
        if not upper_candidates.empty and upper_candidates.sum() > 0:
            upper_wall = upper_candidates.idxmax().mid

        # 下の壁（現在値より下）
        lower_mask = vol_profile.index.map(lambda x: x.mid) < current_price
        lower_candidates = vol_profile[lower_mask]
        
        lower_wall = None
        if not lower_candidates.empty and lower_candidates.sum() > 0:
            lower_wall = lower_candidates.idxmax().mid
            
        # --- 判定ロジック (3%ルール) ---
        
        # 1. 上の壁に接近中
        if upper_wall and (upper_wall - current_price) / current_price <= 0.03:
             return f"🔥上壁激戦中 ({upper_wall:,.0f}円)"
             
        # 2. 下の壁に接近中
        if lower_wall and (current_price - lower_wall) / current_price <= 0.03:
             return f"⚠️下壁激戦中 ({lower_wall:,.0f}円)"
        
        # 3. レンジ表示
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
    # 待機時間を少し長めに（安全策）
    time.sleep(random.uniform(2.0, 4.0))

    ticker = f"{code4}.T"
    hist = None
    info = {}
    
    # ---------------------------------------------------------
    # 1. 株価データ (History) の取得 【最優先】
    # ---------------------------------------------------------
    error_msg = ""
    t = yf.Ticker(ticker)
    
    # 3回リトライ
    for _ in range(3):
        try:
            temp_hist = t.history(period="6mo")
            if not temp_hist.empty:
                hist = temp_hist
                break
            time.sleep(2)
        except Exception as e:
            error_msg = str(e)
            time.sleep(2)
    
    # 6ヶ月ダメなら1ヶ月
    if hist is None or hist.empty:
        try:
            temp_hist = t.history(period="1mo")
            if not temp_hist.empty:
                hist = temp_hist
        except: pass

    # 株価すら取れなかったら終了
    if hist is None or hist.empty:
        note_text = "アクセス不可"
        if "404" in error_msg: note_text = "存在しない銘柄"
        if "429" in error_msg: note_text = "制限中(429)"
        
        return {
            "code": code4, "name": "取得エラー", "weather": "—", "price": None, 
            "fair_value": None, "upside_pct": None, "note": note_text, 
            "dividend": None, "dividend_amount": None, "growth": None, 
            "market_cap": None, "big_prob": None,
            "signal_icon": "—", "volume_wall": "—"
        }

    # ---------------------------------------------------------
    # 2. テクニカル & 需給の壁 計算 (株価があれば絶対やる)
    # ---------------------------------------------------------
    price = _safe_float(hist["Close"].dropna().iloc[-1], None)
    current_volume = _safe_float(hist["Volume"].dropna().iloc[-1], 0)
    
    # 需給の壁
    volume_wall = "—"
    if price is not None:
        volume_wall = _calc_volume_profile_wall(hist, price)

    # シグナル
    signal_icon = "—"
    if len(hist) > 0:
        # データ不足でも動くように緩和
        try:
            score = 0
            # RSI
            rsi_series = _calc_rsi(hist["Close"])
            rsi_val = rsi_series.iloc[-1] if not rsi_series.empty else 50
            if rsi_val <= 30: score += 2
            elif rsi_val <= 40: score += 1
            elif rsi_val >= 70: score -= 2
            elif rsi_val >= 60: score -= 1
            
            # MA75 (データ足りなければMA25等にフォールバックも考えられるが、一旦75日なければスキップ)
            if len(hist) > 75:
                ma75 = hist["Close"].rolling(window=75).mean().iloc[-1]
                if price > ma75: score += 1
                else: score -= 1
            
            # BB
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
        except:
            signal_icon = "—"

    # ---------------------------------------------------------
    # 3. 財務データ (Info) の取得 【取れたらラッキー】
    # ---------------------------------------------------------
    try:
        info = t.info
    except:
        info = {}

    # Infoが空の場合の対策 (Nameなどは空文字になるので補完)
    long_name = info.get("longName", "")
    short_name = info.get("shortName", "")
    
    # 名前決定ロジック：Infoがダメならコードを表示
    if long_name: name = long_name
    elif short_name: name = short_name
    else: name = f"({code4})" 

    eps_trail = _safe_float(info.get("trailingEps"), None) 
    eps_fwd   = _safe_float(info.get("forwardEps"), None)
    bps       = _safe_float(info.get("bookValue"), None)
    roe = _safe_float(info.get("returnOnEquity"), None) 
    roa = _safe_float(info.get("returnOnAssets"), None) 
    market_cap = _safe_float(info.get("marketCap"), None)
    avg_volume = _safe_float(info.get("averageVolume"), None)
    
    q_type = info.get("quoteType", "").upper()
    if not q_type: # Info失敗時は名前から推測
        if "ETF" in name or "REIT" in name: q_type = "ETF"

    # 理論株価などの計算
    fair_value = None
    note = "OK"
    calc_eps = None
    is_forecast = False
    is_fund = False

    if q_type in ["ETF", "MUTUALFUND"]:
        is_fund = True
    elif "ETF" in name or "REIT" in name: # 補完判定
        is_fund = True

    if is_fund:
        note = "ETF/REIT等のため対象外"
    elif bps is None: 
        note = "財務データ不足" # Infoが取れなかった場合ここに来る
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
    
    # その他の指標
    pbr = (price / bps) if (price and bps and bps > 0) else None
    volume_ratio = (current_volume / avg_volume) if (avg_volume and avg_volume > 0) else 0
    big_prob = _calc_big_player_score(market_cap, pbr, volume_ratio)
    
    weather = _get_weather_icon(roe, roa)
    
    div_rate = None
    raw_div = info.get("dividendRate")
    if raw_div is not None and price and price > 0:
        div_rate = (raw_div / price) * 100.0

    rev_growth = _safe_float(info.get("revenueGrowth"), None)
    if rev_growth: rev_growth *= 100.0
    
    upside_pct = None
    if price and fair_value:
            upside_pct = round((fair_value / price - 1.0) * 100.0, 2)

    return {
        "code": code4, "name": name, "weather": weather, "price": price,
        "fair_value": fair_value, "upside_pct": upside_pct, "note": note, 
        "dividend": div_rate, "dividend_amount": raw_div,
        "growth": rev_growth, "market_cap": market_cap, "big_prob": big_prob,
        "signal_icon": signal_icon,
        "volume_wall": volume_wall # ここが絶対に返るようになる
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

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

def _calc_volume_profile_wall(hist, current_price, bins=50):
    """
    需給の壁（価格帯別出来高）を計算
    """
    try:
        if hist is None or hist.empty: return "—"
        
        # データコピー
        df = hist.copy()
        
        # 最低限のデータチェック
        if len(df) < 3: return "データ不足"

        # 価格帯ビンの作成
        if df['Close'].max() == df['Close'].min():
             return "値動きなし"

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
            
        # 3%ルール判定
        if upper_wall and (upper_wall - current_price) / current_price <= 0.03:
             return f"🔥上壁激戦中 ({upper_wall:,.0f}円)"
             
        if lower_wall and (current_price - lower_wall) / current_price <= 0.03:
             return f"⚠️下壁激戦中 ({lower_wall:,.0f}円)"
        
        u_text = f"🚧上 {upper_wall:,.0f}円" if upper_wall else "🟦青天井"
        l_text = f"🛡️下 {lower_wall:,.0f}円" if lower_wall else "🕳️底なし"
        
        return f"{u_text} / {l_text}"

    except Exception:
        return "計算エラー"

def _fetch_single_stock(code4: str) -> dict:
    # ★固定で3秒待つ（安定重視）
    time.sleep(3.0)

    ticker = f"{code4}.T"
    
    # === STEP 1: 株価データ取得 ===
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="6mo")
        
        # 6ヶ月がダメなら1ヶ月で再トライ
        if hist.empty:
            time.sleep(1)
            hist = t.history(period="1mo")
            
    except Exception:
        hist = None

    # 株価が取れなかったら即終了（これは本当に存在しないか通信エラー）
    if hist is None or hist.empty:
        return {
            "code": code4, "name": "取得失敗", "weather": "—", "price": None, 
            "fair_value": None, "upside_pct": None, "note": "アクセス不可", 
            "dividend": None, "dividend_amount": None, "growth": None, 
            "market_cap": None, "big_prob": None,
            "signal_icon": "—", "volume_wall": "—"
        }

    # === STEP 2: テクニカル指標の計算 ===
    # ここはデータがある限り計算する
    price = _safe_float(hist["Close"].iloc[-1], 0)
    current_volume = _safe_float(hist["Volume"].iloc[-1], 0)
    
    # 需給の壁
    volume_wall = _calc_volume_profile_wall(hist, price)

    # シグナル（簡易版）
    signal_icon = "—"
    try:
        if len(hist) > 25:
            # RSI計算
            delta = hist["Close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            rsi_val = rsi.iloc[-1]
            
            # ボリンジャーバンド
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

    # === STEP 3: 財務データ取得（失敗してもOK） ===
    info = {}
    try:
        info = t.info
    except:
        pass # 取れなくてもエラーにしない

    # 各種データの取り出し（なければNone）
    name = info.get("longName", info.get("shortName", f"({code4})"))
    
    # 業績
    roe = _safe_float(info.get("returnOnEquity"), None)
    roa = _safe_float(info.get("returnOnAssets"), None)
    weather = "☁（普通）"
    if roe is not None and roe < 0: weather = "☔（赤字）"
    if roe is not None and roe >= 0.08 and roa is not None and roa >= 0.05: weather = "☀（優良）"

    # グレアム数計算
    eps = _safe_float(info.get("trailingEps"), info.get("forwardEps", None))
    bps = _safe_float(info.get("bookValue"), None)
    
    fair_value = None
    note = "OK"
    
    if bps is None:
        note = "財務データなし"
    elif eps is None or eps < 0:
        note = "赤字/算出不可"
    else:
        try:
            val = 22.5 * eps * bps
            if val > 0:
                fair_value = round(math.sqrt(val), 0)
                note = f"EPS{eps:.1f}×BPS{bps:.0f}"
        except:
            note = "計算エラー"

    upside_pct = None
    if fair_value and price:
        upside_pct = round((fair_value / price - 1) * 100, 2)

    # 配当など
    div_rate = None
    raw_div = info.get("dividendRate")
    if raw_div and price: div_rate = (raw_div / price) * 100
    
    growth = _safe_float(info.get("revenueGrowth"), None)
    if growth: growth *= 100
    
    mcap = _safe_float(info.get("marketCap"), None)
    
    # 大口期待度（簡易）
    big_prob = 0
    if mcap:
        oku = mcap / 100000000
        if 500 <= oku <= 3000: big_prob = 60
    
    return {
        "code": code4, "name": name, "weather": weather, "price": price,
        "fair_value": fair_value, "upside_pct": upside_pct, "note": note, 
        "dividend": div_rate, "dividend_amount": raw_div,
        "growth": growth, "market_cap": mcap, "big_prob": big_prob,
        "signal_icon": signal_icon,
        "volume_wall": volume_wall
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

import re
import math
import unicodedata
from typing import Any, Dict, List, Optional
import pandas as pd
import streamlit as st
import fair_value_calc_y4 as fv  # 計算エンジン読み込み

# -----------------------------
# UI設定（デザイン）
# -----------------------------
st.set_page_config(page_title="フヤセルブレイン - AI理論株価分析ツール", page_icon="📈", layout="wide")

# CSSでデザインを整える
hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stDeployButton {display:none;}
            
            /* カード風デザイン */
            div.stButton > button:first-child {
                background-color: #ff4b4b;
                color: white;
                font-weight: bold;
                border-radius: 12px;
                border: none;
                padding: 0.8rem 2rem;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }
            div.stButton > button:hover {
                background-color: #e63e3e;
            }
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# -----------------------------
# 関数群
# -----------------------------
def sanitize_codes(raw_codes: List[str]) -> List[str]:
    """全角数字を半角に直し、コードを抽出する"""
    cleaned: List[str] = []
    for x in raw_codes:
        if x is None: continue
        s = str(x).strip()
        s = unicodedata.normalize('NFKC', s) # ７７７７ -> 7777
        s = s.upper().replace(" ", "").replace(",", "")
        if not s: continue
        m = re.search(r"[0-9A-Z]{4}", s)
        if m:
            s = m.group(0)
            cleaned.append(s)
    
    uniq: List[str] = []
    for c in cleaned:
        if c not in uniq: uniq.append(c)
    return uniq

def fmt_yen(x: Any) -> str:
    if x is None: return "—"
    try:
        v = float(x)
        if math.isnan(v): return "—"
        return f"{v:,.0f} 円"
    except: return "—"

def fmt_pct(x: Any) -> str:
    if x is None: return "—"
    try:
        v = float(x)
        if math.isnan(v): return "—"
        return f"{v:.2f}%"
    except: return "—"

def fmt_market_cap(x: Any) -> str:
    if x is None: return "—"
    try:
        v = float(x)
        if math.isnan(v): return "—"
        if v >= 100_000_000:
            return f"{v/100_000_000:.0f} 億円"
        return f"{v:,.0f} 円"
    except: return "—"

def fmt_big_prob(x: Any) -> str:
    if x is None: return "—"
    try:
        v = float(x)
        if v >= 80: return f"🔥 {v:.0f}%" 
        if v >= 60: return f"⚡ {v:.0f}%" 
        return f"{v:.0f}%"
    except: return "—"

def calc_rating(upside_pct: Optional[float]) -> str:
    if upside_pct is None: return "—"
    if upside_pct >= 50: return "★★★★★"
    if upside_pct >= 30: return "★★★★☆"
    if upside_pct >= 15: return "★★★☆☆"
    if upside_pct >= 5: return "★★☆☆☆"
    if upside_pct >= 0: return "★☆☆☆☆"
    return "☆☆☆☆☆"

def _as_float(x: Any) -> Optional[float]:
    try:
        if x is None: return None
        return float(x)
    except: return None

# -----------------------------
# メイン画面
# -----------------------------
st.title("📈 フヤセルブレイン")
st.caption("AI理論株価・大口介入スコア算出ツール")

with st.expander("★ 評価基準（AI自動判定）", expanded=True):
    st.markdown("""
    - :red[★★★★★：**お宝**（上昇余地 **+50%** 以上）]
    - ★★★★☆：**激アツ**（上昇余地 **+30%** 〜 +50%）
    - ★★★☆☆：**有望**（上昇余地 **+15%** 〜 +30%）
    """)

st.subheader("🔢 銘柄入力")
raw_text = st.text_area("分析したい証券コード（改行区切り）", height=100, placeholder="7777\n7203\n9984")
run_btn = st.button("🚀 AIで分析開始！")

st.divider()

if run_btn:
    raw_codes = raw_text.split()
    codes = sanitize_codes(raw_codes)
    if not codes:
        st.error("証券コードを入力してください")
        st.stop()

    with st.spinner("🚀 爆速で分析中..."):
        try:
            bundle = fv.calc_fuyaseru_bundle(codes)
        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
            st.stop()

    # データ整形
    data_list = []
    for code in codes:
        v = bundle.get(code, {})
        
        # 数値変換
        fair_val = _as_float(v.get("fair_value"))
        price = _as_float(v.get("price"))
        upside = _as_float(v.get("upside_pct"))
        
        # 上昇余地（円）
        upside_yen = "—"
        if fair_val and price:
            diff = fair_val - price
            upside_yen = f"+{diff:,.0f}円" if diff >=0 else f"▲{abs(diff):,.0f}円"

        data_list.append({
            "コード": code,
            "銘柄名": v.get("name", "取得失敗"),
            "現在値": fmt_yen(price),
            "理論株価": fmt_yen(fair_val),
            "上昇余地(%)": fmt_pct(upside),
            "上昇余地(円)": upside_yen,
            "評価": calc_rating(upside),
            "大口スコア": fmt_big_prob(v.get("big_prob")),
            "天気": v.get("weather", "—"),
            "時価総額": fmt_market_cap(v.get("market_cap")),
            "メモ": v.get("note", "—")
        })

    df = pd.DataFrame(data_list)
    
    # 表示
    st.subheader("📊 分析結果")
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    st.info("※ 7777（スリー・ディー・マトリックス）のような赤字企業は、理論株価が算出できないため「—」や「赤字」と表示されます。", icon="💡")

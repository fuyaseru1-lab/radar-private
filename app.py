import re
import math
import unicodedata
from typing import Any, Dict, List, Optional
import pandas as pd
import streamlit as st
import fair_value_calc_y4 as fv  # 計算エンジン読み込み

# -----------------------------
# UI設定
# -----------------------------
st.set_page_config(page_title="フヤセルブレイン - AI理論株価分析ツール", page_icon="📈", layout="wide")

hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stDeployButton {display:none;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# -----------------------------
# 関数群
# -----------------------------
def sanitize_codes(raw_codes: List[str]) -> List[str]:
    cleaned: List[str] = []
    for x in raw_codes:
        if x is None: continue
        s = str(x).strip()
        s = unicodedata.normalize('NFKC', s)
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
    except Exception: return "—"

def fmt_yen_diff(x: Any) -> str:
    if x is None: return "—"
    try:
        v = float(x)
        if math.isnan(v): return "—"
        if v >= 0: return f"+{v:,.0f} 円"
        else: return f"▲ {abs(v):,.0f} 円"
    except Exception: return "—"

def fmt_pct(x: Any) -> str:
    if x is None: return "—"
    try:
        v = float(x)
        if math.isnan(v): return "—"
        return f"{v:.2f}%"
    except Exception: return "—"

def fmt_market_cap(x: Any) -> str:
    if x is None: return "—"
    try:
        v = float(x)
        if math.isnan(v): return "—"
        if v >= 1_000_000_000_000:
            return f"{v/1_000_000_000_000:.2f} 兆円"
        elif v >= 100_000_000:
            return f"{v/100_000_000:.0f} 億円"
        else:
            return f"{v:,.0f} 円"
    except Exception: return "—"

def fmt_big_prob(x: Any) -> str:
    if x is None: return "—"
    try:
        v = float(x)
        if math.isnan(v): return "—"
        if v >= 80: return f"🔥 {v:.0f}%" 
        if v >= 60: return f"⚡ {v:.0f}%" 
        if v >= 40: return f"👀 {v:.0f}%" 
        return f"{v:.0f}%"
    except Exception: return "—"

def calc_rating_from_upside(upside_pct: Optional[float]) -> Optional[int]:
    if upside_pct is None: return None
    if upside_pct >= 50: return 5
    if upside_pct >= 30: return 4
    if upside_pct >= 15: return 3
    if upside_pct >= 5: return 2
    if upside_pct >= 0: return 1
    return 0

def to_stars(n: Optional[int]) -> str:
    if n is None: return "—"
    n = max(0, min(5, int(n)))
    return "★" * n + "☆" * (5 - n)

def _as_float(x: Any) -> Optional[float]:
    try:
        if x is None: return None
        v = float(x)
        if math.isnan(v): return None
        return v
    except Exception: return None

def highlight_errors(val):
    if val == "存在しない銘柄" or val == "エラー":
        return 'color: #ff4b4b; font-weight: bold;'
    return ''

def bundle_to_df(bundle: Any, codes: List[str]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    if isinstance(bundle, dict):
        for code in codes:
            v = bundle.get(code)
            if isinstance(v, dict):
                row = {"ticker": code, **v}
            else:
                row = {"ticker": code, "note": "形式エラー", "value": v}
            rows.append(row)
    else:
        rows.append({"ticker": ",".join(codes), "note": "エラー", "value": bundle})

    df = pd.DataFrame(rows)
    cols = ["name", "weather", "price", "fair_value", "upside_pct", "dividend", "growth", "market_cap", "big_prob", "note"]
    for col in cols:
        if col not in df.columns: df[col] = None

    df["price_num"] = df["price"].apply(_as_float)
    df["fair_value_num"] = df["fair_value"].apply(_as_float)
    df["upside_pct_num"] = df["upside_pct"].apply(_as_float)
    df["upside_yen_num"] = df["fair_value_num"] - df["price_num"]
    
    df["div_num"] = df["dividend"].apply(_as_float)
    df["growth_num"] = df["growth"].apply(_as_float)
    df["mc_num"] = df["market_cap"].apply(_as_float)
    df["prob_num"] = df["big_prob"].apply(_as_float)

    df["rating"] = df["upside_pct_num"].apply(calc_rating_from_upside)
    df["stars"] = df["rating"].apply(to_stars)

    df["証券コード"] = df["ticker"]
    df["銘柄名"] = df["name"].fillna("—")
    df["業績"] = df["weather"].fillna("—")
    
    df["現在値"] = df["price"].apply(fmt_yen)
    df["理論株価"] = df["fair_value"].apply(fmt_yen)
    df["上昇余地（円）"] = df["upside_yen_num"].apply(fmt_yen_diff)
    df["上昇余地（％）"] = df["upside_pct_num"].apply(fmt_pct)
    df["評価"] = df["stars"]
    
    df["配当利回り"] = df["div_num"].apply(fmt_pct)
    df["事業の勢い"] = df["growth_num"].apply(fmt_pct)
    
    df["時価総額"] = df["mc_num"].apply(fmt_market_cap)
    df["大口介入期待度"] = df["prob_num"].apply(fmt_big_prob)
    
    df["根拠【グレアム数】"] = df["note"].fillna("")
    df.index = df.index + 1

    show_cols = [
        "証券コード", "銘柄名", "現在値", "理論株価", 
        "上昇余地（％）", "評価", "配当利回り", "事業の勢い", 
        "業績", "時価総額", "大口介入期待度", "根拠【グレアム数】"
    ]
    return df[show_cols]

# -----------------------------
# メイン画面
# -----------------------------
st.title("📈 フヤセルブレイン - AI理論株価分析ツール")
st.caption("証券コードを入力すると、理論株価・配当・成長性・大口介入期待度を一括表示します。")

with st.expander("★ 評価基準（AI自動判定）", expanded=True):
    st.markdown("""
    - :red[★★★★★：**お宝**（上昇余地 **+50%** 以上）]
    - ★★★★☆：**激アツ**（上昇余地 **+30%** 〜 +50%）
    - ★★★☆☆：**有望**（上昇余地 **+15%** 〜 +30%）
    - ★★☆☆☆：**普通**（上昇余地 **+5%** 〜 +15%）
    - ★☆☆☆☆：**トントン**（上昇余地 **0%** 〜 +5%）
    - ☆☆☆☆☆：**割高**（上昇余地 **0% 未満**）
    """)

st.subheader("🔢 銘柄入力")
raw_text = st.text_area("分析したい証券コード（改行区切りで複数OK）", height=150, placeholder="7203\n8306\n9984")
run_btn = st.button("🚀 AIで分析開始！", type="primary")

st.divider()

if run_btn:
    raw_codes = raw_text.split()
    codes = sanitize_codes(raw_codes)
    if not codes:
        st.error("証券コードが入力されていません。")
        st.stop()

    with st.spinner("🚀 爆速で分析中..."):
        try:
            bundle = fv.calc_fuyaseru_bundle(codes)
        except Exception as e:
            st.error(f"エラー: {e}")
            st.stop()

    df = bundle_to_df(bundle, codes)
    st.subheader("📊 フヤセルブレイン分析結果")
    st.dataframe(df, use_container_width=True)
    
    st.info("※業績マーク：☀(優良)、☁(普通)、☔(赤字) ／ 成長性：売上高成長率", icon="ℹ️")

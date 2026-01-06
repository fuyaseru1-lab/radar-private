import re
import math
import unicodedata
from typing import Any, Dict, List, Optional
import pandas as pd
import streamlit as st
import fair_value_calc_y4 as fv # 計算エンジン読み込み

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
            
            /* フヤセル風ボタン */
            div.stButton > button:first-child {
                background-color: #ff4b4b;
                color: white;
                font-weight: bold;
                border-radius: 12px;
                border: none;
                padding: 0.5rem 1rem;
                width: 100%;
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
    cleaned: List[str] = []
    for x in raw_codes:
        if x is None: continue
        s = str(x).strip()
        s = unicodedata.normalize('NFKC', s)
        s = s.upper().replace(" ", "").replace(",", "")
        if not s: continue
        m = re.search(r"[0-9A-Z]{4}", s)
        if m:
            cleaned.append(m.group(0))
            
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

def fmt_yen_diff(x: Any) -> str:
    if x is None: return "—"
    try:
        v = float(x)
        if math.isnan(v): return "—"
        if v >= 0: return f"+{v:,.0f} 円"
        else: return f"▲ {abs(v):,.0f} 円"
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
        if v >= 1_000_000_000_000:
            return f"{v/1_000_000_000_000:.2f} 兆円"
        elif v >= 100_000_000:
            return f"{v/100_000_000:.0f} 億円"
        else:
            return f"{v:,.0f} 円"
    except: return "—"

def fmt_big_prob(x: Any) -> str:
    if x is None: return "—"
    try:
        v = float(x)
        if math.isnan(v): return "—"
        if v >= 80: return f"🔥 {v:.0f}%" 
        if v >= 60: return f"⚡ {v:.0f}%" 
        if v >= 40: return f"👀 {v:.0f}%" 
        return f"{v:.0f}%"
    except: return "—"

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
    except: return None

def highlight_errors(val):
    if val == "存在しない銘柄" or val == "エラー":
        return 'color: #ff4b4b; font-weight: bold;'
    return ''

# -----------------------------
# データ整形
# -----------------------------
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
        "証券コード", "銘柄名", 
        "現在値", "理論株価", 
        "上昇余地（％）", "評価", 
        "配当利回り", "事業の勢い", 
        "業績", 
        "時価総額", "大口介入期待度", 
        "根拠【グレアム数】"
    ]
    return df[show_cols]


# -----------------------------
# メイン画面
# -----------------------------
st.title("📈 フヤセルブレイン - AI理論株価分析ツール")
st.caption("証券コードを入力すると、理論株価・配当・成長性・大口介入期待度を一括表示します。")

with st.expander("★ 評価基準（AI自動判定）", expanded=True):
    st.markdown(
        """
評価（★）は **上昇余地%** を基準にしています。

- :red[★★★★★：**お宝**（上昇余地 **+50%** 以上）]
- ★★★★☆：**激アツ**（上昇余地 **+30%** 〜 +50%）
- ★★★☆☆：**有望**（上昇余地 **+15%** 〜 +30%）
- ★★☆☆☆：**普通**（上昇余地 **+5%** 〜 +15%）
- ★☆☆☆☆：**トントン**（上昇余地 **0%** 〜 +5%）
- ☆☆☆☆☆：**割高**（上昇余地 **0% 未満**）

※ 理論株価がマイナスの場合や取得できない場合は **評価不能（—）** になります。
"""
    )

st.subheader("🔢 銘柄入力")

raw_text = st.text_area(
    "分析したい証券コードを入力してください（複数可・改行区切り推奨）",
    height=150,
    placeholder="例：\n7203\n9984\n7777\n（Excelなどからコピペも可能です）"
)

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
            # ここで並列処理版のエンジンを呼び出す
            bundle = fv.calc_fuyaseru_bundle(codes)
        except Exception as e:
            st.error(f"計算でエラー：{e}")
            st.stop()

    df = bundle_to_df(bundle, codes)

    st.subheader("📊 フヤセルブレイン分析結果")
    
    styled_df = df.style.map(highlight_errors, subset=["銘柄名"])
    st.dataframe(styled_df, use_container_width=True)

    info_text = (
        "**※ 評価が表示されない（—）銘柄について**\n\n"
        "赤字決算や財務データが不足している銘柄（例：7777など）は、\n\n"
        "投資リスクの観点から自動的に **「評価対象外」** となる場合があります。\n\n"
        "---\n\n"
        "**※ 業績（お天気マーク）の判定基準**\n\n"
        "☀ **（優良）**：ROE 8%以上 **かつ** ROA 5%以上\n\n"
        "☁ **（普通）**：黒字だが、優良基準には満たない\n\n"
        "☔ **（赤字）**：ROE マイナス（赤字決算）"
    )
    st.info(info_text, icon="ℹ️")

    with st.expander("📚 【豆知識】理論株価の計算根拠（グレアム数）とは？"):
        st.markdown(
            """
            ### 🧙‍♂️ "投資の神様"の師匠が考案した「割安株」の黄金式
            
            このツールで算出している理論株価は、**「グレアム数」** をベースにしています。
            ベンジャミン・グレアムが考案した由緒ある指標です。
            
            > **今の株価 ＜ 理論株価（グレアム数）**
            
            となっていれば、それは **「実力よりも過小評価されている」** という強力なサインになります。
            """
        )

    with st.expander("🚀 【注目】なぜ「事業の勢い（売上成長率）」を見るの？"):
        st.markdown(
            """
            ### 📈 株価を押し上げる"真のエンジン"は売上にあり！
            
            - **🚀 +30% 以上**： **【超・急成長】**
            - **🏃 +10% 〜 +30%**： **【成長軌道】**
            - **🚶 0% 〜 +10%**： **【安定・成熟】**
            - **📉 マイナス**： **【衰退・縮小】**
            """
        )

    with st.expander("🌊 ファンドや機関（大口）の\"動き\"を検知する先乗り指標"):
        st.markdown(
            """
            時価総額や出来高の異常検知を組み合わせ、**「大口投資家が仕掛けやすい条件」** が揃っているかを%で表示します。
            
            #### 🎯 ゴールデンゾーン（時価総額 500億〜3000億円）
            機関投資家等が一番動きやすく、TOB（買収）のターゲットにもなりやすい規模感。
            
            #### ⚡ 出来高急増（ボリュームスパイク）
            今日の出来高が、普段の平均より2倍以上ある場合、裏で何かが起きている可能性があります。
            """
        )

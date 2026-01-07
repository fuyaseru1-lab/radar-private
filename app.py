import re
import math
import unicodedata
import time
from typing import Any, Dict, List, Optional
import pandas as pd
import streamlit as st
import fair_value_calc_y4 as fv

# ==========================================
# 🔑 パスワード設定
# ==========================================
USER_PASSWORD = "7777"
ADMIN_PASSWORD = "77777"
# ==========================================

st.set_page_config(page_title="フヤセルブレイン - シンプル版", page_icon="📈", layout="wide")

hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stDeployButton {display:none;}
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
# 🔐 認証
# -----------------------------
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    st.markdown("## 🔒 ACCESS RESTRICTED")
    pwd = st.text_input("パスワード", type="password")
    if st.button("ログイン"):
        if pwd == USER_PASSWORD:
            st.session_state["logged_in"] = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    st.stop()

# -----------------------------
# 関数群
# -----------------------------
def sanitize_codes(raw_codes: List[str]) -> List[str]:
    cleaned: List[str] = []
    for x in raw_codes:
        if x is None: continue
        s = str(x).strip().upper().replace(" ", "").replace(",", "")
        if not s: continue
        m = re.search(r"[0-9A-Z]{4}", s)
        if m:
            cleaned.append(m.group(0))
    return list(set(cleaned))

def fmt_yen(x): return f"{float(x):,.0f} 円" if x and x > 0 else "—"
def fmt_pct(x): return f"{float(x):.2f}%" if x is not None else "—"

def bundle_to_df(bundle, codes):
    rows = []
    for code in codes:
        v = bundle.get(code)
        if v:
            rows.append({"ticker": code, **v})
        else:
            rows.append({"ticker": code, "name": "読込失敗", "price": None})
            
    df = pd.DataFrame(rows)
    
    # 表示用データ作成
    display_rows = []
    for _, row in df.iterrows():
        # 金額系のフォーマット
        price_str = fmt_yen(row.get("price"))
        fair_str = fmt_yen(row.get("fair_value"))
        
        # 評価（★）
        upside = row.get("upside_pct")
        stars = "—"
        if upside is not None:
            if upside >= 50: stars = "★★★★★"
            elif upside >= 30: stars = "★★★★☆"
            elif upside >= 15: stars = "★★★☆☆"
            elif upside >= 5: stars = "★★☆☆☆"
            elif upside >= 0: stars = "★☆☆☆☆"
            else: stars = "☆☆☆☆☆"

        display_rows.append({
            "証券コード": row.get("ticker"),
            "銘柄名": row.get("name", "—"),
            "現在値": price_str,
            "理論株価": fair_str,
            "上昇余地": fmt_pct(upside),
            "評価": stars,
            "シグナル": row.get("signal_icon", "—"),
            "需給の壁": row.get("volume_wall", "—"),
            "業績": row.get("weather", "—"),
            "時価総額": f"{row.get('market_cap', 0)/100000000:,.0f} 億円" if row.get('market_cap') else "—",
            "備考": row.get("note", "")
        })
        
    return pd.DataFrame(display_rows)

# -----------------------------
# メイン画面
# -----------------------------
st.title("📈 フヤセルブレイン - シンプル版")

with st.expander("ℹ️ 評価の見方・壁の説明"):
    st.markdown("""
    * **🚧 上値壁**: ここを超えると青天井（買い）
    * **🛡️ 下値壁**: ここを割ると底なし（売り）
    * **🔥 激戦中**: まさに今、壁を突破するかどうかの瀬戸際！
    """)

raw_text = st.text_area("証券コード（複数可）", height=150, placeholder="7203\n9984")
run_btn = st.button("🚀 分析開始", type="primary")

if run_btn:
    codes = sanitize_codes(raw_text.split())
    if not codes:
        st.error("コードを入力してください")
        st.stop()
        
    with st.spinner("データを取得中...（安定のため3秒/件かかります）"):
        bundle = fv.calc_fuyaseru_bundle(codes)
        
    df = bundle_to_df(bundle, codes)
    st.dataframe(df, use_container_width=True)

st.divider()
with st.expander("🔧 管理者メニュー"):
    pwd = st.text_input("管理者パスワード", type="password")
    if pwd == ADMIN_PASSWORD:
        if st.button("キャッシュ削除"):
            st.cache_data.clear()
            st.success("削除しました。リロードします。")
            time.sleep(1)
            st.rerun()

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

st.set_page_config(page_title="フヤセルブレイン - 完全版", page_icon="📈", layout="wide")

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
def fmt_prob(x): 
    if x is None: return "—"
    if x >= 80: return f"🔥 {x:.0f}%"
    if x >= 60: return f"⚡ {x:.0f}%"
    if x >= 40: return f"👀 {x:.0f}%"
    return f"{x:.0f}%"

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
            "上昇余地(%)": fmt_pct(upside),
            "評価": stars,
            "今買いか？": row.get("signal_icon", "—"),
            "需給の壁 (価格帯別出来高)": row.get("volume_wall", "—"),
            "配当利回り": fmt_pct(row.get("dividend")),
            "年間配当": fmt_yen(row.get("dividend_amount")),
            "事業の勢い": fmt_pct(row.get("growth")),
            "業績": row.get("weather", "—"),
            "時価総額": f"{row.get('market_cap', 0)/100000000:,.0f} 億円" if row.get('market_cap') else "—",
            "大口介入期待度": fmt_prob(row.get("big_prob")),
            "根拠【グレアム数】": row.get("note", "")
        })
        
    return pd.DataFrame(display_rows)

# -----------------------------
# メイン画面
# -----------------------------
st.title("📈 フヤセルブレイン - 完全版")

with st.expander("★ 評価基準とアイコンの見方（クリックで詳細を表示）", expanded=False):
    st.markdown("""
### 1. 割安度評価（★）
**理論株価**（本来の実力）と **現在値** を比較した「お得度」です。
- :red[★★★★★：**お宝**（上昇余地 **+50%** 以上）]
- ★★★★☆：**激アツ**（上昇余地 **+30%** 〜 +50%）
- ★★★☆☆：**有望**（上昇余地 **+15%** 〜 +30%）
- ★★☆☆☆：**普通**（上昇余地 **+5%** 〜 +15%）
- ★☆☆☆☆：**トントン**（上昇余地 **0%** 〜 +5%）
- ☆☆☆☆☆：**割高**（上昇余地 **0% 未満**）

---

### 2. 売買シグナル（矢印）
**テクニカル指標** を複合分析した「売買タイミング」です。
| 表示 | 意味 | 判定ロジック |
| :--- | :--- | :--- |
| **↑◎** | **激熱** | **「底値圏」＋「売られすぎ」＋「上昇トレンド」** 等の好条件が3つ以上重なった最強の買い場！ |
| **↗〇** | **買い** | 複数のプラス要素あり。打診買いのチャンス。 |
| **→△** | **様子見** | 可もなく不可もなく。方向感が出るまで待つのが無難。 |
| **↘▲** | **売り** | 天井圏や下落トレンド入り。利益確定や損切りの検討を。 |
| **↓✖** | **危険** | **「買われすぎ」＋「暴落シグナル」** 等が点灯。手を出してはいけない。 |

---

### 3. 需給の壁（突破力） ※価格帯別出来高
**過去6ヶ月間で、注文が溜まっていて「壁」となっている価格帯**です。

* **🚧 上値壁（〇〇円）**
    * **【基本】** ここは売りたい人が多いため、**株価が上がっても跳ね返されやすい（下落しやすい）** 場所です。
    * **【突破】** しかし、ここを食い破れば売り手不在の**「青天井」**モード突入！一気に上昇するチャンスです。
* **🛡️ 下値壁（〇〇円）**
    * **【基本】** ここは買いたい人が多いため、**株価が下がっても支えられやすい（反発しやすい）** 場所です。
    * **【割込】** しかし、ここを割り込むと全員が含み損になり**「パニック売り」**が連鎖する恐れあり。即逃げ推奨です。
* **⚔️ 激戦中**
    * まさに今、その壁の価格帯で攻防戦が行われています。突破するか跳ね返されるか、運命の分かれ道です。
""", unsafe_allow_html=True) 

raw_text = st.text_area("分析したい証券コードを入力してください（複数可・改行区切り推奨）", height=150, placeholder="例：\n7203\n9984\n285A")
run_btn = st.button("🚀 AIで分析開始！", type="primary")

if run_btn:
    codes = sanitize_codes(raw_text.split())
    if not codes:
        st.error("証券コードが入力されていません。")
        st.stop()
        
    with st.spinner("🚀 爆速で分析中...（安定のため3秒/件かかります）"):
        bundle = fv.calc_fuyaseru_bundle(codes)
        
    df = bundle_to_df(bundle, codes)
    st.subheader("📊 フヤセルブレイン分析結果")
    st.dataframe(df, use_container_width=True)
    st.info("**※ 評価が表示されない銘柄について**\n赤字決算や財務データ不足の銘柄は自動的に「評価対象外」としています。ただし来期黒字予想がある場合は「※予想EPS参照」として計算しています。", icon="ℹ️")

st.divider()
with st.expander("🔧 管理者メニュー"):
    st.write("キャッシュ削除機能などを使用するには管理者パスワードが必要です。")
    pwd = st.text_input("管理者パスワード", type="password")
    if pwd == ADMIN_PASSWORD:
        if st.button("🗑️ キャッシュを全削除してリセット", type="secondary"):
            st.cache_data.clear()
            st.success("キャッシュを削除しました！リロードします...")
            time.sleep(1)
            st.rerun()

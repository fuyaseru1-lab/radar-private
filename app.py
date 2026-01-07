import re
import math
import unicodedata
import time
from typing import Any, Dict, List, Optional
import pandas as pd
import streamlit as st
import fair_value_calc_y4 as fv  # 計算エンジン

# ==========================================
# 🔑 パスワード設定
# ==========================================
USER_PASSWORD = "7777"       # ログイン用パスワード
ADMIN_PASSWORD = "77777"     # 管理者メニュー用パスワード
# ==========================================

st.set_page_config(page_title="フヤセルブレイン - AI理論株価分析ツール", page_icon="📈", layout="wide")

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
            details {
                background-color: #f9f9f9;
                padding: 10px;
                border-radius: 5px;
                border: 1px solid #eee;
                margin-top: 10px;
                margin-bottom: 20px;
            }
            summary {
                cursor: pointer;
                font-weight: bold;
                color: #31333F;
            }
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# -----------------------------
# 🔐 認証ロジック
# -----------------------------
def check_password():
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if not st.session_state["logged_in"]:
        st.markdown("## 🔒 ACCESS RESTRICTED")
        st.caption("関係者専用ツールのため、パスワード制限をかけています。")
        password_input = st.text_input("パスワードを入力してください", type="password")
        if st.button("ログイン"):
            input_norm = unicodedata.normalize('NFKC', password_input).upper().strip()
            secret_norm = unicodedata.normalize('NFKC', USER_PASSWORD).upper().strip()
            if input_norm == secret_norm:
                st.session_state["logged_in"] = True
                st.rerun()
            else:
                st.error("パスワードが違います 🙅")
        st.stop()

check_password()

# ==========================================
# メインアプリ本体
# ==========================================

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
    cols = ["name", "weather", "price", "fair_value", "upside_pct", "dividend", "dividend_amount", "growth", "market_cap", "big_prob", "note", "signal_icon", "volume_wall"]
    for col in cols:
        if col not in df.columns: df[col] = None

    df["price_num"] = df["price"].apply(_as_float)
    df["fair_value_num"] = df["fair_value"].apply(_as_float)
    df["upside_pct_num"] = df["upside_pct"].apply(_as_float)
    df["upside_yen_num"] = df["fair_value_num"] - df["price_num"]
    df["div_num"] = df["dividend"].apply(_as_float)
    df["div_amount_num"] = df["dividend_amount"].apply(_as_float)
    df["growth_num"] = df["growth"].apply(_as_float)
    df["mc_num"] = df["market_cap"].apply(_as_float)
    df["prob_num"] = df["big_prob"].apply(_as_float)
    df["rating"] = df["upside_pct_num"].apply(calc_rating_from_upside)
    df["stars"] = df["rating"].apply(to_stars)
    
    df.loc[df["name"] == "存在しない銘柄", "stars"] = "—"

    df["証券コード"] = df["ticker"]
    df["銘柄名"] = df["name"].fillna("—")
    df["業績"] = df["weather"].fillna("—")
    df["現在値"] = df["price"].apply(fmt_yen)
    df["理論株価"] = df["fair_value"].apply(fmt_yen)
    df["上昇余地（円）"] = df["upside_yen_num"].apply(fmt_yen_diff)
    df["上昇余地（％）"] = df["upside_pct_num"].apply(fmt_pct)
    df["評価"] = df["stars"]
    df["今買いか？"] = df["signal_icon"].fillna("—")
    df["需給の壁（価格帯別出来高）"] = df["volume_wall"].fillna("—")

    df["配当利回り"] = df["div_num"].apply(fmt_pct)
    df["年間配当"] = df["div_amount_num"].apply(fmt_yen)
    df["事業の勢い"] = df["growth_num"].apply(fmt_pct)
    df["時価総額"] = df["mc_num"].apply(fmt_market_cap)
    df["大口介入期待度"] = df["prob_num"].apply(fmt_big_prob)
    df["根拠【グレアム数】"] = df["note"].fillna("")

    df.index = df.index + 1
    
    show_cols = [
        "証券コード", "銘柄名", "現在値", "理論株価", "上昇余地（％）", "評価", "今買いか？", "需給の壁（価格帯別出来高）",
        "配当利回り", "年間配当", "事業の勢い", "業績", "時価総額", "大口介入期待度", "根拠【グレアム数】"
    ]
    return df[show_cols]

st.title("📈 フヤセルブレイン - AI理論株価分析ツール")
st.caption("証券コードを入力すると、理論株価・配当・成長性・大口介入期待度を一括表示します。")

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

<details><summary>🤔 「割高」判定ばかり出る…という方へ</summary>
<br><span style="color: #ff4b4b; font-weight: bold;">※ 割高だから悪いというわけではありません。</span><br>
むしろ優秀な企業だから株価が理論値をはるかに上回っている可能性もあります。
</details>

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

### 3. 需給の壁（突破力）
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

st.subheader("🔢 銘柄入力")
raw_text = st.text_area("分析したい証券コードを入力してください（複数可・改行区切り推奨）", height=150, placeholder="例：\n7203\n9984\n285A")
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
    styled_df = df.style.map(highlight_errors, subset=["銘柄名"])
    st.dataframe(styled_df, use_container_width=True)
    st.info("**※ 評価が表示されない銘柄について**\n赤字決算や財務データ不足の銘柄は自動的に「評価対象外」としています。ただし来期黒字予想がある場合は「※予想EPS参照」として計算しています。", icon="ℹ️")

st.divider()

with st.expander("🔧 管理者用メニュー"):
    st.write("キャッシュ削除機能などを使用するには管理者パスワードが必要です。")
    admin_input = st.text_input("管理者パスワードを入力", type="password", key="admin_pass")
    if admin_input:
        input_norm = unicodedata.normalize('NFKC', admin_input).upper().strip()
        secret_norm = unicodedata.normalize('NFKC', ADMIN_PASSWORD).upper().strip()
        if input_norm == secret_norm:
            st.success("認証成功：管理者権限が有効です")
            if st.button("🗑️ キャッシュを全削除してリセット", type="secondary"):
                st.cache_data.clear()
                st.success("キャッシュを削除しました！リロードします...")
                time.sleep(1)
                st.rerun()
        else:
            st.error("パスワードが違います")

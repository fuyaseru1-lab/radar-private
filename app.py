import re
import math
import unicodedata
import time
from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np
import streamlit as st
import fair_value_calc_y4 as fv  # 計算エンジン
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==========================================
# 🔑 パスワード設定（Secretsから読み込む安全仕様）
# ==========================================
try:
    LOGIN_PASSWORD = st.secrets["LOGIN_PASSWORD"]
    ADMIN_CODE = st.secrets["ADMIN_CODE"]
except Exception:
    st.error("❌ システムエラー：パスワード設定（Secrets）が見つかりません。")
    st.info("Streamlit Cloudの [Settings] > [Secrets] にパスワードを設定してください。")
    st.stop()
# ==========================================

# -----------------------------
# UI設定
# -----------------------------
st.set_page_config(page_title="フヤセルブレイン - AI理論株価分析ツール", page_icon="📈", layout="wide")

# ★スマホ対応：文字色強制ブラック＆チャート調整CSS
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
            
            /* ★スマホのダークモード対策：強制的に文字を濃い色にする */
            html, body, p, h1, h2, h3, h4, h5, h6, li, span, div {
                color: #31333F !important;
            }
            /* 背景も白系に固定 */
            .stApp {
                background-color: #ffffff;
            }
            /* 入力ボックス内の文字色も見やすく */
            .stTextInput input, .stTextArea textarea {
                color: #31333F !important;
            }
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# -----------------------------
# 🔐 認証
# -----------------------------
def check_password():
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if not st.session_state["logged_in"]:
        st.markdown("## 🔒 ACCESS RESTRICTED")
        password_input = st.text_input("パスワードを入力してください", type="password")
        if st.button("ログイン"):
            input_norm = unicodedata.normalize('NFKC', password_input).upper().strip()
            secret_norm = unicodedata.normalize('NFKC', LOGIN_PASSWORD).upper().strip()
            if input_norm == secret_norm:
                st.session_state["logged_in"] = True
                st.rerun()
            else:
                st.error("パスワードが違います 🙅")
        st.stop()

check_password()

# -----------------------------
# 📈 チャート描画関数（Plotly）
# -----------------------------
def draw_wall_chart(ticker_data: Dict[str, Any]):
    hist = ticker_data.get("hist_data")
    if hist is None or hist.empty:
        st.warning("チャートデータがありません（取得失敗）")
        return

    name = ticker_data.get("name", "Unknown")
    code = ticker_data.get("code", "----")
    current_price = ticker_data.get("price", 0)
    fair_value = ticker_data.get("fair_value")

    # データ整理
    hist = hist.reset_index()
    hist['Date'] = pd.to_datetime(hist.iloc[:, 0]).dt.tz_localize(None) # タイムゾーン削除

    # 需給の壁データ作成
    bins = 50
    p_min = min(hist['Close'].min(), current_price * 0.9)
    p_max = max(hist['Close'].max(), current_price * 1.1)
    bin_edges = np.linspace(p_min, p_max, bins)
    hist['bin'] = pd.cut(hist['Close'], bins=bin_edges)
    vol_profile = hist.groupby('bin', observed=False)['Volume'].sum()
    
    # 壁の色分け
    bar_colors = []
    for interval in vol_profile.index:
        if interval.mid > current_price:
            bar_colors.append('rgba(255, 82, 82, 0.6)')  # 赤（上値）
        else:
            bar_colors.append('rgba(33, 150, 243, 0.6)') # 青（下値）

    # サブプロット作成
    fig = make_subplots(
        rows=1, cols=2, 
        shared_yaxes=True, 
        column_widths=[0.75, 0.25],
        horizontal_spacing=0.02
    )

    # 1. ローソク足
    fig.add_trace(go.Candlestick(
        x=hist['Date'],
        open=hist['Open'], high=hist['High'],
        low=hist['Low'], close=hist['Close'],
        name='株価'
    ), row=1, col=1)

    # 2. 壁（横棒グラフ）
    fig.add_trace(go.Bar(
        x=vol_profile.values,
        y=[i.mid for i in vol_profile.index],
        orientation='h',
        marker_color=bar_colors,
        name='出来高'
    ), row=1, col=2)

    # 3. 理論株価ライン
    if fair_value:
        fig.add_hline(y=fair_value, line_dash="dash", line_color="white", annotation_text="理論株価", annotation_position="top left")

    # レイアウト調整（★ここ重要：ドラッグ禁止設定）
    fig.update_layout(
        title=f"📊 {name} ({code})",
        height=450,
        showlegend=False,
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=40, b=10),
        dragmode=False,  # ★ドラッグ操作（拡大縮小）を無効化
    )
    
    # x軸・y軸の固定設定
    fig.update_xaxes(fixedrange=True) # ★X軸ズーム禁止
    fig.update_yaxes(fixedrange=True) # ★Y軸ズーム禁止

    # ★configでツールバーも非表示にして完全固定
    st.plotly_chart(
        fig, 
        use_container_width=True,
        config={
            'displayModeBar': False, # ツールバー消す
            'staticPlot': False,      # 静止画にはしない（ツールチップは見れるように）
            'scrollZoom': False       # スクロールズーム禁止
        }
    )


# ==========================================
# メイン処理
# ==========================================

# 関数群
def sanitize_codes(raw_codes: List[str]) -> List[str]:
    cleaned: List[str] = []
    for x in raw_codes:
        if x is None: continue
        s = str(x).strip()
        s = unicodedata.normalize('NFKC', s)
        s = s.upper().replace(" ", "").replace(",", "")
        if not s: continue
        m = re.search(r"[0-9A-Z]{4}", s)
        if m: cleaned.append(m.group(0))
    uniq: List[str] = []
    for c in cleaned:
        if c not in uniq: uniq.append(c)
    return uniq

def fmt_yen(x):
    try: return f"{float(x):,.0f} 円"
    except: return "—"
def fmt_yen_diff(x):
    try:
        v = float(x)
        return f"+{v:,.0f} 円" if v>=0 else f"▲ {abs(v):,.0f} 円"
    except: return "—"
def fmt_pct(x):
    try: return f"{float(x):.2f}%"
    except: return "—"
def fmt_market_cap(x):
    try:
        v = float(x)
        if v >= 1e12: return f"{v/1e12:.2f} 兆円"
        elif v >= 1e8: return f"{v/1e8:.0f} 億円"
        else: return f"{v:,.0f} 円"
    except: return "—"
def fmt_big_prob(x):
    try:
        v = float(x)
        if v >= 80: return f"🔥 {v:.0f}%" 
        if v >= 60: return f"⚡ {v:.0f}%" 
        if v >= 40: return f"👀 {v:.0f}%" 
        return f"{v:.0f}%"
    except: return "—"
def calc_rating_from_upside(upside_pct):
    if upside_pct is None: return 0
    if upside_pct >= 50: return 5
    if upside_pct >= 30: return 4
    if upside_pct >= 15: return 3
    if upside_pct >= 5: return 2
    if upside_pct >= 0: return 1
    return 0
def to_stars(n):
    n = max(0, min(5, int(n or 0)))
    return "★" * n + "☆" * (5 - n)
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

    # 数値化とフォーマット
    def _as_float(x):
        try: return float(x)
        except: return None
        
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
    
    # 詳細チェックボックス
    df["詳細"] = False
    
    show_cols = [
        "証券コード", "銘柄名", "現在値", "理論株価", "上昇余地（％）", "評価", "今買いか？", "需給の壁（価格帯別出来高）",
        "詳細", 
        "配当利回り", "年間配当", "事業の勢い", "業績", "時価総額", "大口介入期待度", "根拠【グレアム数】"
    ]
    return df[show_cols]


# -----------------------------
# メイン画面構築
# -----------------------------
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

### 2. 売買シグナル（矢印）
| 表示 | 意味 | 判定ロジック |
| :--- | :--- | :--- |
| **↑◎** | **激熱** | **「底値圏」＋「売られすぎ」＋「上昇トレンド」** 等の好条件が3つ以上重なった最強の買い場！ |
| **↗〇** | **買い** | 複数のプラス要素あり。打診買いのチャンス。 |
| **→△** | **様子見** | 可もなく不可もなく。方向感が出るまで待つのが無難。 |
| **↘▲** | **売り** | 天井圏や下落トレンド入り。利益確定や損切りの検討を。 |
| **↓✖** | **危険** | **「買われすぎ」＋「暴落シグナル」** 等が点灯。手を出してはいけない。 |

### 3. 需給の壁（突破力）
**過去6ヶ月間で最も取引が活発だった価格帯（しこり玉・岩盤）** です。
- **🚧 上壁（戻り売り圧力）**：ここまでは上がっても叩き落とされやすい（抵抗線）。突破すれば青天井！
- **🛡️ 下壁（押し目買い支持）**：ここで下げ止まって反発しやすい（支持線）。割るとパニック売り注意。
- **🔥 激戦中（分岐点）**：まさに今、その壁の中で戦っている。
""", unsafe_allow_html=True) 

st.subheader("🔢 銘柄入力")
raw_text = st.text_area(
    "分析したい証券コードを入力してください（複数可・改行区切り推奨）",
    height=150,
    placeholder="例：\n7203\n9984\n285A\n（Excelなどからコピペも可能です）"
)
run_btn = st.button("🚀 AIで分析開始！", type="primary")

st.divider()

if "analysis_bundle" not in st.session_state:
    st.session_state["analysis_bundle"] = None
if "analysis_codes" not in st.session_state:
    st.session_state["analysis_codes"] = []

if run_btn:
    raw_codes = raw_text.split()
    codes = sanitize_codes(raw_codes)
    if not codes:
        st.error("証券コードが入力されていません。")
        st.stop()

    with st.spinner(f"🚀 高速分析中...（1銘柄につき数3秒ほどお待ちください。アクセス集中時はリトライ実行）"):
        try:
            bundle = fv.calc_fuyaseru_bundle(codes)
            st.session_state["analysis_bundle"] = bundle
            st.session_state["analysis_codes"] = codes
        except Exception as e:
            st.error(f"エラー: {e}")
            st.stop()

# 分析結果があれば表示
if st.session_state["analysis_bundle"]:
    bundle = st.session_state["analysis_bundle"]
    codes = st.session_state["analysis_codes"]
    
    df = bundle_to_df(bundle, codes)
    
    st.subheader("📊 フヤセルブレイン分析結果")
    st.info("💡 **「詳細」** 列のチェックボックスをONにすると、下に詳細チャートが表示されます！")
    
    styled_df = df.style.map(highlight_errors, subset=["銘柄名"])
    
    # st.data_editor
    edited_df = st.data_editor(
        styled_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "詳細": st.column_config.CheckboxColumn(
                "詳細",
                help="チェックするとチャートを表示します",
                default=False,
            ),
            "証券コード": st.column_config.TextColumn(disabled=True),
            "銘柄名": st.column_config.TextColumn(disabled=True),
        },
        disabled=["証券コード", "銘柄名", "現在値", "理論株価", "上昇余地（％）", "評価", "今買いか？", "需給の壁（価格帯別出来高）", "配当利回り", "年間配当", "事業の勢い", "業績", "時価総額", "大口介入期待度", "根拠【グレアム数】"]
    )
    
    # チェックがついている行を探す
    selected_rows = edited_df[edited_df["詳細"] == True]
    
    if not selected_rows.empty:
        selected_code = selected_rows.iloc[0]["証券コード"]
        ticker_data = bundle.get(selected_code)
        
        st.divider()
        st.markdown(f"### 📉 詳細分析チャート：{ticker_data.get('name')}")
        draw_wall_chart(ticker_data)
        st.divider()

    st.info(
        "**※ 評価が表示されない（—）銘柄について**\n\n"
        "赤字決算や財務データが不足している銘柄は、投資リスクの観点から自動的に **「評価対象外」** としています。\n\n"
        "ただし、**「今は赤字だが来期は黒字予想」の場合は、自動的に『予想EPS』を使って理論株価を算出**しています。\n"
        "その場合、根拠欄に **「※予想EPS参照」** と記載されます。",
        icon="ℹ️"
    )

# -----------------------------
# 🔧 管理者メニュー（最下部）
# -----------------------------
st.divider()
with st.expander("🔧 管理者専用メニュー"):
    st.caption("関係者のみ操作可能です。")
    admin_input = st.text_input("管理者コード", type="password", key="admin_pass_bottom")
    if admin_input == ADMIN_CODE:
        st.success("認証OK：管理者権限")
        if st.button("🗑️ キャッシュ全削除", type="primary"):
            st.cache_data.clear()
            st.success("削除完了！再読み込みします...")
            time.sleep(1)
            st.rerun()

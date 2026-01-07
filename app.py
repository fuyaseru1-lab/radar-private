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
# 🔑 パスワード設定
# ==========================================
LOGIN_PASSWORD = "7777"
ADMIN_CODE = "77777"

# ==========================================
# UI設定
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
            
            /* 文字色を黒(#31333F)に固定 */
            .stApp, .stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown span, .stMarkdown div, .stDataFrame {
                color: #31333F !important;
                background-color: #ffffff !important;
            }
            div[data-testid="stAppViewContainer"] {
                background-color: #ffffff !important;
            }
            .stTextInput input, .stTextArea textarea {
                color: #31333F !important;
                background-color: #f0f2f6 !important;
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
# 📈 チャート描画関数（抵抗線ロジック実装済み）
# -----------------------------
def draw_wall_chart(ticker_data: Dict[str, Any]):
    hist = ticker_data.get("hist_data")
    if hist is None or hist.empty:
        st.warning("チャートデータがありません（取得失敗）")
        return

    name = ticker_data.get("name", "Unknown")
    code = ticker_data.get("code", "----")
    current_price = ticker_data.get("price", 0)

    hist = hist.reset_index()
    hist['Date'] = pd.to_datetime(hist.iloc[:, 0]).dt.tz_localize(None)

    # --- 1. 価格帯別出来高の集計 ---
    bins = 50
    p_min = min(hist['Close'].min(), current_price * 0.9)
    p_max = max(hist['Close'].max(), current_price * 1.1)
    bin_edges = np.linspace(p_min, p_max, bins)
    hist['bin'] = pd.cut(hist['Close'], bins=bin_edges)
    vol_profile = hist.groupby('bin', observed=False)['Volume'].sum()

    # --- 2. 抵抗線・支持線のロジック ---
    upper_candidates = []
    lower_candidates = []

    for interval, volume in vol_profile.items():
        mid_price = interval.mid
        if volume == 0: continue
        
        if mid_price > current_price:
            upper_candidates.append({'vol': volume, 'price': mid_price})
        else:
            lower_candidates.append({'vol': volume, 'price': mid_price})

    # 赤（上値抵抗線）：出来高最大 > 価格低い方
    if upper_candidates:
        best_red = sorted(upper_candidates, key=lambda x: (-x['vol'], x['price']))[0]
        resistance_price = best_red['price']
    else:
        resistance_price = hist['High'].max()

    # 青（下値抵抗線）：出来高最大 > 価格高い方
    if lower_candidates:
        best_blue = sorted(lower_candidates, key=lambda x: (-x['vol'], -x['price']))[0]
        support_price = best_blue['price']
    else:
        support_price = hist['Low'].min()

    # --- バーの色分け ---
    bar_colors = []
    for interval in vol_profile.index:
        if interval.mid > current_price:
            bar_colors.append('rgba(255, 82, 82, 0.4)')
        else:
            bar_colors.append('rgba(33, 150, 243, 0.4)')

    fig = make_subplots(
        rows=1, cols=2, 
        shared_yaxes=True, 
        column_widths=[0.75, 0.25], 
        horizontal_spacing=0.02,
        subplot_titles=("📉 トレンド分析", "🧱 需給の壁")
    )

    # 1. ローソク足
    fig.add_trace(go.Candlestick(
        x=hist['Date'], open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], 
        name='株価'
    ), row=1, col=1)

    # 2. 出来高プロファイル
    fig.add_trace(go.Bar(
        x=vol_profile.values, y=[i.mid for i in vol_profile.index], 
        orientation='h', marker_color=bar_colors, name='出来高'
    ), row=1, col=2)

    # --- ライン描画 ---
    fig.add_hline(
        y=resistance_price, 
        line_color="#ef4444", 
        line_width=2,
        annotation_text="🟥 上値抵抗線（抜ければ激アツ）", 
        annotation_position="top left",
        annotation_font_color="#ef4444",
        row=1, col=1
    )

    fig.add_hline(
        y=support_price, 
        line_color="#3b82f6", 
        line_width=2,
        annotation_text="🟦 下値抵抗線（割れれば即逃げ）", 
        annotation_position="bottom left",
        annotation_font_color="#3b82f6",
        row=1, col=1
    )

    fig.update_layout(
        title=f"📊 {name} ({code})", 
        height=450, 
        showlegend=False, 
        xaxis_rangeslider_visible=False, 
        margin=dict(l=10, r=10, t=60, b=10), 
        dragmode=False
    )
    fig.update_xaxes(fixedrange=True) 
    fig.update_yaxes(fixedrange=True)

    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False, 'staticPlot': False, 'scrollZoom': False})

# ==========================================
# メイン処理
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
        if m: cleaned.append(m.group(0))
    uniq: List[str] = []
    for c in cleaned:
        if c not in uniq: uniq.append(c)
    return uniq

# ★フォーマット関数
def fmt_yen(x):
    if x is None or pd.isna(x) or str(x).lower() == 'nan': return "—"
    try: return f"{float(x):,.0f} 円"
    except: return "—"
def fmt_pct(x):
    if x is None or pd.isna(x) or str(x).lower() == 'nan': return "—"
    try: return f"{float(x):.2f}%"
    except: return "—"
def fmt_market_cap(x):
    if x is None or pd.isna(x) or str(x).lower() == 'nan': return "—"
    try:
        v = float(x)
        if v >= 1e12: return f"{v/1e12:.2f} 兆円"
        elif v >= 1e8: return f"{v/1e8:.0f} 億円"
        else: return f"{v:,.0f} 円"
    except: return "—"
def fmt_big_prob(x):
    if x is None or pd.isna(x) or str(x).lower() == 'nan': return "—"
    try:
        v = float(x)
        if v >= 80: return f"🔥 {v:.0f}%" 
        if v >= 60: return f"⚡ {v:.0f}%" 
        if v >= 40: return f"👀 {v:.0f}%" 
        return f"{v:.0f}%"
    except: return "—"
def calc_rating_from_upside(upside_pct):
    if upside_pct is None or pd.isna(upside_pct): return 0
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

# ★ランク付け用のスコア計算関数
def calculate_score_and_rank(row):
    score = 0
    
    # 1. 上昇余地 (Max 40点)
    up = row.get('upside_pct_num', 0)
    if pd.isna(up): up = 0
    if up >= 50: score += 40
    elif up >= 30: score += 30
    elif up >= 15: score += 20
    elif up > 0: score += 10
    
    # 2. 大口介入 (Max 30点)
    prob = row.get('prob_num', 0)
    if pd.isna(prob): prob = 0
    if prob >= 80: score += 30
    elif prob >= 60: score += 20
    elif prob >= 40: score += 10
    
    # 3. 事業成長 (Max 20点)
    growth = row.get('growth_num', 0)
    if pd.isna(growth): growth = 0
    if growth >= 30: score += 20
    elif growth >= 10: score += 10
    
    # 4. 財務健全性 (Max 10点)
    weather = row.get('weather', '')
    if weather == '☀': score += 10
    elif weather == '☁': score += 5
    
    # ランク判定
    if score >= 95: return "SSS"
    if score >= 90: return "SS"
    if score >= 85: return "S"
    if score >= 75: return "A"
    if score >= 60: return "B"
    if score >= 45: return "C"
    if score >= 30: return "D"
    return "E"

def bundle_to_df(bundle: Any, codes: List[str]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    if isinstance(bundle, dict):
        for code in codes:
            v = bundle.get(code)
            if isinstance(v, dict):
                if v.get("note") == "データ取得不可(Yahoo拒否)" or v.get("name") == "エラー" or v.get("name") == "計算エラー":
                     v["name"] = "存在しない銘柄"
                     v["note"] = "—"
                     v["volume_wall"] = "—"
                     v["signal_icon"] = "—"
                     v["weather"] = "—"
                if v.get("note") == "ETF/REIT対象外":
                     v["note"] = "ETF/REITのため対象外"
                row = {"ticker": code, **v}
            else:
                row = {"ticker": code, "name": "存在しない銘柄", "note": "—", "value": v}
            rows.append(row)
    else:
        rows.append({"ticker": ",".join(codes), "name": "存在しない銘柄", "note": "—", "value": bundle})

    df = pd.DataFrame(rows)
    cols = ["name", "weather", "price", "fair_value", "upside_pct", "dividend", "dividend_amount", "growth", "market_cap", "big_prob", "note", "signal_icon", "volume_wall"]
    for col in cols:
        if col not in df.columns: df[col] = None

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
    
    # 星計算
    df["rating"] = df["upside_pct_num"].apply(calc_rating_from_upside)
    df["stars"] = df["rating"].apply(to_stars)
    
    # エラー処理
    error_mask = df["name"] == "存在しない銘柄"
    df.loc[error_mask, "stars"] = "—"
    df.loc[error_mask, "price"] = None
    df.loc[error_mask, "fair_value"] = None 
    df.loc[error_mask, "note"] = "—"

    # ★ランク計算実行
    df["ランク"] = df.apply(calculate_score_and_rank, axis=1)
    df.loc[error_mask, "ランク"] = "—"

    # カラム整理
    df["証券コード"] = df["ticker"]
    df["銘柄名"] = df["name"].fillna("—")
    df["業績"] = df["weather"].fillna("—")
    df["現在値"] = df["price"].apply(fmt_yen)
    df["理論株価"] = df["fair_value"].apply(fmt_yen)
    df["上昇余地"] = df["upside_pct_num"].apply(fmt_pct)
    df["評価"] = df["stars"]
    df["売買"] = df["signal_icon"].fillna("—")
    df["需給の壁"] = df["volume_wall"].fillna("—")
    df["配当利回り"] = df["div_num"].apply(fmt_pct)
    df["年間配当"] = df["div_amount_num"].apply(fmt_yen)
    df["事業の勢い"] = df["growth_num"].apply(fmt_pct)
    df["時価総額"] = df["mc_num"].apply(fmt_market_cap)
    df["大口介入"] = df["prob_num"].apply(fmt_big_prob)
    df["根拠"] = df["note"].fillna("—")

    df.index = df.index + 1
    df["詳細"] = False
    
    # ランクを一番左へ
    show_cols = [
        "ランク", "証券コード", "銘柄名", "現在値", "理論株価", "上昇余地", "評価", "売買", "需給の壁",
        "詳細", 
        "配当利回り", "年間配当", "事業の勢い", "業績", "時価総額", "大口介入", "根拠"
    ]
    
    return df[show_cols]

# ==========================================
# メイン画面構築
# ==========================================
st.title("📈 フヤセルブレイン - AI理論株価分析ツール")

with st.expander("★ ランク・評価基準の見方（クリックで詳細を表示）", expanded=False):
    st.markdown("""
### 👑 総合ランク（SSS〜E）
理論株価の上昇余地だけでなく、**「大口の動き」「事業の成長性」「財務の安全性」**を総合的にスコア化（100点満点）した格付けです。
- **SSS (95-100点)**：**神**。全ての条件が揃った奇跡の銘柄。
- **SS (90-94点)**：**最強**。ほぼ死角なし。
- **S (85-89点)**：**超優秀**。文句なしの買い候補。
- **A (75-84点)**：**優良**。合格点。
- **B (60-74点)**：**普通**。悪くはない。
- **C〜E**：**微妙〜危険**。

### 1. 割安度評価（★）
**理論株価**（本来の実力）と **現在値** を比較した「お得度」です。
- :red[★★★★★：**お宝**（上昇余地 **+50%** 以上）]
- ★★★★☆：**激アツ**（上昇余地 **+30%** 〜 +50%）
- ★★★☆☆：**有望**（上昇余地 **+15%** 〜 +30%）

### 2. 売買シグナル（矢印）
| 表示 | 意味 | 判定ロジック |
| :--- | :--- | :--- |
| **↑◎** | **激熱** | **「底値圏」＋「売られすぎ」＋「上昇トレンド」** 等の好条件が3つ以上重なった最強の買い場！ |
| **↗〇** | **買い** | 複数のプラス要素あり。打診買いのチャンス。 |
| **↓✖** | **危険** | **「買われすぎ」＋「暴落シグナル」** 等が点灯。手を出してはいけない。 |

### 3. 需給の壁（突破力）
**過去6ヶ月間で最も取引が活発だった価格帯** です。
- **🚧 上壁**：ここまでは上がっても叩き落とされやすい（抵抗線）。**ここを抜ければ青天井！**
- **🛡️ 下壁**：ここで下げ止まって反発しやすい（支持線）。**ここを割ったら即逃げ！**
""", unsafe_allow_html=True) 

st.subheader("🔢 銘柄入力")
raw_text = st.text_area("分析したい証券コードを入力してください", height=100, placeholder="例：\n7203\n9984\n285A")
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

    with st.spinner(f"🚀 高速分析中..."):
        try:
            bundle = fv.calc_fuyaseru_bundle(codes)
            st.session_state["analysis_bundle"] = bundle
            st.session_state["analysis_codes"] = codes
        except Exception as e:
            st.error(f"エラー: {e}")
            st.stop()

if st.session_state["analysis_bundle"]:
    bundle = st.session_state["analysis_bundle"]
    codes = st.session_state["analysis_codes"]
    
    df = bundle_to_df(bundle, codes)
    
    st.subheader("📊 分析結果")
    st.info("💡 **「詳細」** 列のチェックボックスをONにすると、下に詳細チャートが表示されます！（複数選択OK）")
    
    styled_df = df.style.map(highlight_errors, subset=["銘柄名"])
    
    edited_df = st.data_editor(
        styled_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "詳細": st.column_config.CheckboxColumn(
                "詳細",
                help="チャートを表示",
                default=False,
            ),
            # ★ランク列の設定
            "ランク": st.column_config.TextColumn(
                "ランク",
                help="総合スコア評価（SSS〜E）",
                width="small"
            ),
            "証券コード": st.column_config.TextColumn(disabled=True),
            "銘柄名": st.column_config.TextColumn(disabled=True),
        },
        disabled=["ランク", "証券コード", "銘柄名", "現在値", "理論株価", "上昇余地", "評価", "売買", "需給の壁", "配当利回り", "年間配当", "事業の勢い", "業績", "時価総額", "大口介入", "根拠"]
    )
    
    selected_rows = edited_df[edited_df["詳細"] == True]
    
    # ★複数選択ループ表示
    if not selected_rows.empty:
        for _, row in selected_rows.iterrows():
            selected_code = row["証券コード"]
            ticker_data = bundle.get(selected_code)
            
            if ticker_data and ticker_data.get("name") != "存在しない銘柄" and ticker_data.get("hist_data") is not None:
                st.divider()
                st.markdown(f"### 📉 詳細分析チャート：{ticker_data.get('name')}")
                draw_wall_chart(ticker_data)

    st.info("""
    **※ 評価が表示されない（—）銘柄について**
    赤字決算や財務データが不足している銘柄は、投資リスクの観点から自動的に **「評価対象外」** としています。
    ただし、**「今は赤字だが来期は黒字予想」の場合は、自動的に『予想EPS』を使って理論株価を算出**しています。
    """)

# -----------------------------
# ★豆知識コーナー
# -----------------------------
st.divider()
st.subheader("📚 投資の豆知識・用語解説")

with st.expander("📚 【豆知識】理論株価の計算根拠（グレアム数）とは？"):
    st.markdown("""
    ### 🧙‍♂️ "投資の神様"の師匠が考案した「割安株」の黄金式
    このツールで算出している理論株価は、**「グレアム数」** という計算式をベースにしています。
    これは、あの世界最強の投資家 **ウォーレン・バフェットの師匠** であり、「バリュー投資の父」と呼ばれる **ベンジャミン・グレアム** が考案した由緒ある指標です。

    **今の株価 ＜ 理論株価（グレアム数）** となっていれば、それは **「実力よりも過小評価されている（バーゲンセール中）」** という強力なサインになります。
    """)

with st.expander("🚀 【注目】なぜ「事業の勢い（売上成長率）」を見るの？"):
    st.markdown("""
    ### 📈 株価を押し上げる"真のエンジン"は売上にあり！
    「利益」は経費削減などで一時的に作れますが、**「売上」** の伸びだけは誤魔化せません。売上が伸びているということは、**「その会社の商品が世の中でバカ売れしている」** という最強の証拠だからです。
    - **🚀 +30% 以上： 【超・急成長】** 将来のスター株候補！
    - **🏃 +10% 〜 +30%： 【成長軌道】** 安心の優良企業。
    """)

with st.expander("🌊 ファンドや機関（大口）の\"動き\"を検知する先乗り指標"):
    st.markdown("""
    時価総額や出来高の異常検知を組み合わせ、**「大口投資家が仕掛けやすい（買収や買い上げを狙いやすい）条件」** が揃っているかを%で表示します。
    **独自ロジックで80%以上は「激アツ」！** 大口の買い上げこそ暴騰のチャンスです。
    """)

# -----------------------------
# 🔧 管理者メニュー
# -----------------------------
st.divider()
with st.expander("🔧 管理者専用メニュー"):
    admin_input = st.text_input("管理者コード", type="password", key="admin_pass_bottom")
    if admin_input == ADMIN_CODE:
        st.success("認証OK")
        if st.button("🗑️ キャッシュ全削除", type="primary"):
            st.cache_data.clear()
            st.success("削除完了！再読み込みします...")
            time.sleep(1)
            st.rerun()

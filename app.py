import re
import math
import unicodedata
from typing import Any, Dict, List, Optional
import pandas as pd
import streamlit as st
import fair_value_calc_y4 as fv  # 計算エンジン

# ==========================================
# 🔑 パスワード設定
# ==========================================
USER_PASSWORD = "7777"      # 一般ユーザー
ADMIN_PASSWORD = "77777"    # 管理者（キャッシュ削除可能）
# ==========================================

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
            
            /* 詳細タグ（details）のデザイン調整 */
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
# 🔐 認証ロジック（門番）
# -----------------------------
def check_password():
    """パスワードが合っているか確認する関数"""
    
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "is_admin" not in st.session_state:
        st.session_state["is_admin"] = False

    if not st.session_state["logged_in"]:
        st.markdown("## 🔒 ACCESS RESTRICTED")
        st.caption("関係者専用ツールのため、パスワード制限をかけています。")
        
        password_input = st.text_input("パスワードを入力してください", type="password")
        
        if st.button("ログイン"):
            input_norm = unicodedata.normalize('NFKC', password_input).upper().strip()
            user_norm = unicodedata.normalize('NFKC', USER_PASSWORD).upper().strip()
            admin_norm = unicodedata.normalize('NFKC', ADMIN_PASSWORD).upper().strip()
            
            if input_norm == admin_norm:
                st.session_state["logged_in"] = True
                st.session_state["is_admin"] = True
                st.rerun()
            elif input_norm == user_norm:
                st.session_state["logged_in"] = True
                st.session_state["is_admin"] = False
                st.rerun()
            else:
                st.error("パスワードが違います 🙅")
        
        st.stop()

# ★認証実行
check_password()

# -----------------------------
# 管理者メニュー（キャッシュ削除）
# -----------------------------
if st.session_state["is_admin"]:
    with st.sidebar:
        st.header("🔧 管理者メニュー")
        st.info("管理者権限でログイン中")
        if st.button("🗑️ キャッシュ全削除"):
            st.cache_data.clear()
            st.success("キャッシュを削除しました！")
            time.sleep(1)
            st.rerun()

# ==========================================
# ここから下がいつものアプリ本体
# ==========================================
import time # インポート追加

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

# -----------------------------
# メイン画面
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

<details>
<summary>🤔 「割高」判定ばかり出る…という方へ（クリックで読む）</summary>
<br>
<span style="color: #ff4b4b; font-weight: bold;">※ 割高だから悪いというわけではありません。</span><br>
むしろ優秀な企業だから株価が理論値をはるかに上回っている可能性もあります。<br>
もしお持ちの銘柄で割高判定を受けた場合は、<strong>売り場の模索をするなどの指標</strong>としてお考えくださいませ。
</details>

---

### 2. 売買シグナル（矢印）
**テクニカル指標（RSI・移動平均線・ボリンジャーバンド）** を複合分析した「売買タイミング」です。

| 表示 | 意味 | 判定ロジック |
| :--- | :--- | :--- |
| **↑◎** | **激熱** | **「底値圏」＋「売られすぎ」＋「上昇トレンド」** 等の好条件が3つ以上重なった最強の買い場！ |
| **↗〇** | **買い** | 複数のプラス要素あり。打診買いのチャンス。 |
| **→△** | **様子見** | 可もなく不可もなく。方向感が出るまで待つのが無難。 |
| **↘▲** | **売り** | 天井圏や下落トレンド入り。利益確定や損切りの検討を。 |
| **↓✖** | **危険** | **「買われすぎ」＋「暴落シグナル」** 等が点灯。手を出してはいけない。 |

---

### 3. 需給の壁（突破力）
**過去6ヶ月間で最も取引が活発だった価格帯（しこり玉・岩盤）** です。
この壁は**「跳ね返される場所（反転）」**であると同時に、**「抜けた後の加速装置（突破）」**でもあります。

- **🚧 上値壁（戻り売り圧力）**
    - **【基本】** ここまでは上がっても叩き落とされやすい（抵抗線）。
    - **【突破】** しかしここを食い破れば、売り手不在の**「青天井」**モード突入！
- **🛡️ 下値壁（押し目買い支持）**
    - **【基本】** ここで下げ止まって反発しやすい（支持線）。
    - **【割込】** しかしここを割り込むと、ガチホ勢が全員含み損になり**「パニック売り」**が連鎖する恐れあり。
- **🔥 激戦中（分岐点）**
    - まさに今、その壁の中で戦っている。突破するか、跳ね返されるか、要注目！

※ 理論株価がマイナスの場合や取得できない場合は **評価不能（—）** になります。
""", unsafe_allow_html=True) 

st.subheader("🔢 銘柄入力")

raw_text = st.text_area(
    "分析したい証券コードを入力してください（複数可・改行区切り推奨）",
    height=150,
    placeholder="例：\n7203\n9984\n285A\n（Excelなどからコピペも可能です）"
)

run_btn = st.button("🚀 AIで分析開始！", type="primary")

st.divider()

if run_btn:
    raw_codes = raw_text.split()
    codes = sanitize_codes(raw_codes)
    if not codes:
        st.error("証券コードが入力されていません。")
        st.stop()

    # 待機時間を考慮したメッセージ
    eta = len(codes) * 3
    with st.spinner(f"🚀 爆速で分析中...（Yahoo対策のため1銘柄につき3秒お待ちください。予想完了時間: {eta}秒）"):
        try:
            bundle = fv.calc_fuyaseru_bundle(codes)
        except Exception as e:
            st.error(f"エラー: {e}")
            st.stop()

    df = bundle_to_df(bundle, codes)
    st.subheader("📊 フヤセルブレイン分析結果")
    styled_df = df.style.map(highlight_errors, subset=["銘柄名"])
    st.dataframe(styled_df, use_container_width=True)

    info_text = (
        "**※ 評価が表示されない（—）銘柄について**\n\n"
        "赤字決算や財務データが不足している銘柄は、投資リスクの観点から自動的に **「評価対象外」** としています。\n\n"
        "ただし、**「今は赤字だが来期は黒字予想」の場合は、自動的に『予想EPS』を使って理論株価を算出**しています。\n"
        "その場合、根拠欄に **「※予想EPS参照」** と記載されます。\n\n"
        "---\n\n"
        "**※ 業績（お天気マーク）の判定基準**\n\n"
        "☀ **（優良）**：ROE 8%以上 **かつ** ROA 5%以上（効率性・健全性ともに最強）\n\n"
        "☁ **（普通）**：黒字だが、優良基準には満たない（一般的）\n\n"
        "☔ **（赤字）**：ROE マイナス（赤字決算）"
    )
    st.info(info_text, icon="ℹ️")

    with st.expander("📚 【豆知識】理論株価の計算根拠（グレアム数）とは？"):
        st.markdown("""
        ### 🧙‍♂️ "投資の神様"の師匠が考案した「割安株」の黄金式
        
        このツールで算出している理論株価は、**「グレアム数」** という計算式をベースにしています。
        これは、あの世界最強の投資家 **ウォーレン・バフェットの師匠** であり、
        「バリュー投資の父」と呼ばれる **ベンジャミン・グレアム** が考案した由緒ある指標です。
        
        #### 💡 何がすごいの？
        多くの投資家は「利益（PER）」だけで株を見がちですが、グレアム数は
        **「企業の利益（稼ぐ力）」** と **「純資産（持っている財産）」** の両面から、
        その企業が本来持っている **「真の実力値（適正価格）」** を厳しく割り出します。
        
        > **今の株価 ＜ 理論株価（グレアム数）**
        
        となっていれば、それは **「実力よりも過小評価されている（バーゲンセール中）」** という強力なサインになります。
        """)

    with st.expander("🚀 【注目】なぜ「事業の勢い（売上成長率）」を見るの？"):
        st.markdown("""
        ### 📈 株価を押し上げる"真のエンジン"は売上にあり！
        
        「利益」は経費削減などで一時的に作れますが、**「売上」** の伸びだけは誤魔化せません。
        売上が伸びているということは、**「その会社の商品が世の中でバカ売れしている」** という最強の証拠だからです。
        
        #### 📊 成長スピードの目安（より厳しめのプロ基準）
        
        - **🚀 +30% 以上**： **【超・急成長】**
            - 驚異的な伸びです。将来のスター株候補の可能性がありますが、**期待先行で株価が乱高下するリスク**も高くなります。
        - **🏃 +10% 〜 +30%**： **【成長軌道】**
            - 安定してビジネスが拡大しています。安心して見ていられる優良企業のラインです。
        - **🚶 0% 〜 +10%**： **【安定・成熟】**
            - 急成長はしていませんが、堅実に稼いでいます。配当狙いの銘柄に多いです。
        - **📉 マイナス**： **【衰退・縮小】**
            - 去年より売れていません。ビジネスモデルの転換期か、斜陽産業の可能性があります。
        
        ### 💡 分析のポイント
        **「赤字 × 急成長」の判断について**
        
        本来、赤字企業は投資対象外ですが、「事業の勢い」が **+30%** を超えている場合は、
        **「将来のシェア獲得のために、あえて広告や研究に大金を投じている（＝今は赤字を掘っている）」** だけの可能性があります。
        
        :red[**ただし、黒字化できないまま倒産するリスクもあるため、上級者向けの「ハイリスク・ハイリターン枠」として慎重に見る必要があります。**]
        """)

    with st.expander("🌊 ファンドや機関（大口）の\"動き\"を検知する先乗り指標"):
        st.markdown("""
        時価総額や出来高の異常検知を組み合わせ、**「大口投資家が仕掛けやすい（買収や買い上げを狙いやすい）条件」** が揃っているかを%で表示します。
        
        ### 🔍 判定ロジック
        **先乗り（先回り）理論、季節性、対角性、テーマ性、ファンド動向、アクティビスト検知、企業成長性など、ニッチ性、株大量保有条件、あらゆる大口介入シグナルを自動で検出する独自ロジックを各項目ごとにポイント制にしてパーセンテージを算出する次世代の指数**
        
        #### 🎯 ゴールデンゾーン（時価総額 500億〜3000億円）
        機関投資家等が一番動きやすく、TOB（買収）のターゲットにもなりやすい「おいしい規模感」。
        
        #### 📉 PBR 1倍割れ（バーゲンセール）
        「会社を解散して現金を配った方がマシ」という超割安状態。買収の標的にされやすい。
        
        #### ⚡ 出来高急増（ボリュームスパイク）
        今日の出来高が、普段の平均より2倍以上ある場合、裏で何かが起きている（誰かが集めている）可能性大！
        **独自の先乗り（先回り）法を完全数値化に成功！**
        
        :fire: **80%以上は「激アツ」** 何らかの材料（ニュース）が出る前触れか、水面下で大口が集めている可能性があります。
        
        **大口の買い上げこそ暴騰のチャンスです。この指標もしっかりご確認ください。**
        """)

import streamlit as st
import pandas as pd
import fair_value_calc_y4 as brain  # 計算エンジンを読み込み

# -------------------------------------------
# 1. ページ設定とフヤセル風デザイン (CSS注入)
# -------------------------------------------
st.set_page_config(page_title="フヤセルジワジワレーダー", page_icon="💹", layout="centered")

# 前のデザインを再現するためのCSS
st.markdown("""
    <style>
    /* 全体の背景 */
    .stApp {
        background-color: #f8f9fa;
        font-family: 'Helvetica Neue', Arial, sans-serif;
    }
    /* カード風デザインの再現 */
    div.stButton > button:first-child {
        background-color: #ff4b4b;
        color: white;
        font-weight: bold;
        border-radius: 12px;
        width: 100%;
        border: none;
        padding: 0.6rem 1rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    div.stButton > button:hover {
        background-color: #e63e3e;
        color: white;
    }
    /* サイドバーのカスタマイズ */
    [data-testid="stSidebar"] {
        background-color: white;
        border-right: 1px solid #eee;
    }
    /* 結果表示のヘッダー */
    .result-header {
        color: #ff4b4b;
        font-weight: bold;
        border-left: 5px solid #ff4b4b;
        padding-left: 10px;
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# -------------------------------------------
# 2. ヘッダー表示
# -------------------------------------------
st.title("💹 フヤセルジワジワレーダー")
st.caption("〜 ジェシカ流・理論株価＆大口介入スコア算出ツール 〜")

# -------------------------------------------
# 3. 入力エリア (サイドバー)
# -------------------------------------------
with st.sidebar:
    st.header("銘柄リスト入力")
    default_codes = "7203, 8306, 9984, 5401, 9101"
    codes_input = st.text_area("銘柄コード（カンマ区切り）", default_codes, height=150)
    
    analyze_btn = st.button("🚀 分析開始")
    st.markdown("---")
    st.markdown("##### 💡 見方のヒント")
    st.markdown("* **★**: 多いほど割安（上昇余地）")
    st.markdown("* **大口スコア**: 80点以上は要注目🔥")

# -------------------------------------------
# 4. メイン処理
# -------------------------------------------
if analyze_btn:
    # コードを整理
    raw_codes = codes_input.replace(" ", "").replace("　", "").split(",")
    target_codes = [c for c in raw_codes if c]

    if not target_codes:
        st.warning("銘柄コードを入力してください")
    else:
        with st.spinner(f"{len(target_codes)}銘柄を高速分析中..."):
            # 爆速エンジンの呼び出し
            results = brain.calc_fuyaseru_bundle(target_codes)

        # 結果をリストにまとめる
        data_list = []
        for code in target_codes:
            if code in results:
                r = results[code]
                
                stars = "★" * (r.get("rating") or 0)
                upside = r.get("upside_pct")
                upside_str = f"+{upside}%" if upside and upside > 0 else f"{upside}%"
                
                big_score = r.get("big_prob", 0)
                big_icon = "🔥" if big_score >= 80 else ("✨" if big_score >= 50 else "")

                mc = r.get("market_cap")
                mc_oku = f"{mc/100000000:,.0f}億" if mc else "-"

                data_list.append({
                    "コード": code,
                    "銘柄名": r.get("name"),
                    "現在値": f"{r.get('price', 0):,.0f}",
                    "理論株価": f"{r.get('fair_value', 0):,.0f}",
                    "上昇余地": upside_str,
                    "割安度": stars,
                    "大口期待度": f"{big_score}点 {big_icon}",
                    "天気": r.get("weather"),
                    "時価総額": mc_oku,
                    "メモ": r.get("note")
                })
        
        # 結果表示
        st.markdown('<div class="result-header">📊 分析結果</div>', unsafe_allow_html=True)
        
        df = pd.DataFrame(data_list)
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.success("全ての分析が完了しました！")

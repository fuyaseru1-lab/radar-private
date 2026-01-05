import streamlit as st
import pandas as pd
import fair_value_calc_y4 as brain  # 計算エンジンを読み込み

# -------------------------------------------
# ページ設定
# -------------------------------------------
st.set_page_config(page_title="フヤセルジワジワレーダー", page_icon="💹", layout="wide")

st.title("💹 フヤセルジワジワレーダー")
st.caption("ジェシカ流・理論株価＆大口介入スコア算出ツール")

# -------------------------------------------
# 入力エリア
# -------------------------------------------
with st.sidebar:
    st.header("銘柄リスト入力")
    default_codes = "7203, 8306, 9984, 5401, 9101"
    codes_input = st.text_area("銘柄コード（カンマ区切り）", default_codes, height=150)
    
    analyze_btn = st.button("🚀 分析開始", type="primary")
    st.markdown("---")
    st.markdown("**見方のヒント**")
    st.markdown("- **★**: 5つに近いほど割安（上昇余地あり）")
    st.markdown("- **大口スコア**: 80点以上は機関投資家の好物")

# -------------------------------------------
# メイン処理
# -------------------------------------------
if analyze_btn:
    # コードをリスト化
    raw_codes = codes_input.replace(" ", "").replace("　", "").split(",")
    target_codes = [c for c in raw_codes if c]

    if not target_codes:
        st.warning("銘柄コードを入力してください")
    else:
        with st.spinner(f"{len(target_codes)}銘柄を高速分析中..."):
            # ★爆速エンジンの呼び出し
            results = brain.calc_fuyaseru_bundle(target_codes)

        # ---------------------------------------
        # 結果の整形と表示
        # ---------------------------------------
        data_list = []
        for code in target_codes:
            if code in results:
                r = results[code]
                
                # 表示用にデータを整理
                stars = "★" * (r.get("rating") or 0)
                upside = r.get("upside_pct")
                upside_str = f"+{upside}%" if upside and upside > 0 else f"{upside}%"
                
                # 大口スコア
                big_score = r.get("big_prob", 0)
                big_icon = "🔥" if big_score >= 80 else ("✨" if big_score >= 50 else "")

                # 時価総額を億円に
                mc = r.get("market_cap")
                mc_oku = f"{mc/100000000:,.0f}億" if mc else "-"

                data_list.append({
                    "コード": code,
                    "銘柄名": r.get("name"),
                    "現在値": f"{r.get('price', 0):,.0f}",
                    "理論株価": f"{r.get('fair_value', 0):,.0f}",
                    "上昇余地": upside_str,
                    "おすすめ度": stars,
                    "大口スコア": f"{big_score}点 {big_icon}",
                    "天気": r.get("weather"),
                    "時価総額": mc_oku,
                    "メモ": r.get("note")
                })
        
        # DataFrame化して表示
        df = pd.DataFrame(data_list)
        st.dataframe(
            df, 
            use_container_width=True,
            column_config={
                "おすすめ度": st.column_config.TextColumn("割安度", help="理論株価との乖離による判定"),
                "大口スコア": st.column_config.TextColumn("大口期待度", help="時価総額・PBR・出来高によるスコア"),
            },
            hide_index=True
        )

        st.success("分析完了！")

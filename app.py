import streamlit as st
import yfinance as yf
import pandas as pd

st.title("🏥 接続診断ツール")

if st.button("通信テスト開始"):
    st.write("通信を試みています...")
    try:
        # トヨタ(7203)のデータを取ってみる
        ticker = yf.Ticker("7203.T")
        hist = ticker.history(period="1d")
        
        if hist is None or hist.empty:
            st.error("❌ データが空です。")
            st.error("判定：Yahooファイナンスからアクセス制限（BAN）を受けています。")
            st.warning("対処法：IPアドレスを変える（スマホのWi-Fiを切って4G/5Gで繋ぐなど）か、明日まで待つ必要があります。")
        else:
            st.success("✅ データ取得成功！")
            st.write(f"取得できた株価: {hist['Close'].iloc[-1]} 円")
            st.success("判定：アクセス制限はされていません！")
            st.info("メインのコードに戻して、もう一度『Clear cache』を試してください。")
            
    except Exception as e:
        st.error(f"❌ エラー発生: {e}")

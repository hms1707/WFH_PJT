import streamlit as st
import pandas as pd
import json
import time
import os

# 1. 페이지 레이아웃: wide 모드로 설정하여 가로 공간 최대한 확보
st.set_page_config(page_title="하이브리드 트레이딩 대시보드", page_icon="🚀", layout="wide")

# 스타일 최적화 (Streamlit 기본 여백 줄이기)
st.markdown("""
    <style>
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    </style>
    """, unsafe_allow_html=True)

st.title("🚀 자동매매 봇 실시간 모니터링")

def load_status():
    try:
        with open("bot_status.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

def load_history():
    try:
        if os.path.isfile("trade_history.csv"):
            return pd.read_csv("trade_history.csv")
        return pd.DataFrame()
    except:
        return pd.DataFrame()

status = load_status()

if status is None:
    st.warning("봇이 데이터를 수집 중입니다... 엔진(`WFH_PJT_Engine.py`)이 실행 중인지 확인해주세요!")
else:
    # 2. 메트릭 레이아웃: 화면 넓이에 맞춰 균등 분배
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("현재 비트코인 가격", f"{status['price']:,.0f} 원")
    with col2: st.metric("현재 시장 온도 🌡️", f"{status['temp']}도", status['state'])
    with col3: 
        holding = "보유 중 🟢" if status['is_holding'] else "대기 중 💤"
        st.metric("포지션 상태", holding)
    with col4: 
        profit = status.get('current_profit', 0)
        st.metric("현재 수익률 📈", f"{profit:.2f}%")

    st.markdown("---")
    
    # 3. 차트 vs 거래내역 비중 조절 (차트 3 : 표 1)
    # col_chart를 3배 크게 할당하여 넓게 쓰기
    col_chart, col_table = st.columns([3, 1])
    
    history_df = load_history()
    
    with col_chart:
        st.subheader("📊 누적 수익률 차트")
        if not history_df.empty:
            history_df['cumulative_profit'] = history_df['profit_rate'].cumsum()
            # use_container_width=True로 차트가 부모 컨테이너(col_chart)를 꽉 채우게 함
            st.line_chart(history_df['cumulative_profit'], use_container_width=True)
        else:
            st.info("아직 거래 내역이 없습니다.")
            
    with col_table:
        st.subheader("📋 최근 거래 체결 내역")
        if not history_df.empty:
            # 표도 꽉 차게 설정
            st.dataframe(history_df.iloc[::-1].head(10), use_container_width=True)
        else:
            st.info("거래 내역이 없습니다.")

time.sleep(2)
st.rerun()
import streamlit as st
import pandas as pd
import json
import time
import os

# 1. 페이지 설정: 가로 공간을 최대한 활용하는 wide 모드
st.set_page_config(page_title="하이브리드 트레이딩 대시보드", page_icon="🚀", layout="wide")

# 레이아웃을 더 시원하게 만드는 CSS 최적화
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }
    </style>
    """, unsafe_allow_html=True)

st.title("🚀 자동매매 봇 실시간 모니터링")
st.markdown("---")

def load_status():
    try:
        # 데이터가 없을 경우를 대비해 에러 방지 처리
        if not os.path.exists("bot_status.json"):
            return None
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
    st.warning("봇이 데이터를 수집 중입니다... (엔진인 `WFH_PJT_Engine.py`가 실행 중인지 확인해주세요!)")
else:
    # 2. 상단 지표: 4개로 균등 분할하여 가로폭 최적화
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("현재 비트코인 가격", f"{status.get('price', 0):,.0f} 원")
    with col2:
        st.metric("현재 시장 온도 🌡️", f"{status.get('temp', 0)}도", status.get('state', '보합'))
    with col3:
        holding_str = "보유 중 🟢" if status.get('is_holding') else "대기 중 💤"
        st.metric("포지션 상태", holding_str)
    with col4:
        profit = status.get('current_profit', 0)
        st.metric("현재 보유 수익률 📈", f"{profit:.2f}%")

    st.markdown("---")
    
    # 3. 차트(넓게)와 거래 내역(좁게)을 3:1 비율로 배치
    col_chart, col_table = st.columns([3, 1])
    
    history_df = load_history()
    
    with col_chart:
        st.subheader("📊 누적 수익률 차트")
        if not history_df.empty:
            history_df['cumulative_profit'] = history_df['profit_rate'].cumsum()
            # use_container_width=True로 차트가 컨테이너를 가득 채우게 함
            st.line_chart(history_df['cumulative_profit'], use_container_width=True)
        else:
            st.info("아직 완료된 거래가 없습니다.")
            
    with col_table:
        st.subheader("📋 최근 거래 체결 내역")
        if not history_df.empty:
            # use_container_width=True로 표도 가로폭에 맞춤
            st.dataframe(history_df.iloc[::-1].head(10), use_container_width=True)
        else:
            st.info("거래 내역 없음")

# 2초마다 갱신
time.sleep(2)
st.rerun()
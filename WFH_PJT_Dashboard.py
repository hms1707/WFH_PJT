import streamlit as st
import pandas as pd
import json
import os
import time
import uuid
import ccxt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# 2560x1440 모니터 최적화
st.set_page_config(page_title="퇴사 발사대 대시보드", page_icon="🚀", layout="wide")

# CSS: 상단 잘림 방지, 헤더 스타일링, 수직 밸런스 및 폰트 사이즈 조정
st.markdown("""
    <style>
    .block-container { 
        padding-top: 3.5rem !important; 
        padding-bottom: 2rem !important; 
        padding-left: 1.5rem !important; 
        padding-right: 1.5rem !important; 
        max-width: 100% !important; 
    }
    h3 { margin-bottom: 5px !important; font-size: 1.1rem !important; }
    
    /* 상단 우측 시간 스타일 */
    .header-time { font-size: 1.2rem; color: #888; text-align: right; line-height: 1.2; }
    .header-date { font-weight: bold; color: #ccc; }
    
    /* 메트릭스와 차트 사이 여백 조정 */
    .stMetric { margin-bottom: -15px !important; }
    </style>
""", unsafe_allow_html=True)

STATUS_FILE = "bot_status.json"
HISTORY_FILE = "trade_history.csv"
CMD_FILE = "manual_cmd.json"

def load_status():
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def safe_num(d, key, default=0):
    v = d.get(key, default)
    return default if v is None else v

def load_history():
    if not os.path.isfile(HISTORY_FILE):
        return pd.DataFrame()
    try:
        df = pd.read_csv(HISTORY_FILE)
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()
    return df.iloc[::-1]

def write_command(action, amount_krw):
    cmd = {
        "action": action,
        "amount_krw": amount_krw,
        "cmd_id": str(uuid.uuid4()), 
        "ts": time.time(),
    }
    tmp_path = CMD_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cmd, f)
    os.replace(tmp_path, CMD_FILE)

@st.cache_resource
def get_upbit_client():
    return ccxt.upbit({"enableRateLimit": True})

# ==========================================
# ★ 상단 헤더 영역 (로고/버전 & 실시간 시계 정렬 픽스)
# ==========================================
head_left, head_right = st.columns([0.8, 0.2])
with head_left:
    st.markdown("""
    <div style="display: flex; align-items: flex-end; gap: 20px; padding-bottom: 5px;">
        <h2 style="margin-bottom: 0; padding-bottom: 0; line-height: 1;">🚀 퇴사 발사대 (Crypto Bot)</h2>
        <div style="display: flex; flex-direction: column; font-size: 0.85rem; color: #aaa; line-height: 1.3;">
            <div style="display: flex;"><span style="width: 75px;">Engine</span><span>v0.1 (2026.07.02)</span></div>
            <div style="display: flex;"><span style="width: 75px;">Dashboard</span><span>v0.1 (2026.07.02)</span></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

with head_right:
    now_kst = datetime.utcnow() + timedelta(hours=9)
    date_str = now_kst.strftime("%Y-%m-%d")
    time_str = now_kst.strftime("%p %I:%M:%S")
    st.markdown(f"<div class='header-time'><span class='header-date'>{date_str}</span><br>{time_str}</div>", unsafe_allow_html=True)

st.markdown("---")

# ==========================================
# ★ 3단 레이아웃 비율 수정 (12% - 58% - 30%)
# ==========================================
left, mid, right = st.columns([0.12, 0.58, 0.30])

# [좌측 12%]: 상황판 (자산 및 봇 포지션만 세로 배열)
with left:
    @st.fragment(run_every=1) 
    def render_left_panel():
        status = load_status()
        krw_price = safe_num(status, 'price')

        # 1. 바이낸스 자산 (Sandbox)
        st.markdown("##### 🌍 바이낸스 자산 (Sandbox)")
        usdt_krw_rate = safe_num(status, 'usdt_krw_rate', 1380) 
        usdt_bal = safe_num(status, 'usdt_bal')
        btc_bal = safe_num(status, 'btc_bal')
        
        binance_krw_eval = usdt_bal * usdt_krw_rate
        binance_total_krw = binance_krw_eval + (btc_bal * krw_price)
        
        st.write(f"- 보유 KRW : {binance_krw_eval:,.0f} KRW")
        st.write(f"- 보유 BTC : {btc_bal:.8f} BTC")
        st.write(f"- 총 자산 : {binance_total_krw:,.0f} KRW")

        st.markdown("<br>", unsafe_allow_html=True)

        # 2. 업비트 자산
        st.markdown("##### 🏦 업비트 자산")
        upbit_krw = safe_num(status, 'upbit_krw')
        upbit_btc = safe_num(status, 'upbit_btc')
        upbit_total = upbit_krw + (upbit_btc * krw_price)
        
        st.write(f"- 보유 KRW : {upbit_krw:,.0f} KRW")
        st.write(f"- 보유 BTC : {upbit_btc:.8f} BTC")
        st.write(f"- 총 자산 : {upbit_total:,.0f} KRW")

        st.markdown("<br>", unsafe_allow_html=True)

        # 3. 봇 포지션
        st.markdown("##### 🤖 봇 포지션")
        st.write(f"- 상태: **{'보유 중 🟢' if status.get('is_holding') else '대기 중 💤'}**")
        st.write(f"- 진입가: {safe_num(status, 'buy_price'):,.0f} KRW")
        st.write(f"- 손익: {safe_num(status, 'current_profit'):.2f}%")

    render_left_panel()

# [가운데 58%]: 메트릭스 4개 가로 배열 & 차트
with mid:
    @st.fragment(run_every=1)
    def render_mid_metrics():
        status = load_status()
        c1, c2, c3, c4 = st.columns(4)
        
        temp = safe_num(status, "temp", 20)
        emoji = "🔥" if temp > 30 else "❄️" if temp < 15 else "🌡️"
        
        c1.metric("🌡️ 시장 온도", f"{emoji} {temp}도")
        c2.metric("업비트 (KRW)", f"{safe_num(status, 'price'):,.0f}")
        c3.metric("바이낸스 (USDT)", f"${safe_num(status, 'binance_price'):,.2f}")
        c4.metric("김프", f"{safe_num(status, 'premium_pct'):.2f}%")
        
    render_mid_metrics()
    
    st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
    st.subheader("📈 실시간 차트 (BTC/KRW)")

    @st.fragment(run_every=2) 
    def render_chart():
        status = load_status()
        try:
            upbit = get_upbit_client()
            ohlcv = upbit.fetch_ohlcv("BTC/KRW", timeframe="1m", limit=150)
            df = pd.DataFrame(ohlcv, columns=["t", "o", "h", "l", "c", "v"])
            df["t"] = pd.to_datetime(df["t"], unit="ms") + pd.Timedelta(hours=9)
            
            df['ema7'] = df['c'].ewm(span=7, adjust=False).mean()
            df['ema25'] = df['c'].ewm(span=25, adjust=False).mean()
            
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.03, row_heights=[0.75, 0.25])
            
            fig.add_trace(go.Candlestick(
                x=df["t"], open=df["o"], high=df["h"], low=df["l"], close=df["c"],
                increasing_line_color='#FF3B30', decreasing_line_color='#007AFF',
                name='Price'
            ), row=1, col=1)
            
            fig.add_trace(go.Scatter(x=df["t"], y=df['ema7'], line=dict(color='#FFD700', width=1.5), name='EMA(7)'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df["t"], y=df['ema25'], line=dict(color='#9370DB', width=1.5), name='EMA(25)'), row=1, col=1)
            
            volume_colors = ['#FF3B30' if row['c'] >= row['o'] else '#007AFF' for _, row in df.iterrows()]
            fig.add_trace(go.Bar(
                x=df['t'], y=df['v'], marker_color=volume_colors, name='Volume'
            ), row=2, col=1)
            
            # ★ 버그 픽스: 현재 가격 가로 대시선 및 Y축 정밀 라벨 박스 그리기 (X축 오류 해결)
            current_close = df.iloc[-1]['c']
            current_open = df.iloc[-1]['o']
            curr_color = '#FF3B30' if current_close >= current_open else '#007AFF'
            
            # 가로선 + Y축 끝에 박스 붙이기 (annotation_position 활용으로 안전하게 우측 고정)
            fig.add_hline(
                y=current_close, 
                line_dash="dash", 
                line_color=curr_color, 
                line_width=1.5,
                annotation_text=f"{current_close:,.0f}", 
                annotation_position="right",
                annotation_font_color="white",
                annotation_bgcolor=curr_color,
                annotation_font_size=12,
                row=1, col=1
            )
            
            # 익절/손절선 그리기
            if status.get('is_holding') and safe_num(status, 'buy_price') > 0:
                buy_p = status['buy_price']
                tp_p = buy_p * (1.0045 / 0.999) 
                sl_p = buy_p * (0.997 / 0.999) 
                
                fig.add_hline(y=buy_p, line_dash="dash", line_color="#FFD700", row=1, col=1, annotation_text="진입가", annotation_position="top left")
                fig.add_hline(y=tp_p, line_dash="dash", line_color="#00FF00", row=1, col=1, annotation_text="목표 익절 (순수익 +0.35%)", annotation_position="top left")
                fig.add_hline(y=sl_p, line_dash="dash", line_color="#FF1493", row=1, col=1, annotation_text="안전 손절 (순손실 -0.40%)", annotation_position="bottom left")

            fig.update_layout(
                height=600, 
                template="plotly_dark",
                # ★ 우측 여백(r)을 100으로 대폭 늘려 90,000,000 라벨 박스가 온전히 보이게 함
                margin=dict(l=0, r=100, t=10, b=0),
                dragmode="pan",
                showlegend=False,
                xaxis_rangeslider_visible=False,
                uirevision="keep"
            )
            
            fig.update_yaxes(side="right", tickformat=",", row=1, col=1) 
            fig.update_yaxes(side="right", showgrid=False, row=2, col=1)
            fig.update_xaxes(rangeslider_visible=False, row=2, col=1)
            
            st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True}, key="btc_chart")
        except Exception as e:
            st.error(f"차트 로딩 실패: {e}")

    render_chart()

# [우측 30%]: 컨트롤러 & 히스토리
with right:
    st.subheader("🎮 매매 컨트롤러")

    @st.fragment
    def render_controller():
        amt = st.selectbox("거래 금액", ["1만", "5만", "10만", "50만"])
        val = {"1만": 10000, "5만": 50000, "10만": 100000, "50만": 500000}[amt]

        def handle_click(action):
            now = time.time()
            last = st.session_state.get("last_cmd_ts", 0)
            if now - last < 1.5:
                st.toast("⚠️ 방금 주문을 보냈어요. 잠시 후 다시 시도하세요.")
                return
            write_command(action, val)
            st.session_state["last_cmd_ts"] = now
            st.toast(f"✅ {action} 주문 전송 ({val:,}원)")

        col_b, col_s = st.columns(2)
        if col_b.button("🔴 매수", type="primary", use_container_width=True):
            handle_click("BUY")
        if col_s.button("🔵 매도", use_container_width=True):
            handle_click("SELL")

    render_controller()

    st.subheader("📋 체결 히스토리")

    @st.fragment(run_every=1)
    def render_history():
        hist = load_history()
        needed_cols = ["time", "buy_price", "sell_price", "trade_amount", "profit_krw", "profit_rate"]
        
        if not hist.empty and all(c in hist.columns for c in needed_cols):
            display_df = hist[needed_cols].rename(columns={
                "time": "거래일시",
                "buy_price": "구매가격",
                "sell_price": "판매가격",
                "trade_amount": "수량",
                "profit_krw": "평가손익",
                "profit_rate": "수익률"
            })
            
            st.dataframe(
                display_df, 
                use_container_width=True,
                hide_index=True, 
                height=500,
                column_config={
                    "구매가격": st.column_config.NumberColumn(format="%d"),
                    "판매가격": st.column_config.NumberColumn(format="%d"),
                    "수량": st.column_config.NumberColumn(format="%.4f"),
                    "평가손익": st.column_config.NumberColumn(format="%d"),
                    "수익률": st.column_config.NumberColumn(format="%.2f%%")
                }
            )
        else:
            st.caption("체결 내역이 없거나 구버전 데이터입니다.")

    render_history()
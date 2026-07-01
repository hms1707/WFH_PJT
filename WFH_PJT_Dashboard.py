import streamlit as st
import pandas as pd
import time
import uuid
import ccxt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from supabase import create_client, Client

# 2560x1440 모니터 최적화
st.set_page_config(page_title="퇴사 발사대 대시보드", page_icon="🚀", layout="wide")

# CSS: 상단 잘림 방지, 헤더 스타일링, 수직 밸런스 조정
st.markdown("""
    <style>
    .block-container { 
        padding-top: 3rem !important; 
        padding-bottom: 2rem !important; 
        padding-left: 1rem !important; 
        padding-right: 1rem !important; 
        max-width: 100% !important; 
    }
    h3 { margin-bottom: 5px !important; font-size: 1.1rem !important; }
    .header-time { font-size: 1.2rem; color: #888; text-align: right; line-height: 1.2; }
    .header-date { font-weight: bold; color: #ccc; }
    /* 버전 텍스트를 위아래로 딱 맞게 정렬 */
    .version-table { display: inline-block; vertical-align: middle; font-size: 0.8rem; color: #00FF00; margin-left: 15px; line-height: 1.2; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# ★ Supabase (클라우드 DB) 연동
# ==========================================
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]  # 여기에 anon/public 키가 들어옵니다!
    return create_client(url, key)

try:
    supabase = init_supabase()
except Exception as e:
    st.error("DB 연결 실패! Streamlit Secrets에 SUPABASE_URL과 SUPABASE_KEY가 등록되어 있는지 확인해주세요.")
    st.stop()

# DB에서 봇 상태 읽어오기
def load_status():
    try:
        res = supabase.table('bot_status').select('status_data').eq('id', 1).execute()
        if res.data:
            return res.data[0]['status_data']
    except:
        pass
    return {}

# DB에서 체결 히스토리 읽어오기
def load_history():
    try:
        res = supabase.table('trade_history').select('*').order('id', desc=True).limit(50).execute()
        if res.data:
            return pd.DataFrame(res.data)
    except:
        pass
    return pd.DataFrame()

# DB로 수동 매매 명령 쏘기
def write_command(action, amount_krw):
    try:
        cmd = {
            "action": action,
            "amount_krw": amount_krw,
            "cmd_id": str(uuid.uuid4()),
            "ts": time.time(),
            "is_executed": False
        }
        supabase.table('bot_commands').insert(cmd).execute()
    except Exception as e:
        st.error(f"명령어 전송 실패: {e}")

def safe_num(d, key, default=0):
    v = d.get(key, default)
    return default if v is None else v

@st.cache_resource
def get_upbit_client():
    return ccxt.upbit({"enableRateLimit": True})

# ==========================================
# ★ 상단 헤더 영역 (로고/버전 & 실시간 시계)
# ==========================================
head_left, head_right = st.columns([0.8, 0.2])
with head_left:
    st.markdown("""
        <div style="display: flex; align-items: center;">
            <h2 style="margin: 0; padding: 0;">🚀 퇴사 발사대 (Crypto Bot)</h2>
            <div class="version-table">
                <div>Engine &nbsp;&nbsp;&nbsp;&nbsp; v3.0 (2026.07.02)</div>
                <div>Dashboard &nbsp; v3.0 (2026.07.02)</div>
            </div>
        </div>
    """, unsafe_allow_html=True)
with head_right:
    now_kst = datetime.utcnow() + timedelta(hours=9)
    st.markdown(f"<div class='header-time'><span class='header-date'>{now_kst.strftime('%Y-%m-%d')}</span><br>{now_kst.strftime('%p %I:%M:%S')}</div>", unsafe_allow_html=True)

st.markdown("---")

# ==========================================
# ★ 상단 메트릭 패널 (차트 위로 이동하여 공간 확보)
# ==========================================
status = load_status()

m1, m2, m3, m4 = st.columns(4)
with m1:
    temp = safe_num(status, "temp", 20)
    emoji = "🔥" if temp > 30 else "❄️" if temp < 15 else "🌡️"
    st.metric("시장 온도", f"{emoji} {temp}도")
with m2:
    st.metric("업비트 가격", f"{safe_num(status, 'price'):,.0f} KRW")
with m3:
    st.metric("바이낸스 가격", f"${safe_num(status, 'binance_price'):,.2f}")
with m4:
    st.metric("현재 김치 프리미엄", f"{safe_num(status, 'premium_pct'):.2f}%")

st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# ★ 3단 레이아웃 (12% - 58% - 30%)
# ==========================================
left, mid, right = st.columns([0.12, 0.58, 0.30])

# [좌측 12%]: 압축된 자산 및 포지션 정보
with left:
    @st.fragment(run_every=2)
    def render_left_panel():
        curr_status = load_status()
        
        st.markdown("#### 🌍 바이낸스 (Sandbox)")
        st.write(f"보유 USDT: ${safe_num(curr_status, 'usdt_bal'):,.2f}")
        st.write(f"보유 BTC: {safe_num(curr_status, 'btc_bal'):.6f} ₿")
        
        st.markdown("#### 🏦 업비트 자산")
        st.write(f"보유 KRW: {safe_num(curr_status, 'upbit_krw'):,.0f}원")
        st.write(f"보유 BTC: {safe_num(curr_status, 'upbit_btc'):.6f} ₿")
        
        st.markdown("#### 🤖 봇 포지션")
        st.write(f"상태: **{'보유 중 🟢' if curr_status.get('is_holding') else '대기 중 💤'}**")
        st.write(f"진입가: {safe_num(curr_status, 'buy_price'):,.0f}")
        color = "red" if safe_num(curr_status, 'current_profit') > 0 else "blue"
        st.markdown(f"손익: <span style='color:{color}'><b>{safe_num(curr_status, 'current_profit'):.2f}%</b></span>", unsafe_allow_html=True)

    render_left_panel()

# [가운데 58%]: 차트 (X축 버그 픽스 & Y축 라벨 앵커 적용)
with mid:
    st.subheader("📈 실시간 차트 (BTC/KRW)")

    @st.fragment(run_every=2) 
    def render_chart():
        curr_status = load_status()
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
            
            # 목표/손절선 그리기 (보유 중일 때만)
            if curr_status.get('is_holding') and safe_num(curr_status, 'buy_price') > 0:
                buy_p = curr_status['buy_price']
                tp_p = buy_p * (1.0045 / 0.999) 
                sl_p = buy_p * (0.997 / 0.999) 
                
                # 라벨을 안전하게 우측 종단에 고정 (X축 늘어남 방지)
                fig.add_hline(y=buy_p, line_dash="dash", line_color="#FFD700", row=1, col=1)
                fig.add_annotation(x=1.01, xref="paper", y=buy_p, text="진입가", showarrow=False, font=dict(size=10, color="black"), bgcolor="#FFD700", xanchor="left", row=1, col=1)
                
                fig.add_hline(y=tp_p, line_dash="dash", line_color="#00FF00", row=1, col=1)
                fig.add_annotation(x=1.01, xref="paper", y=tp_p, text="목표(순 +0.35%)", showarrow=False, font=dict(size=10, color="black"), bgcolor="#00FF00", xanchor="left", row=1, col=1)
                
                fig.add_hline(y=sl_p, line_dash="dash", line_color="#FF1493", row=1, col=1)
                fig.add_annotation(x=1.01, xref="paper", y=sl_p, text="손절(순 -0.40%)", showarrow=False, font=dict(size=10, color="white"), bgcolor="#FF1493", xanchor="left", row=1, col=1)

            # 실시간 현재 가격 표시선
            current_p = df['c'].iloc[-1]
            cur_color = "#FF3B30" if current_p >= df['o'].iloc[-1] else "#007AFF"
            fig.add_hline(y=current_p, line_dash="dash", line_color=cur_color, row=1, col=1)
            fig.add_annotation(x=1.01, xref="paper", y=current_p, text=f"{current_p:,.0f}", showarrow=False, font=dict(size=11, color="white"), bgcolor=cur_color, xanchor="left", row=1, col=1)

            fig.update_layout(
                height=650,
                template="plotly_dark",
                margin=dict(l=0, r=80, t=10, b=0), # 우측 여백 확보하여 라벨이 안 잘리게 함
                dragmode="pan",
                showlegend=False,
                xaxis_rangeslider_visible=False,
                uirevision="keep"
            )
            
            fig.update_yaxes(side="right", row=1, col=1)
            fig.update_yaxes(side="right", showgrid=False, row=2, col=1)
            fig.update_xaxes(rangeslider_visible=False, row=2, col=1)
            
            st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True}, key="btc_chart")
        except Exception as e:
            st.error(f"차트 로딩 실패: {e}")

    render_chart()

# [우측 30%]: 컨트롤러 & 히스토리
with right:
    st.subheader("🎮 원격 매매 컨트롤러")

    @st.fragment
    def render_controller():
        amt = st.selectbox("거래 금액", ["1만", "5만", "10만", "50만"])
        val = {"1만": 10000, "5만": 50000, "10만": 100000, "50만": 500000}[amt]

        def handle_click(action):
            now = time.time()
            last = st.session_state.get("last_cmd_ts", 0)
            if now - last < 2.0:
                st.toast("⚠️ 방금 명령을 보냈어요. 잠시 후 다시 시도하세요.")
                return
            write_command(action, val)
            st.session_state["last_cmd_ts"] = now
            st.toast(f"✅ {action} 명령 클라우드 전송 ({val:,}원)")

        col_b, col_s = st.columns(2)
        if col_b.button("🔴 매수", type="primary", use_container_width=True):
            handle_click("BUY")
        if col_s.button("🔵 매도", use_container_width=True):
            handle_click("SELL")

    render_controller()

    st.subheader("📋 체결 히스토리")

    @st.fragment(run_every=2)
    def render_history():
        hist = load_history()
        
        if not hist.empty:
            display_df = hist.rename(columns={
                "time": "거래일시",
                "buy_price": "구매가격",
                "sell_price": "판매가격",
                "trade_amount": "수량",
                "profit_krw": "평가손익",
                "profit_rate": "수익률"
            })
            display_df = display_df[["거래일시", "구매가격", "판매가격", "수량", "평가손익", "수익률"]]
            
            st.dataframe(
                display_df, 
                use_container_width=True,
                hide_index=True, 
                height=450,
                column_config={
                    "구매가격": st.column_config.NumberColumn(format="%d"),
                    "판매가격": st.column_config.NumberColumn(format="%d"),
                    "수량": st.column_config.NumberColumn(format="%.4f"),
                    "평가손익": st.column_config.NumberColumn(format="%d"),
                    "수익률": st.column_config.NumberColumn(format="%.2f%%")
                }
            )
        else:
            st.caption("클라우드 DB에 체결 내역이 아직 없습니다.")

    render_history()
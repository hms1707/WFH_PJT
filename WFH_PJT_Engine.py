import ccxt
import time
import sys
from datetime import datetime
import pandas as pd
import ta
import json
import os
import urllib.request 
from dotenv import load_dotenv
from supabase import create_client, Client

# 환경 변수 로드 (.env 파일)
load_dotenv()

# ==========================================
# 1. Supabase (DB) 및 거래소 초기화
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ 에러: .env 파일에 SUPABASE_URL과 SUPABASE_KEY를 입력해주세요!")
    sys.exit()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

exchange = ccxt.upbit({
    'apiKey': os.getenv('UPBIT_API_KEY', ''),  
    'secret': os.getenv('UPBIT_SECRET_KEY', ''),  
    'enableRateLimit': True
}) 

binance_live = ccxt.binance({'enableRateLimit': True}) 
binance_sandbox = ccxt.binance({
    'apiKey': os.getenv('BINANCE_API_KEY', ''),
    'secret': os.getenv('BINANCE_SECRET_KEY', ''),
    'enableRateLimit': True,
})
binance_sandbox.set_sandbox_mode(True)

# 봇의 기억 상자
bot_state = {
    'is_holding': False,
    'buy_price': 0.0,
    'total_trades': 0,
    'profits': [],
    'temps': [],
    'start_time': datetime.now(),
    'cool_down_until': 0 
}

# --- [유틸리티 함수] ---
def get_realtime_exchange_rate():
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req)
        data = json.loads(response.read().decode('utf-8'))
        return data['rates']['KRW']
    except:
        return 1380

def init_clean_state():
    print("\n🚀 실전 테스트 시작: 보유 코인 전량 매도 및 초기화 중...")
    try:
        balance = binance_sandbox.fetch_balance()
        btc_balance = balance['free'].get('BTC', 0)
        if btc_balance > 0.0001: 
            binance_sandbox.create_market_sell_order('BTC/USDT', btc_balance)
            print(f"✅ 샌드박스 초기화 완료: {btc_balance} BTC 매도")
        else:
            print("✅ 샌드박스 초기화 완료: 보유 코인 없음")
    except Exception as e:
        print(f"⚠️ 초기화 중 에러 발생: {e}")

def test_sandbox_connection():
    try:
        balance = binance_sandbox.fetch_balance()
        usdt_balance = balance['free'].get('USDT', 0)
        print(f"✅ 테스트넷 연결 성공! (💵 {usdt_balance:,.2f} USDT)")
        return True
    except Exception as e:
        print(f"❌ 연결 실패: {e}")
        return False

# --- [제어 센터: 시장 분석 및 판단 엔진] ---
def decide_trade(symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1m', limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df['ema_short'] = ta.trend.ema_indicator(df['close'], window=7)
        df['ema_long'] = ta.trend.ema_indicator(df['close'], window=25)
        df['rsi'] = ta.momentum.rsi(df['close'], window=14)
        
        macd = ta.trend.MACD(df['close'])
        df['macd_hist'] = macd.macd_diff() 
        
        current = df.iloc[-1]
        current_price = current['close']
        
        trend_sig = "HOLD"
        if current['ema_short'] > current['ema_long'] and current['macd_hist'] > 0 and current['rsi'] < 65:
            trend_sig = "BUY"
        elif current['ema_short'] < current['ema_long'] and current['macd_hist'] < 0:
            trend_sig = "SELL" 

        grid_sig = "HOLD"
        if current['rsi'] < 30: grid_sig = "BUY"  
        elif current['rsi'] > 70: grid_sig = "SELL" 
        
        temp = 20
        if current['ema_short'] > current['ema_long']: temp += 10
        if current['macd_hist'] > 0: temp += 5
        if current['rsi'] > 50: temp += 5
        
        state = "상승장(불장)" if temp >= 30 else "하락/조정장" if temp <= 20 else "보합세"
        
        return trend_sig, grid_sig, current_price, temp, state, current['rsi']
    
    except Exception as e:
        return "ERROR", "ERROR", 0, 20, f"데이터 수집 에러: {e}", 50

# --- [메인 봇 실행 로직] ---
def run_trading_bot():
    try:
        now = datetime.now().strftime('%H:%M:%S')
        now_ts = time.time()
        symbol = 'BTC/KRW'
        
        FEE_RATE = 0.001 
        USDT_KRW = get_realtime_exchange_rate() 
        trend_sig, grid_sig, krw_price, market_temp, market_state, rsi = decide_trade(symbol)
        
        if krw_price == 0: return 
            
        try:
            binance_ticker = binance_live.fetch_ticker('BTC/USDT')
            binance_price = binance_ticker['last']
            premium_pct = (krw_price / (binance_price * USDT_KRW) - 1) * 100
            diff_krw = krw_price - (binance_price * USDT_KRW)
        except:
            binance_price, premium_pct, diff_krw = 0, 0, 0

        # ==========================================
        # ★ 원격 제어 (수동 매매) 클라우드 명령 확인 로직
        # ==========================================
        try:
            cmds = supabase.table('bot_commands').select('*').eq('is_executed', False).execute()
            for cmd in cmds.data:
                action = cmd.get("action")
                amount_krw = float(cmd.get("amount_krw", 10000))
                
                trade_amount = round(amount_krw / krw_price, 4) if krw_price > 0 else 0.001
                if trade_amount < 0.001: trade_amount = 0.001 
                
                if action == "BUY" and not bot_state['is_holding']:
                    binance_sandbox.create_market_buy_order('BTC/USDT', trade_amount)
                    bot_state['is_holding'] = True
                    bot_state['buy_price'] = krw_price
                    print(f"🔴 [원격 수동 매수 완료] 금액: {amount_krw:,}원")
                    
                elif action == "SELL" and bot_state['is_holding']:
                    binance_sandbox.create_market_sell_order('BTC/USDT', trade_amount)
                    
                    gross_profit_krw = (krw_price - bot_state['buy_price']) * trade_amount
                    fee_krw = (bot_state['buy_price'] * trade_amount * FEE_RATE) + (krw_price * trade_amount * FEE_RATE)
                    net_profit_krw = gross_profit_krw - fee_krw
                    net_profit_rate = (net_profit_krw / (bot_state['buy_price'] * trade_amount)) * 100
                    
                    old_buy_price = bot_state['buy_price'] 
                    bot_state['is_holding'] = False
                    bot_state['total_trades'] += 1
                    bot_state['profits'].append(net_profit_rate)
                    bot_state['cool_down_until'] = time.time() + 180 
                    
                    print(f"🔵 [원격 수동 매도 완료] 순수익률: {net_profit_rate:.2f}%")
                    
                    history_data = {
                        "time": now, "buy_price": old_buy_price, "sell_price": krw_price,
                        "trade_amount": trade_amount, "profit_krw": net_profit_krw,
                        "profit_rate": net_profit_rate, "reason": "원격 수동 매도"
                    }
                    supabase.table('trade_history').insert(history_data).execute()
                
                supabase.table('bot_commands').update({'is_executed': True}).eq('id', cmd['id']).execute()
        except Exception as e:
            pass

        # 잔고 조회 로직
        try:
            balance_binance = binance_sandbox.fetch_balance()
            usdt_bal, btc_bal = balance_binance['free'].get('USDT', 0), balance_binance['free'].get('BTC', 0)
        except: usdt_bal, btc_bal = 0, 0

        try:
            balance_upbit = exchange.fetch_balance()
            upbit_krw, upbit_btc = balance_upbit['free'].get('KRW', 0), balance_upbit['free'].get('BTC', 0)
        except: upbit_krw, upbit_btc = 0, 0

        net_profit_rate = 0.0
        if bot_state['is_holding']:
            trade_amount_eval = 0.001 
            gross_profit_krw = (krw_price - bot_state['buy_price']) * trade_amount_eval
            fee_krw = (bot_state['buy_price'] * trade_amount_eval * FEE_RATE) + (krw_price * trade_amount_eval * FEE_RATE)
            net_profit_krw = gross_profit_krw - fee_krw
            net_profit_rate = (net_profit_krw / (bot_state['buy_price'] * trade_amount_eval)) * 100

        # 상태값 구성
        status_data = {
            "time": now, "price": krw_price, "binance_price": binance_price,
            "premium_pct": premium_pct, "diff_krw": diff_krw, "temp": market_temp,
            "state": market_state, "rsi": rsi, "is_holding": bot_state['is_holding'],
            "buy_price": bot_state['buy_price'], "current_profit": net_profit_rate,
            "usdt_bal": usdt_bal, "btc_bal": btc_bal, "upbit_krw": upbit_krw,
            "upbit_btc": upbit_btc, "usdt_krw_rate": USDT_KRW
        }

        # ==========================================
        # ★ [핵심 버그 픽스] 봇 상태를 DB에 쏘기
        # ==========================================
        try:
            # update -> upsert 로 변경: 데이터가 없으면 새로 1번 방을 파서 넣고, 있으면 덮어씁니다!
            supabase.table('bot_status').upsert({'id': 1, 'status_data': status_data}).execute()
        except Exception as e:
            print(f"⚠️ DB 전송 에러: {e}") # 이제 전송 실패시 터미널에 빨간불 띄워줍니다

        # 터미널 출력
        if not bot_state['is_holding'] and now_ts < bot_state['cool_down_until']:
            print(f"[{now}] 📡 UPBIT: {krw_price:,.0f}원 | ⏳ 쿨다운 대기 중... ({int(bot_state['cool_down_until'] - now_ts)}초 남음)")
        else:
            print(f"[{now}] 📡 UPBIT: {krw_price:,.0f}원 | 김프: {premium_pct:.2f}% | 🌡️ {market_temp}도")
            if bot_state['is_holding']:
                color_code = "\033[31m" if net_profit_rate >= 0 else "\033[34m"
                print(f" 💼 [보유 중] 순수익률: {color_code}{net_profit_rate:+.2f}%\033[0m")

        # === [자동 매수/매도 로직 V2] ===
        trade_amount = 0.001 
        
        if not bot_state['is_holding']:
            if now_ts >= bot_state['cool_down_until']:
                if trend_sig == "BUY" or grid_sig == "BUY":
                    binance_sandbox.create_market_buy_order('BTC/USDT', trade_amount)
                    bot_state['is_holding'] = True
                    bot_state['buy_price'] = krw_price
                    print(f"🚀 자동 매수 완료: {krw_price:,.0f} KRW (추세/MACD:{trend_sig} | RSI: {rsi:.1f})")
        else:
            should_sell = False
            reason = ""
            if net_profit_rate >= 0.35: should_sell, reason = True, "목표 달성 익절"
            elif net_profit_rate <= -0.40: should_sell, reason = True, "안전 손절"
            elif grid_sig == "SELL": should_sell, reason = True, "RSI 과매수 탈출"
            elif trend_sig == "SELL":
                if net_profit_rate > 0.1: should_sell, reason = True, "추세 꺾임 (안전 익절)"
                elif net_profit_rate <= -0.2: should_sell, reason = True, "추세 꺾임 (방어 손절)"

            if should_sell:
                binance_sandbox.create_market_sell_order('BTC/USDT', trade_amount)
                
                gross_profit_krw = (krw_price - bot_state['buy_price']) * trade_amount
                fee_krw = (bot_state['buy_price'] * trade_amount * FEE_RATE) + (krw_price * trade_amount * FEE_RATE)
                net_profit_krw = gross_profit_krw - fee_krw
                old_buy_price = bot_state['buy_price']
                
                bot_state['is_holding'] = False
                bot_state['total_trades'] += 1
                bot_state['profits'].append(net_profit_rate)
                bot_state['cool_down_until'] = time.time() + 180
                
                print(f"💰 자동 매도 완료 [{reason}] 최종 순수익률: {net_profit_rate:.2f}% (※ 3분 쿨다운)")
                
                history_data = {
                    "time": now, "buy_price": old_buy_price, "sell_price": krw_price,
                    "trade_amount": trade_amount, "profit_krw": net_profit_krw,
                    "profit_rate": net_profit_rate, "reason": reason
                }
                try:
                    supabase.table('trade_history').insert(history_data).execute()
                except Exception as e:
                    print("DB 저장 실패:", e)

    except Exception as e:
        pass

if __name__ == "__main__":
    print("🚀 하이브리드 추세추종 봇 V3 (클라우드 DB 버전) 시작...")
    if test_sandbox_connection():
        init_clean_state()
        try:
            while True:
                run_trading_bot()
                time.sleep(1.5) 
        except KeyboardInterrupt:
            sys.exit()
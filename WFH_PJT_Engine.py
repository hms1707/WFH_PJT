import ccxt
import time
import sys
from datetime import datetime
import pandas as pd
import ta
import json
import os
import urllib.request 

# ==========================================
# 1. 거래소 객체 초기화 (API 키 설정)
# ==========================================
# ★ 업비트 잔고 조회를 위해 발급받으신 API 키를 아래에 입력해 주세요!
exchange = ccxt.upbit({
    'apiKey': ' ',  # 예: 'x8...a9'
    'secret': ' ',  # 예: 'Yq...3z'
    'enableRateLimit': True
}) 

binance_live = ccxt.binance({'enableRateLimit': True}) 
binance_sandbox = ccxt.binance({
    'apiKey': ' ',
    'secret': ' ',
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

def show_final_report():
    print("\n" + "="*40)
    print("📊 최종 거래 성적표")
    print(f"⏱️ 가동 시간: {datetime.now() - bot_state['start_time']}")
    print(f"🔄 총 거래 횟수: {bot_state['total_trades']}회")
    
    if bot_state['profits']:
        total_profit = sum(bot_state['profits'])
        avg_profit = total_profit / len(bot_state['profits'])
        print(f"📈 평균 순수익률: {avg_profit:.2f}%")
        print(f"💰 누적 순수익률(단순합): {total_profit:.2f}%")
    else:
        print("📉 거래된 내역이 없습니다.")
    print("="*40 + "\n")

# --- [제어 센터: 시장 분석 및 판단 엔진 V2] ---
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
        
        if krw_price == 0:
            return 
            
        try:
            binance_ticker = binance_live.fetch_ticker('BTC/USDT')
            binance_price = binance_ticker['last']
            premium_pct = (krw_price / (binance_price * USDT_KRW) - 1) * 100
            diff_krw = krw_price - (binance_price * USDT_KRW)
        except Exception:
            binance_price = 0
            premium_pct = 0
            diff_krw = 0

        bot_state['temps'].append(market_temp)
        
        if not bot_state['is_holding'] and now_ts < bot_state['cool_down_until']:
            cd_remain = int(bot_state['cool_down_until'] - now_ts)
            print(f"[{now}] 📡 UPBIT: {krw_price:,.0f}원 | BINANCE: ${binance_price:,.2f} | ⏳ 쿨다운 대기 중... ({cd_remain}초 남음)")
        else:
            print(f"[{now}] 📡 UPBIT: {krw_price:,.0f}원 | BINANCE: ${binance_price:,.2f} | 김프: {premium_pct:.2f}% | 🌡️ {market_temp}도")

        # ==========================================
        # ★ 잔고 조회 로직
        # ==========================================
        # 1. 바이낸스 샌드박스 잔고
        try:
            balance_binance = binance_sandbox.fetch_balance()
            usdt_bal = balance_binance['free'].get('USDT', 0)
            btc_bal = balance_binance['free'].get('BTC', 0)
        except Exception:
            usdt_bal = 0
            btc_bal = 0

        # 2. 업비트 실제 잔고 (API 키가 없으면 0 반환)
        try:
            balance_upbit = exchange.fetch_balance()
            upbit_krw = balance_upbit['free'].get('KRW', 0)
            upbit_btc = balance_upbit['free'].get('BTC', 0)
        except Exception:
            upbit_krw = 0
            upbit_btc = 0

        net_profit_rate = 0.0
        if bot_state['is_holding']:
            trade_amount_eval = 0.001 
            gross_profit_krw = (krw_price - bot_state['buy_price']) * trade_amount_eval
            fee_krw = (bot_state['buy_price'] * trade_amount_eval * FEE_RATE) + (krw_price * trade_amount_eval * FEE_RATE)
            net_profit_krw = gross_profit_krw - fee_krw
            net_profit_rate = (net_profit_krw / (bot_state['buy_price'] * trade_amount_eval)) * 100

        # JSON에 업비트 정보와 실시간 환율 정보 추가!
        status_data = {
            "time": now,
            "price": krw_price,
            "binance_price": binance_price,
            "premium_pct": premium_pct,
            "diff_krw": diff_krw,
            "temp": market_temp,
            "state": market_state,
            "rsi": rsi,
            "is_holding": bot_state['is_holding'],
            "buy_price": bot_state['buy_price'],
            "current_profit": net_profit_rate,
            "usdt_bal": usdt_bal,
            "btc_bal": btc_bal,
            "upbit_krw": upbit_krw,         # ★ 업비트 원화
            "upbit_btc": upbit_btc,         # ★ 업비트 코인
            "usdt_krw_rate": USDT_KRW       # ★ 실시간 환율 적용
        }

        # === [수동 매매 명령 처리] ===
        cmd_file = "manual_cmd.json"
        if os.path.exists(cmd_file):
            try:
                with open(cmd_file, "r", encoding="utf-8") as f:
                    cmd = json.load(f)
                os.remove(cmd_file) 
                
                action = cmd.get("action")
                amount_krw = cmd.get("amount_krw", 10000)
                
                trade_amount = round(amount_krw / krw_price, 4) if krw_price > 0 else 0.001
                if trade_amount < 0.001: trade_amount = 0.001 
                
                if action == "BUY" and not bot_state['is_holding']:
                    binance_sandbox.create_market_buy_order('BTC/USDT', trade_amount)
                    bot_state['is_holding'] = True
                    bot_state['buy_price'] = krw_price
                    print(f"🔴 [수동 매수 완료] 금액: {amount_krw:,}원 (약 {trade_amount} BTC)")
                    
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
                    
                    print(f"🔵 [수동 매도 완료] 순수익률: {net_profit_rate:.2f}% (※ 3분간 매수 금지)")
                    
                    history_exists = os.path.isfile("trade_history.csv")
                    with open("trade_history.csv", "a", encoding="utf-8") as f:
                        if not history_exists:
                            f.write("time,buy_price,sell_price,trade_amount,profit_krw,profit_rate,reason\n")
                        f.write(f"{now},{old_buy_price},{krw_price},{trade_amount},{net_profit_krw:.0f},{net_profit_rate:.2f},수동 매도(테스트)\n")
            except Exception as e:
                print(f"수동 명령 처리 중 에러: {e}")

        # === [자동 매수/매도 로직 V2] ===
        trade_amount = 0.001 
        
        if not bot_state['is_holding']:
            if now_ts < bot_state['cool_down_until']:
                pass 
            else:
                if trend_sig == "BUY" or grid_sig == "BUY":
                    binance_sandbox.create_market_buy_order('BTC/USDT', trade_amount)
                    bot_state['is_holding'] = True
                    bot_state['buy_price'] = krw_price
                    print(f"🚀 자동 매수 완료: {krw_price:,.0f} KRW (추세/MACD:{trend_sig} | RSI: {rsi:.1f})")
        
        else:
            color_code = "\033[31m" if net_profit_rate >= 0 else "\033[34m"
            print(f" 💼 [보유 중] 순수익률(수수료 차감 후): {color_code}{net_profit_rate:+.2f}%\033[0m")
            
            should_sell = False
            reason = ""
            
            if net_profit_rate >= 0.35:
                should_sell = True
                reason = "목표 달성 익절"
            elif net_profit_rate <= -0.40:
                should_sell = True
                reason = "안전 손절"
            elif grid_sig == "SELL":
                should_sell = True
                reason = "RSI 과매수 탈출"
            elif trend_sig == "SELL":
                if net_profit_rate > 0.1: 
                    should_sell = True
                    reason = "추세 꺾임 (안전 익절)"
                elif net_profit_rate <= -0.2: 
                    should_sell = True
                    reason = "추세 꺾임 (방어 손절)"

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
                
                history_exists = os.path.isfile("trade_history.csv")
                with open("trade_history.csv", "a", encoding="utf-8") as f:
                    if not history_exists:
                        f.write("time,buy_price,sell_price,trade_amount,profit_krw,profit_rate,reason\n")
                    f.write(f"{now},{old_buy_price},{krw_price},{trade_amount},{net_profit_krw:.0f},{net_profit_rate:.2f},{reason}\n")
                    
        with open("bot_status.json", "w", encoding="utf-8") as f:
            json.dump(status_data, f, ensure_ascii=False)

    except Exception as e:
        print(f"시스템 에러: {e}")

if __name__ == "__main__":
    print("🚀 하이브리드 추세추종 봇 V2 시작...")
    if test_sandbox_connection():
        init_clean_state()
        try:
            while True:
                run_trading_bot()
                time.sleep(1) 
        except KeyboardInterrupt:
            print("\n🛑 봇 종료 신호 감지! 통계를 계산합니다...")
            show_final_report()
            sys.exit()
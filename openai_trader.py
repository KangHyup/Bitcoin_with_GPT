import os
import json
import logging
from binance.client import Client
from dotenv import load_dotenv

import openai

load_dotenv()

# 바이낸스 API 키 로드
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

# 바이낸스 클라이언트 초기화 (Spot + Futures 겸용)
# 하나의 Client로도 선물 주문이 가능합니다.
client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

# 로깅 설정
logging.basicConfig(
    filename='openai_trader.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s'
)

def calculate_order_quantity(symbol, usdt_amount):
    """
    Spot 매수시, 지정된 USDT 금액으로 매수할 수 있는 BTC 수량을 계산하는 함수.
    바이낸스의 최소 주문 단위를 고려합니다.
    """
    try:
        # 심볼 정보 조회 (Spot 기준)
        symbol_info = client.get_symbol_info(symbol)
        step_size = 0.000001
        min_qty = 0.000001
        for f in symbol_info['filters']:
            if f['filterType'] == 'LOT_SIZE':
                step_size = float(f['stepSize'])
                min_qty = float(f['minQty'])
                break

        ticker = client.get_symbol_ticker(symbol=symbol)
        current_price = float(ticker['price']) if 'price' in ticker else 0
        if current_price == 0:
            return 0

        quantity = usdt_amount / current_price
        quantity = (quantity // step_size) * step_size

        if quantity < min_qty:
            logging.warning(f"매수하려는 수량 {quantity} BTC가 최소 주문 수량 {min_qty}보다 작습니다.")
            return 0

        return round(quantity, 8)
    except Exception as e:
        logging.error(f"Spot 매수 수량 계산 중 오류 발생: {e}")
        return 0

def calculate_futures_quantity(symbol, usdt_amount):
    """
    Futures (선물) 롱/숏 진입시, 지정된 USDT 금액을 활용해 시장가로 진입할 때의 계약 수량을 추정.
    바이낸스 선물 거래는 '거래 단위'가 현물과 같지만(1 BTC), 
    레버리지 고려 시 자금 대비 포지션 규모가 달라질 수 있음.
    여기서는 레버리지 1배이므로 Spot 계산과 거의 유사하지만,
    별도의 최소 수량/스텝 사이즈가 존재합니다.
    """
    try:
        # 선물 심볼 정보 조회 (Futures API)
        # python-binance >= 1.0.10 이상 버전이면 아래처럼 futures_exchange_info 사용 가능
        futures_info = client.futures_exchange_info()
        step_size = 0.000001
        min_qty = 0.000001

        for sinfo in futures_info["symbols"]:
            if sinfo["symbol"] == symbol:
                for filt in sinfo["filters"]:
                    if filt["filterType"] == "LOT_SIZE":
                        step_size = float(filt["stepSize"])
                        min_qty = float(filt["minQty"])
                break

        # 현재 선물 가격 조회 (공유된 티커를 그대로 사용 가능)
        # BTCUSDT 선물은 스펙상 현물과 거의 동일한 가격 참조
        ticker = client.futures_symbol_ticker(symbol=symbol)
        current_price = float(ticker['price']) if 'price' in ticker else 0
        if current_price == 0:
            return 0

        # 1배 레버리지는 Spot과 동일하지만, 여기선 같은 로직으로 계산
        quantity = usdt_amount / current_price
        quantity = (quantity // step_size) * step_size

        if quantity < min_qty:
            logging.warning(f"선물 포지션 진입수량 {quantity} BTC < 최소 주문수량 {min_qty}.")
            return 0

        return round(quantity, 8)
    except Exception as e:
        logging.error(f"Futures 포지션 수량 계산 오류: {e}")
        return 0

def set_isolated_margin_and_leverage(symbol):
    """
    Futures에 대해 Isolated 모드와 레버리지를 x1로 설정하는 함수.
    이미 이 설정이 되어있으면 오류가 발생할 수 있으니, 예외처리로 잡음.
    """
    try:
        # 마진 모드 설정
        client.futures_change_margin_type(
            symbol=symbol,
            marginType="ISOLATED"
        )
        logging.info(f"{symbol} 선물 마진모드: ISOLATED 설정 완료.")
    except Exception as e:
        logging.warning(f"{symbol} 선물 마진모드 설정 중 오류/이미 설정됨: {e}")

    try:
        # 레버리지 설정 (1배)
        client.futures_change_leverage(
            symbol=symbol,
            leverage=1
        )
        logging.info(f"{symbol} 레버리지 1배 설정 완료.")
    except Exception as e:
        logging.warning(f"{symbol} 레버리지 설정 중 오류/이미 설정됨: {e}")

def execute_trade(decision, reason, symbol="BTCUSDT"):
    """
    다섯 가지 결정 (long, short, buy, sell, hold)에 따라 
    BTCUSDT 선물 혹은 현물 거래를 실행한다.
    마진모드는 Isolated, 레버리지 1배로 고정.
    
    Parameters:
        decision (str): "long", "short", "buy", "sell", "hold"
        reason (str): 매매 결정 이유
        symbol (str): 기본값 "BTCUSDT"
    """
    try:
        # 공통: Spot 계좌 잔고, Futures 지갑 잔고 등을 각각 조회할 수도 있음
        # 일단은 Spot 잔고만 예시로 가져옴
        account_info = client.get_account()
        balances = {
            bal['asset']: float(bal['free'])
            for bal in account_info['balances']
            if float(bal['free']) > 0
        }
        my_usdt_spot = balances.get("USDT", 0)

        # 선물 지갑 잔고 조회 (Futures)
        # 예: client.futures_account_balance() 등
        # 여기선 간단히 임의로 100 USDT 있다고 가정
        my_usdt_futures = 100.0

        # =========================
        # 1) LONG 포지션 진입
        # =========================
        if decision == "long":
            set_isolated_margin_and_leverage(symbol)
            # USDT를 얼마나 사용할지 결정 (예: 전액 or 일부)
            use_amount = my_usdt_futures  # 예: 100 USDT 전부
            qty = calculate_futures_quantity(symbol, use_amount)
            if qty > 0:
                print(">>> LONG (Futures) BTCUSDT")
                try:
                    # LONG 포지션: side=BUY, positionSide=LONG
                    order = client.futures_create_order(
                        symbol=symbol,
                        side="BUY",
                        positionSide="LONG",
                        type="MARKET",
                        quantity=qty
                    )
                    logging.info(f"롱 포지션 주문 실행: {order}")
                    print(order)
                    print("long reason:", reason)
                except Exception as e:
                    logging.error(f"롱 포지션 주문 오류: {e}")
                    print(f"롱 포지션 주문 오류: {e}")
            else:
                print("롱 포지션 진입 실패: 수량 0")
                logging.info("롱 포지션 진입 실패: 수량 0")

        # =========================
        # 2) SHORT 포지션 진입
        # =========================
        elif decision == "short":
            set_isolated_margin_and_leverage(symbol)
            use_amount = my_usdt_futures
            qty = calculate_futures_quantity(symbol, use_amount)
            if qty > 0:
                print(">>> SHORT (Futures) BTCUSDT")
                try:
                    # SHORT 포지션: side=SELL, positionSide=SHORT
                    order = client.futures_create_order(
                        symbol=symbol,
                        side="SELL",
                        positionSide="SHORT",
                        type="MARKET",
                        quantity=qty
                    )
                    logging.info(f"숏 포지션 주문 실행: {order}")
                    print(order)
                    print("short reason:", reason)
                except Exception as e:
                    logging.error(f"숏 포지션 주문 오류: {e}")
                    print(f"숏 포지션 주문 오류: {e}")
            else:
                print("숏 포지션 진입 실패: 수량 0")
                logging.info("숏 포지션 진입 실패: 수량 0")

        # =========================
        # 3) BUY (Spot)
        # =========================
        elif decision == "buy":
            # 현물 계좌 USDT 잔고가 10 USDT 이상일 때 매수
            if my_usdt_spot >= 10:
                qty = calculate_order_quantity(symbol, my_usdt_spot * 0.9995)
                if qty > 0:
                    print(">>> BUY (Spot) BTCUSDT")
                    try:
                        buy_order = client.order_market_buy(
                            symbol=symbol,
                            quantity=qty
                        )
                        logging.info(f"현물 매수 주문 실행: {buy_order}")
                        print(buy_order)
                        print("buy reason:", reason)
                    except Exception as e:
                        logging.error(f"현물 매수 주문 오류: {e}")
                        print(f"현물 매수 주문 오류: {e}")
                else:
                    print("매수할 수량이 부족합니다.")
                    logging.info("매수할 수량이 부족합니다.")
            else:
                print("매수불가: 보유 USDT가 10 USDT 미만.")
                logging.info("매수 조건 미충족: USDT 잔고 부족.")

        # =========================
        # 4) SELL (Spot)
        # =========================
        elif decision == "sell":
            # 현물 계좌 BTC 잔고 조회
            my_btc_spot = balances.get("BTC", 0)
            if my_btc_spot >= 0.0001:
                print(">>> SELL (Spot) BTCUSDT")
                try:
                    sell_order = client.order_market_sell(
                        symbol=symbol,
                        quantity=my_btc_spot
                    )
                    logging.info(f"현물 매도 주문 실행: {sell_order}")
                    print(sell_order)
                    print("sell reason:", reason)
                except Exception as e:
                    logging.error(f"현물 매도 주문 오류: {e}")
                    print(f"현물 매도 주문 오류: {e}")
            else:
                print("매도불가: 보유 BTC가 0.0001 미만.")
                logging.info("매도 조건 미충족: BTC 잔고 부족.")

        # =========================
        # 5) HOLD
        # =========================
        else:
            print("hold:", reason)
            logging.info("매매 결정: hold")

    except Exception as e:
        logging.error(f"매매 로직 실행 중 오류 발생: {e}")
        print(f"매매 로직 실행 중 오류 발생: {e}")


#######################
# 예: Vision API 로직 #
#######################
def get_ai_decision_with_chart(optimized_data):
    """
    Vision 모델을 사용해 AI에게 매매 결정을 요청하는 함수 예시.
    (별도 구현 필요 시)
    """
    # 예) OPENAI_API_KEY 준비
    openai_api_key = os.getenv("OPENAI_API_KEY")
    openai.api_key = openai_api_key

    # 예시 prompt / 메시지 구성
    system_prompt = (
        "You are a crypto trading assistant with vision. "
        "Analyze the user-provided chart image and other data, then decide: long/short/buy/sell/hold."
    )
    text_content = json.dumps(optimized_data, ensure_ascii=False, indent=2)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Here is the crypto data:\n{text_content}\n Please output a JSON with 'decision' and 'reason'."}
    ]

    # (필요 시 chart_image base64 -> data:image/png;base64,... 형식 Vision에 전달)
    # ...

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages,
            max_tokens=500
        )
        ai_answer = response.choices[0].message.content.strip()
        logging.info(f"[AI Raw Answer]: {ai_answer}")
    except Exception as e:
        logging.error(f"OpenAI API 요청 중 오류: {e}")
        return ("hold", "OpenAI API 오류")

    # JSON 파싱
    try:
        ai_result = json.loads(ai_answer)
        decision = ai_result.get("decision", "hold").lower()
        reason = ai_result.get("reason", "No reason provided.")
    except:
        decision = "hold"
        reason = ai_answer

    return (decision, reason)

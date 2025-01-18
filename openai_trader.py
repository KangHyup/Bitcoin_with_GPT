# openai_trader.py
# 데이터를 기반으로 프롬프트를 작성해 실제 코인을 매매 (바이낸스 API 기반)

import os
import json
import openai
import logging
from binance.client import Client
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 바이낸스 API 키 및 시크릿 로드
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

# OpenAI API 키 로드
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# 바이낸스 클라이언트 초기화
client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

# 로깅 설정
logging.basicConfig(
    filename='openai_trader.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s'
)

def calculate_order_quantity(symbol, usdt_amount):
    """
    지정된 USDT 금액으로 매수할 수 있는 BTC 수량을 계산하는 함수.
    바이낸스의 최소 주문 단위를 고려합니다.
    
    Parameters:
        symbol (str): 거래 심볼 (예: "BTCUSDT")
        usdt_amount (float): 매수에 사용할 USDT 금액
    
    Returns:
        float: 매수할 BTC 수량
    """
    try:
        # 심볼의 정보 조회
        symbol_info = client.get_symbol_info(symbol)
        step_size = 0.000001  # 기본 step size (바이낸스의 최소 주문 단위에 맞게 설정)
        min_qty = 0.000001
        for filter in symbol_info['filters']:
            if filter['filterType'] == 'LOT_SIZE':
                step_size = float(filter['stepSize'])
                min_qty = float(filter['minQty'])
                break

        # BTC 가격 조회
        ticker = client.get_symbol_ticker(symbol=symbol)
        current_price = float(ticker['price']) if 'price' in ticker else 0

        if current_price == 0:
            return 0

        # 매수할 BTC 수량 계산
        quantity = usdt_amount / current_price

        # step size에 맞게 수량 조정
        quantity = (quantity // step_size) * step_size

        # 최소 주문 수량 이상인지 확인
        if quantity < min_qty:
            logging.warning(f"매수하려는 수량 {quantity} BTC가 최소 주문 수량 {min_qty} BTC보다 작습니다.")
            return 0

        return round(quantity, 8)  # 소수점 8자리까지 반올림

    except Exception as e:
        logging.error(f"매수 수량 계산 중 오류 발생: {e}")
        return 0

def send_to_openai_and_trade(data_for_ai):
    """
    1. data_for_ai를 OpenAI API에 전송
    2. AI 응답(JSON)에서 매매 결정을 파싱
    3. 바이낸스 매매 로직 실행
    """
    # ---------------------------
    # (1) 프롬프트 불러오기 (시스템 메시지)
    # ---------------------------
    try:
        with open("gpt_prompt.txt", "r", encoding="utf-8") as f:
            system_prompt = f.read()
        logging.info("gpt_prompt.txt 로드 완료.")
    except FileNotFoundError:
        system_prompt = (
            "You are a helpful assistant. You will receive crypto data and respond with a buy/sell/hold decision."
        )
        logging.warning("gpt_prompt.txt 파일을 찾을 수 없어 기본 프롬프트 사용.")

    # ---------------------------
    # (2) OpenAI Chat API 호출
    # ---------------------------
    user_content = json.dumps(data_for_ai, ensure_ascii=False)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",  # 또는 "gpt-3.5-turbo"
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Analyze the following crypto data and provide buy/sell/hold decision.\n{user_content}"}
            ],
            max_tokens=200  # 응답 토큰 수 제한
        )
        ai_answer = response.choices[0].message.content.strip()
        logging.info("OpenAI API 응답 수신 완료.")
        print("[AI Raw Answer]", ai_answer)
    except Exception as e:
        logging.error(f"OpenAI API 요청 중 오류 발생: {e}")
        print(f"OpenAI API 요청 중 오류 발생: {e}")
        return

    # ---------------------------
    # (3) AI 응답 파싱 (JSON 가정)
    # ---------------------------
    # 예: {"decision":"buy","reason":"단기 추세 반등 예상"}
    try:
        ai_result = json.loads(ai_answer)
        decision = ai_result.get("decision", "hold").lower()
        reason = ai_result.get("reason", "No reason provided.")
        logging.info(f"AI 결정: {decision}, 이유: {reason}")
    except json.JSONDecodeError:
        decision = "hold"
        reason = "JSON 파싱 실패"
        logging.warning("AI 응답을 JSON으로 파싱하는 데 실패했습니다.")
    except Exception as e:
        decision = "hold"
        reason = "Error parsing AI response"
        logging.error(f"AI 응답 파싱 중 오류 발생: {e}")

    # ---------------------------
    # (4) 매매 로직 실행
    # ---------------------------
    try:
        # 바이낸스 잔고 조회
        account_info = client.get_account()
        balances = {balance['asset']: float(balance['free']) for balance in account_info['balances'] if float(balance['free']) > 0}

        # USDT와 BTC 잔고 확인
        my_usdt = balances.get("USDT", 0)
        my_btc = balances.get("BTC", 0)

        # 현재 BTCUSDT 가격 조회
        ticker = client.get_symbol_ticker(symbol="BTCUSDT")
        current_price = float(ticker['price']) if 'price' in ticker else 0
        logging.info(f"현재 BTCUSDT 가격: {current_price}")

        if decision == "buy":
            # USDT 잔고가 10 USDT 이상일 때 매수 (바이낸스에서는 최소 주문량이 있으므로 10 USDT로 설정)
            if my_usdt >= 10:
                order_quantity = calculate_order_quantity("BTCUSDT", my_usdt * 0.9995)  # 수수료 고려
                if order_quantity > 0:
                    print(">>> BUY (market order) BTCUSDT")
                    try:
                        buy_order = client.order_market_buy(
                            symbol="BTCUSDT",
                            quantity=order_quantity
                        )
                        logging.info(f"매수 주문 실행: {buy_order}")
                        print(buy_order)
                        print("buy reason:", reason)
                    except Exception as e:
                        logging.error(f"매수 주문 중 오류 발생: {e}")
                        print(f"매수 주문 중 오류 발생: {e}")
                else:
                    print("매수할 수량이 부족합니다.")
                    logging.info("매수할 수량이 부족합니다.")

            else:
                print("매수불가 : 보유 USDT가 10 USDT 미만입니다.")
                logging.info("매수 조건 미충족: USDT 잔고 부족.")

        elif decision == "sell":
            # BTC 잔고가 0.0001 BTC 이상일 때 매도 (바이낸스에서는 최소 주문량이 있으므로 0.0001 BTC로 설정)
            if my_btc >= 0.0001:
                print(">>> SELL (market order) BTCUSDT")
                try:
                    sell_order = client.order_market_sell(
                        symbol="BTCUSDT",
                        quantity=my_btc
                    )
                    logging.info(f"매도 주문 실행: {sell_order}")
                    print(sell_order)
                    print("sell reason:", reason)
                except Exception as e:
                    logging.error(f"매도 주문 중 오류 발생: {e}")
                    print(f"매도 주문 중 오류 발생: {e}")
            else:
                print("매도불가 : 보유 BTC가 0.0001 BTC 미만입니다.")
                logging.info("매도 조건 미충족: BTC 잔고 부족.")

        else:
            # hold 상태면 아무 매매도 하지 않는다
            print("hold:", reason)
            logging.info("매매 결정: hold")

    except Exception as e:
        logging.error(f"매매 로직 실행 중 오류 발생: {e}")
        print(f"매매 로직 실행 중 오류 발생: {e}")

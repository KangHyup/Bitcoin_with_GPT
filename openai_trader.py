# openai_trader.py
# 매매 결정을 받아 바이낸스 API를 통해 실제 거래를 실행

import os
import json
import logging
from binance.client import Client
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 바이낸스 API 키 및 시크릿 로드
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

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

def execute_trade(decision, reason, symbol="BTCUSDT"):
    """
    매매 결정을 받아 바이낸스 API를 통해 매수/매도/hold를 실행하는 함수.

    Parameters:
        decision (str): "buy", "sell", "hold"
        reason (str): 매매 결정의 이유
        symbol (str): 거래 심볼 (기본값: "BTCUSDT")

    Returns:
        None
    """
    try:
        # 바이낸스 잔고 조회
        account_info = client.get_account()
        balances = {balance['asset']: float(balance['free']) for balance in account_info['balances'] if float(balance['free']) > 0}

        # USDT와 BTC 잔고 확인
        my_usdt = balances.get("USDT", 0)
        my_btc = balances.get("BTC", 0)

        # 현재 BTCUSDT 가격 조회
        ticker = client.get_symbol_ticker(symbol=symbol)
        current_price = float(ticker['price']) if 'price' in ticker else 0
        logging.info(f"현재 BTCUSDT 가격: {current_price}")

        if decision == "buy":
            # USDT 잔고가 10 USDT 이상일 때 매수 (바이낸스에서는 최소 주문량이 있으므로 10 USDT로 설정)
            if my_usdt >= 10:
                order_quantity = calculate_order_quantity(symbol, my_usdt * 0.9995)  # 수수료 고려
                if order_quantity > 0:
                    print(">>> BUY (market order) BTCUSDT")
                    try:
                        buy_order = client.order_market_buy(
                            symbol=symbol,
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
                        symbol=symbol,
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

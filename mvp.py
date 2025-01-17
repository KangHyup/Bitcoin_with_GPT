import os
import time
import json
from dotenv import load_dotenv
import pyupbit

#ta라이브러리
import pandas as pd
from ta.trend import SMAIndicator
from ta.momentum import RSIIndicator

# .env 파일에서 환경 변수를 불러옵니다.
load_dotenv()

# 업비트 로그인
access = os.getenv("UPBIT_ACCESS_KEY")
secret = os.getenv("UPBIT_SECRET_KEY")
upbit = pyupbit.Upbit(access, secret)


def ai_trading():
    """
    1. 비트코인 90일 일봉 차트 (OHLCV) 불러오기
    2. 공포/탐욕 지수(Fear & Greed Index) API 요청
    3. AI에게 넘길 data_for_ai 구성
    4. (옵션) OpenAI로 넘겨서 매매 판단
    """

    df_90 = pyupbit.get_ohlcv("KRW-BTC", count=90, interval="day")
    df_30 = pyupbit.get_ohlcv("KRW-BTC", count=30, interval="day")
    df_24h = pyupbit.get_ohlcv("KRW-BTC", count=24, interval="minute60")

    # ta 라이브러리 호환을 위해 컬럼명 변경
    df_90 = df_90.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume"
    })

    df_30 = df_30.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume"
    })
    df_24h = df_24h.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume"
    })

    # RSI, SMA 추가
    rsi_30 = RSIIndicator(df_30["Close"], window=14).rsi()
    sma_30 = SMAIndicator(df_30["Close"], window=20).sma_indicator()
    df_30["RSI14"] = rsi_30
    df_30["SMA20"] = sma_30

    rsi_24 = RSIIndicator(df_24h["Close"], window=14).rsi()
    sma_24 = SMAIndicator(df_24h["Close"], window=20).sma_indicator()
    df_24h["RSI14"] = rsi_24
    df_24h["SMA20"] = sma_24

    # (중요) Timestamp 인덱스를 컬럼으로 바꾸고, 혹은 reset_index()
    df_90.reset_index(inplace=True)  
    df_30.reset_index(inplace=True)
    df_24h.reset_index(inplace=True)
    # reset_index()하면 'index' 컬럼이 생기고 그 안에 Timestamp가 들어감

    # 인덱스에 있던 시계열을 문자열로 변환(필요하면 'date' 컬럼으로 이름 변경)
    df_90["index"] = df_90["index"].astype(str)  
    df_30["index"] = df_30["index"].astype(str)
    df_24h["index"] = df_24h["index"].astype(str)

    # 여기서 'index' 대신 'date'라는 컬럼명으로 바꾸면 더 직관적일 수 있음
    df_90.rename(columns={"index": "Date"}, inplace=True)
    df_30.rename(columns={"index": "date"}, inplace=True)
    df_24h.rename(columns={"index": "date"}, inplace=True)

    # 이제 to_dict(orient='records')로 안전하게 변환 가능
    day_90_records = df_90.to_dict(orient='records')
    day_30_records = df_30.to_dict(orient='records')
    hour_24_records = df_24h.to_dict(orient='records')

    # --- (2) 공포/탐욕 지수(Fear & Greed Index) 가져오기 ---
    # 참고: https://api.alternative.me/fng/?limit=1
    fear_greed_url = "https://api.alternative.me/fng/?limit=1"
    try:
        response = requests.get(fear_greed_url, timeout=5)  # 5초 타임아웃 예시
        fng_data = response.json()
        # fng_data 구조 예시:
        # {
        #   "name": "Fear and Greed Index",
        #   "data": [
        #     {
        #       "value": "40",
        #       "value_classification": "Fear",
        #       "timestamp": "1551157200",
        #       "time_until_update": "68499"
        #     }
        #   ],
        #   "metadata": {...}
        # }
        if "data" in fng_data and len(fng_data["data"]) > 0:
            fng_value = fng_data["data"][0].get("value", None)
            fng_classification = fng_data["data"][0].get("value_classification", None)
        else:
            fng_value = None
            fng_classification = None
    except Exception as e:
        print("공포/탐욕 지수 조회 실패:", e)
        fng_value = None
        fng_classification = None

    my_krw = upbit.get_balance("KRW")
    my_btc = upbit.get_balance("KRW-BTC")

    data_for_ai = {
        "balance": {
            "KRW": my_krw,
            "BTC": my_btc
        },
        "chart_data": {
            "day_90": day_90_records,
            "day_30": day_30_records,    # 리스트[각 행 dict]
            "hour_24": hour_24_records
        },
        "fear_greed": {
            "value": fng_value,
            "classification": fng_classification
        }
    }

    # JSON 직렬화 테스트
    # ensure_ascii=False -> 한글이 깨지지 않도록, indent=2 -> 예쁘게 정렬
    json_str = json.dumps(data_for_ai, ensure_ascii=False, indent=2)
    print(json_str)


    # ---------------------------
    # (2) OpenAI API 호출
    # ---------------------------
    # import openai

    # openai.api_key = os.getenv("OPENAI_API_KEY")

    # # 프롬프트(시스템 메시지)를 읽어온다
    # with open("gpt_prompt.txt", "r", encoding="utf-8") as file:
    #     gpt_prompt = file.read()

    # # 실제로는 GPT-3.5나 GPT-4 같은 모델명을 사용
    # # 예시: model="gpt-3.5-turbo" 또는 model="gpt-4"
    # response = openai.ChatCompletion.create(
    #     model="gpt-4",  
    #     messages=[
    #         # system 메시지
    #         {
    #             "role": "system",
    #             "content": gpt_prompt
    #         },
    #         # user 메시지(실제 AI가 분석할 데이터)
    #         {
    #             "role": "user",
    #             "content": json.dumps(data_for_ai, ensure_ascii=False)
    #         }
    #     ]
    # )

    # # ChatGPT의 응답(JSON 문자열 형태 가정)
    # ai_answer = response.choices[0].message.content.strip()
    
    # # 예: {"decision":"buy","reason":"단기 추세 반등 예상"}
    # try:
    #     ai_result = json.loads(ai_answer)
    # except:
    #     # 파싱 실패 시 hold 상태로 처리
    #     ai_result = {"decision": "hold", "reason": "JSON 파싱 실패"}

    # decision = ai_result.get("decision", "hold")
    # reason = ai_result.get("reason", "No reason")

    # print("[AI Decision]", decision, reason)

    # # ---------------------------
    # # (3) 매매 로직 실행
    # # ---------------------------
    # # 수수료 등을 고려해 원화 잔고는 조금 줄인다 (예: *0.9995)
    # my_krw = my_krw * 0.9995

    # if decision == "buy":
    #     # KRW 5,000 이상이면 시장가 매수
    #     if my_krw >= 5000:
    #         print(">>> BUY (market order) KRW-BTC")
    #         buy_result = upbit.buy_market_order("KRW-BTC", my_krw)
    #         print(buy_result)
    #         print("buy reason:", reason)
    #     else:
    #         print("매수불가 : 보유 KRW가 5000원 미만입니다.")

    # elif decision == "sell":
    #     # 내가 가진 BTC 평가 금액이 5,000원 이상인지 확인
    #     current_price = pyupbit.get_orderbook("KRW-BTC")['orderbook_units'][0]["ask_price"]
    #     if (my_btc * current_price) >= 5000:
    #         print(">>> SELL (market order) KRW-BTC")
    #         sell_result = upbit.sell_market_order("KRW-BTC", my_btc)
    #         print(sell_result)
    #         print("sell reason:", reason)
    #     else:
    #         print("매도불가 : 보유 BTC 평가액이 5000원 미만입니다.")

    # else:
    #     # hold 상태면 아무 매매도 하지 않는다
    #     print("hold:", reason)


# 매 10초마다 자동매매 함수를 실행
if __name__ == "__main__":
    #while True:
        ai_trading()
        time.sleep(100000)

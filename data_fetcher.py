# data_fetcher.py

import os
import pyupbit
import requests
import pandas as pd

# 보조지표 ta 라이브러리
from ta.trend import SMAIndicator
from ta.momentum import RSIIndicator

# .env에서 불러오려면 필요
from dotenv import load_dotenv
load_dotenv()

# 업비트 로그인
access = os.getenv("UPBIT_ACCESS_KEY")
secret = os.getenv("UPBIT_SECRET_KEY")
upbit = pyupbit.Upbit(access, secret)


def get_data_for_ai():
    """
    1. 업비트 시세(90일/30일 일봉, 24시간 1시간봉) + 보조지표(RSI/SMA) 계산
    2. 공포/탐욕 지수 가져오기
    3. 잔고 조회
    4. AI에게 넘길 data_for_ai(dict) 반환
    """

    # ---------------------------
    # (1) 업비트 시세 불러오기
    # ---------------------------
    df_90 = pyupbit.get_ohlcv("KRW-BTC", count=90, interval="day")
    df_30 = pyupbit.get_ohlcv("KRW-BTC", count=30, interval="day")
    df_24h = pyupbit.get_ohlcv("KRW-BTC", count=24, interval="minute60")

    # 컬럼명 변경
    df_90.rename(columns={
        "open": "Open", "high": "High", "low": "Low", 
        "close": "Close", "volume": "Volume"}, inplace=True)
    df_30.rename(columns={
        "open": "Open", "high": "High", "low": "Low", 
        "close": "Close", "volume": "Volume"}, inplace=True)
    df_24h.rename(columns={
        "open": "Open", "high": "High", "low": "Low", 
        "close": "Close", "volume": "Volume"}, inplace=True)

    # 보조지표(RSI, SMA) - 30일/24시간만 예시
    df_30["RSI14"] = RSIIndicator(df_30["Close"], window=14).rsi()
    df_30["SMA20"] = SMAIndicator(df_30["Close"], window=20).sma_indicator()

    df_24h["RSI14"] = RSIIndicator(df_24h["Close"], window=14).rsi()
    df_24h["SMA20"] = SMAIndicator(df_24h["Close"], window=20).sma_indicator()

    # 인덱스 → 컬럼 + 문자열 변환
    df_90.reset_index(inplace=True)
    df_30.reset_index(inplace=True)
    df_24h.reset_index(inplace=True)

    df_90["index"] = df_90["index"].astype(str)
    df_30["index"] = df_30["index"].astype(str)
    df_24h["index"] = df_24h["index"].astype(str)

    df_90.rename(columns={"index": "Date"}, inplace=True)
    df_30.rename(columns={"index": "Date"}, inplace=True)
    df_24h.rename(columns={"index": "Date"}, inplace=True)

    # to_dict(orient='records')
    day_90_records = df_90.to_dict(orient='records')
    day_30_records = df_30.to_dict(orient='records')
    hour_24_records = df_24h.to_dict(orient='records')

    # ---------------------------
    # (2) 공포/탐욕 지수 가져오기
    # ---------------------------
    fear_greed_url = "https://api.alternative.me/fng/?limit=1"
    try:
        response = requests.get(fear_greed_url, timeout=5)
        fng_data = response.json()
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

    # ---------------------------
    # (3) 잔고 조회
    # ---------------------------
    my_krw = upbit.get_balance("KRW")
    my_btc = upbit.get_balance("KRW-BTC")

    # ---------------------------
    # (4) AI에게 넘길 dict 구성
    # ---------------------------
    data_for_ai = {
        "balance": {
            "KRW": my_krw,
            "BTC": my_btc
        },
        "chart_data": {
            "day_90": day_90_records,
            "day_30": day_30_records,
            "hour_24": hour_24_records
        },
        "fear_greed": {
            "value": fng_value,
            "classification": fng_classification
        }
    }

    return data_for_ai

if __name__ == "__main__":
    data_for_ai = get_data_for_ai()
    # data_for_ai라는 dict가 있다고 가정
    print(json.dumps(data_for_ai["fear_greed"], ensure_ascii=False, indent=2))
# data_fetcher.py
# 데이터를 처리하고 이를 OpenAI API에 넘김

import os
import pyupbit
import requests
import pandas as pd
import json

# 보조지표 ta 라이브러리
from ta.trend import SMAIndicator
from ta.momentum import RSIIndicator

# .env에서 불러오려면 필요
from dotenv import load_dotenv
load_dotenv()

# 업비트 로그인
ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY")
SECRET_KEY = os.getenv("UPBIT_SECRET_KEY")
upbit = pyupbit.Upbit(ACCESS_KEY, SECRET_KEY)

def fetch_upbit_data(symbol="KRW-BTC", count_day_90=90, count_day_30=30, count_min_60=24):
    """
    업비트에서 시세 데이터를 불러오는 함수.
    
    Parameters:
        symbol (str): 조회할 심볼 (기본값: "KRW-BTC")
        count_day_90 (int): 90일 일봉 데이터 개수
        count_day_30 (int): 30일 일봉 데이터 개수
        count_min_60 (int): 24시간 1시간봉 데이터 개수
    
    Returns:
        tuple: (df_90, df_30, df_24h) 데이터프레임 튜플
    """
    df_90 = pyupbit.get_ohlcv(symbol, count=count_day_90, interval="day")
    df_30 = pyupbit.get_ohlcv(symbol, count=count_day_30, interval="day")
    df_24h = pyupbit.get_ohlcv(symbol, count=count_min_60, interval="minute60")
    
    return df_90, df_30, df_24h

def compute_technical_indicators(df_30, df_24h):
    """
    보조지표(RSI, SMA)를 계산하여 데이터프레임에 추가하는 함수.
    
    Parameters:
        df_30 (DataFrame): 30일 일봉 데이터프레임
        df_24h (DataFrame): 24시간 1시간봉 데이터프레임
    
    Returns:
        tuple: (df_30, df_24h) 보조지표가 추가된 데이터프레임 튜플
    """
    # 30일 일봉에 RSI14, SMA20 추가
    df_30["RSI14"] = RSIIndicator(df_30["Close"], window=14).rsi()
    df_30["SMA20"] = SMAIndicator(df_30["Close"], window=20).sma_indicator()
    
    # 24시간 1시간봉에 RSI14, SMA20 추가
    df_24h["RSI14"] = RSIIndicator(df_24h["Close"], window=14).rsi()
    df_24h["SMA20"] = SMAIndicator(df_24h["Close"], window=20).sma_indicator()
    
    return df_30, df_24h

def fetch_fear_greed_index():
    """
    공포/탐욕 지수를 가져오는 함수.
    
    Returns:
        dict: {"value": str, "classification": str} 또는 {"value": None, "classification": None}
    """
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
    
    return {
        "value": fng_value,
        "classification": fng_classification
    }

def fetch_balances():
    """
    업비트에서 잔고를 조회하는 함수.
    
    Returns:
        dict: {"KRW": float, "BTC": float}
    """
    my_krw = upbit.get_balance("KRW")
    my_btc = upbit.get_balance("KRW-BTC")
    
    return {
        "KRW": my_krw,
        "BTC": my_btc
    }

def prepare_data_for_ai(df_90, df_30, df_24h, fear_greed, balances):
    """
    AI에게 넘길 데이터를 구성하는 함수.
    
    Parameters:
        df_90 (DataFrame): 90일 일봉 데이터프레임
        df_30 (DataFrame): 30일 일봉 데이터프레임
        df_24h (DataFrame): 24시간 1시간봉 데이터프레임
        fear_greed (dict): 공포/탐욕 지수 데이터
        balances (dict): 잔고 데이터
    
    Returns:
        dict: AI에게 넘길 데이터 딕셔너리
    """
    # 컬럼명 변경 및 인덱스 처리
    for df in [df_90, df_30, df_24h]:
        df.rename(columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume"
        }, inplace=True)
        df.reset_index(inplace=True)
        df["index"] = df["index"].astype(str)
    
    df_90.rename(columns={"index": "Date"}, inplace=True)
    df_30.rename(columns={"index": "Date"}, inplace=True)
    df_24h.rename(columns={"index": "Date"}, inplace=True)
    
    # to_dict(orient='records')
    day_90_records = df_90.to_dict(orient='records')
    day_30_records = df_30.to_dict(orient='records')
    hour_24_records = df_24h.to_dict(orient='records')
    
    data_for_ai = {
        "balance": balances,
        "chart_data": {
            "day_90": day_90_records,
            "day_30": day_30_records,
            "hour_24": hour_24_records
        },
        "fear_greed": fear_greed
    }
    
    return data_for_ai

def get_data_for_ai():
    """
    전체 데이터를 가져와 AI에게 넘길 데이터를 준비하는 함수.
    
    Returns:
        dict: AI에게 넘길 데이터 딕셔너리
    """
    # 1. 업비트 시세 불러오기
    df_90, df_30, df_24h = fetch_upbit_data()
    
    # 2. 보조지표 계산
    df_30, df_24h = compute_technical_indicators(df_30, df_24h)
    
    # 3. 공포/탐욕 지수 가져오기
    fear_greed = fetch_fear_greed_index()
    
    # 4. 잔고 조회
    balances = fetch_balances()
    
    # 5. AI에게 넘길 데이터 구성
    data_for_ai = prepare_data_for_ai(df_90, df_30, df_24h, fear_greed, balances)
    
    return data_for_ai

if __name__ == "__main__":
    data_for_ai = get_data_for_ai()
    # data_for_ai라는 dict가 있다고 가정
    print(json.dumps(data_for_ai["fear_greed"], ensure_ascii=False, indent=2))

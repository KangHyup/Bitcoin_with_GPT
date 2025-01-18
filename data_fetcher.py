# data_fetcher.py
# 데이터를 처리하고 이를 OpenAI API에 전송

import os
import json
import requests
import pandas as pd
import logging

from binance import Client
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 바이낸스 API 키 및 시크릿 로드
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
BINANCE_TESTNET = False  # 테스트넷 사용 시 True로 설정

# OpenAI API 키 로드
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# CryptoPanic API 키 로드
CRYPTOPANIC_API_KEY = os.getenv("CRYPTOPANIC_API_KEY")

# 로깅 설정
logging.basicConfig(
    filename='data_fetcher.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s'
)

# 바이낸스 클라이언트 초기화
client = Client(BINANCE_API_KEY, BINANCE_API_SECRET, testnet=BINANCE_TESTNET)

# 테스트넷을 사용하는 경우 추가 설정
if BINANCE_TESTNET:
    client.API_URL = 'https://testnet.binance.vision/api'

def fetch_binance_data(symbol="BTCUSDT", count_day_90=90, count_day_30=30, count_min_60=60):
    """
    바이낸스에서 시세 데이터를 불러오는 함수.

    Parameters:
        symbol (str): 조회할 심볼 (기본값: "BTCUSDT")
        count_day_90 (int): 90일 일봉 데이터 개수
        count_day_30 (int): 30일 일봉 데이터 개수
        count_min_60 (int): 24시간 1시간봉 데이터 개수

    Returns:
        tuple: (df_90, df_30, df_24h) 데이터프레임 튜플
    """
    def get_historical_klines(symbol, interval, lookback):
        klines = client.get_historical_klines(symbol, interval, lookback)
        df = pd.DataFrame(klines, columns=[
            'Date', 'Open', 'High', 'Low', 'Close', 'Volume',
            'Close_time', 'Quote_asset_volume', 'Number_of_trades',
            'Taker_buy_base_asset_volume', 'Taker_buy_quote_asset_volume', 'Ignore'
        ])
        df['Date'] = pd.to_datetime(df['Date'], unit='ms')
        df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
        # 숫자형 데이터로 변환
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df

    df_90 = get_historical_klines(symbol, Client.KLINE_INTERVAL_1DAY, f"{count_day_90} day ago UTC")
    df_30 = get_historical_klines(symbol, Client.KLINE_INTERVAL_1DAY, f"{count_day_30} day ago UTC")
    df_24h = get_historical_klines(symbol, Client.KLINE_INTERVAL_1HOUR, f"{count_min_60} hour ago UTC")

    logging.info("바이낸스 데이터 수집 완료.")
    return df_90, df_30, df_24h

def make_unique_columns(df):
    """
    데이터프레임의 컬럼명을 고유하게 만듭니다.
    중복된 컬럼명에 숫자 접미사를 추가합니다.

    Parameters:
        df (DataFrame): 컬럼명을 고유하게 만들 데이터프레임

    Returns:
        DataFrame: 컬럼명이 고유하게 변경된 데이터프레임
    """
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique():
        cols[cols[cols == dup].index.tolist()] = [
            dup + '_' + str(i) if i != 0 else dup for i in range(sum(cols == dup))
        ]
    df.columns = cols
    return df

def verify_unique_columns(df, name):
    """
    데이터프레임의 모든 컬럼명이 고유한지 확인하는 함수.

    Parameters:
        df (DataFrame): 확인할 데이터프레임
        name (str): 데이터프레임 이름 (로그 용도)

    Raises:
        ValueError: 중복된 컬럼명이 존재할 경우
    """
    duplicates = df.columns[df.columns.duplicated()].tolist()
    if duplicates:
        raise ValueError(f"{name} has duplicate columns: {duplicates}")

def compute_technical_indicators(df_30, df_24h):
    """
    보조지표(RSI, SMA 등)를 계산하여 데이터프레임에 추가하는 함수.

    Parameters:
        df_30 (DataFrame): 30일 일봉 데이터프레임
        df_24h (DataFrame): 24시간 1시간봉 데이터프레임

    Returns:
        tuple: (df_30, df_24h) 보조지표가 추가된 데이터프레임 튜플
    """
    try:
        # RSI 추가
        rsi_30 = RSIIndicator(close=df_30["Close"], window=14)
        df_30["RSI14"] = rsi_30.rsi()

        rsi_24h = RSIIndicator(close=df_24h["Close"], window=14)
        df_24h["RSI14"] = rsi_24h.rsi()

        # SMA 추가
        sma_30 = SMAIndicator(close=df_30["Close"], window=20)
        df_30["SMA20"] = sma_30.sma_indicator()

        sma_24h = SMAIndicator(close=df_24h["Close"], window=20)
        df_24h["SMA20"] = sma_24h.sma_indicator()

        # 기술적 지표 계산 후 결측치 제거
        df_30.dropna(inplace=True)
        df_24h.dropna(inplace=True)

        logging.info("기술적 지표 계산 완료 및 결측치 제거됨.")

    except KeyError as ke:
        # 보조지표 컬럼을 None으로 설정
        ta_columns_30 = [col for col in df_30.columns if col not in ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
        ta_columns_24h = [col for col in df_24h.columns if col not in ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
        df_30[ta_columns_30] = None
        df_24h[ta_columns_24h] = None
        logging.error(f"KeyError 발생: {ke}")

    except Exception as e:
        print(f"Technical indicators computation error: {e}")
        logging.error(f"Technical indicators computation error: {e}")
        # 보조지표 컬럼을 None으로 설정
        ta_columns_30 = [col for col in df_30.columns if col not in ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
        ta_columns_24h = [col for col in df_24h.columns if col not in ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
        df_30[ta_columns_30] = None
        df_24h[ta_columns_24h] = None

    # 중복된 컬럼명 확인 및 고유화
    df_30 = make_unique_columns(df_30)
    df_24h = make_unique_columns(df_24h)

    # 고유성 검증
    verify_unique_columns(df_30, "df_30")
    verify_unique_columns(df_24h, "df_24h")

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
        logging.info("공포/탐욕 지수 수집 완료.")
    except Exception as e:
        print(f"Fear & Greed Index API 요청 중 오류 발생: {e}")
        logging.error(f"Fear & Greed Index API 요청 중 오류 발생: {e}")
        fng_value = None
        fng_classification = None

    return {
        "value": fng_value,
        "classification": fng_classification
    }

def fetch_balances():
    """
    바이낸스에서 잔고를 조회하는 함수.

    Returns:
        dict: {"BTC": float, "ETH": float, ...}
    """
    try:
        account_info = client.get_account()
        balances = {}
        for balance in account_info['balances']:
            asset = balance['asset']
            free = float(balance['free'])
            locked = float(balance['locked'])
            total = free + locked
            if total > 0:
                balances[asset] = total
        logging.info("잔고 조회 완료.")
        return balances
    except Exception as e:
        print(f"잔고 조회 중 오류 발생: {e}")
        logging.error(f"잔고 조회 중 오류 발생: {e}")
        return {}

def fetch_crypto_news(api_key, limit=3):
    """
    CryptoPanic API를 사용하여 BTC, ETH, XRP에 관련된 최신 뉴스 헤드라인을 가져오는 함수.

    Parameters:
        api_key (str): CryptoPanic API 키
        limit (int): 가져올 뉴스 개수 (기본값: 3)

    Returns:
        list: 뉴스 헤드라인 리스트 (각 헤드라인은 dict로 {'title': ..., 'published_at': ...})
    """
    base_url = "https://cryptopanic.com/api/v1/posts/"
    params = {
        "auth_token": api_key,
        "filter": "news",
        "regions": "en",
        "limit": 50  # 충분한 수의 뉴스를 가져오기 위해 50으로 설정
    }
    try:
        response = requests.get(base_url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        news_list = []
        keywords = ["btc", "eth", "xrp"]  # 필터링할 키워드
        for post in data.get("results", []):
            title = post.get("title", "").lower()
            if any(keyword in title for keyword in keywords):
                news_list.append({
                    "title": post.get("title", ""),
                    "pub_at": post.get("published_at", "")
                })
                if len(news_list) >= limit:
                    break  # 원하는 수의 뉴스만 수집
        logging.info("CryptoPanic 뉴스 수집 완료.")
        return news_list
    except requests.exceptions.RequestException as e:
        # 예외 발생 시 빈 리스트 반환
        print(f"CryptoPanic API 요청 중 오류 발생: {e}")
        logging.error(f"CryptoPanic API 요청 중 오류 발생: {e}")
        return []

def validate_data(df, name):
    """
    데이터프레임의 무결성을 검증하는 함수.

    Parameters:
        df (DataFrame): 검증할 데이터프레임
        name (str): 데이터프레임 이름

    Raises:
        ValueError: 데이터프레임이 비어있거나 결측치가 존재할 경우
    """
    if df.empty:
        raise ValueError(f"{name} 데이터프레임이 비어 있습니다.")
    if df.isnull().values.any():
        raise ValueError(f"{name} 데이터프레임에 결측치가 존재합니다.")

def prepare_data_for_ai(df_90, df_30, df_24h, fear_greed, balances, crypto_news):
    """
    AI에게 넘길 데이터를 구성하는 함수.

    Parameters:
        df_90 (DataFrame): 90일 일봉 데이터프레임
        df_30 (DataFrame): 30일 일봉 데이터프레임
        df_24h (DataFrame): 24시간 1시간봉 데이터프레임
        fear_greed (dict): 공포/탐욕 지수 데이터
        balances (dict): 잔고 데이터
        crypto_news (list): 최신 뉴스 헤드라인 리스트

    Returns:
        dict: AI에게 넘길 데이터 딕셔너리
    """
    # 데이터 검증
    validate_data(df_90, "df_90")
    validate_data(df_30, "df_30")
    validate_data(df_24h, "df_24h")

    # to_dict(orient='records')을 사용하여 데이터프레임을 딕셔너리 리스트로 변환
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
        "fear_greed": fear_greed,
        "crypto_news": crypto_news  # 뉴스 데이터 추가
    }

    return data_for_ai

def preprocess_data_for_api(data_for_ai, recent_points=5):
    """
    AI에 전송할 데이터를 최적화하는 함수.
    
    Parameters:
        data_for_ai (dict): 원본 데이터 딕셔너리
        recent_points (int): 각 차트 데이터에서 최근 몇 개의 데이터 포인트를 유지할지 결정
    
    Returns:
        dict: 최적화된 데이터 딕셔너리
    """
    optimized_data = {}
    
    # 잔고 정보 최적화
    optimized_data["bal"] = data_for_ai["balance"]
    
    # 차트 데이터 최적화
    optimized_data["charts"] = {}
    for chart_key, chart_data in data_for_ai["chart_data"].items():
        # 최근 N개의 데이터 포인트만 선택
        recent_chart_data = chart_data[-recent_points:]
        optimized_chart = []
        for entry in recent_chart_data:
            optimized_entry = {
                "Date": entry["Date"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(entry["Date"], pd.Timestamp) else entry["Date"],
                "Close": entry["Close"],
                "Volume": entry["Volume"],
                "RSI14": round(entry.get("RSI14", 0), 2),
                "SMA20": round(entry.get("SMA20", 0), 2)
            }
            optimized_chart.append(optimized_entry)
        optimized_data["charts"][chart_key] = optimized_chart
    
    # 공포/탐욕 지수 최적화
    optimized_data["fg"] = {
        "value": data_for_ai["fear_greed"].get("value", None),
        "class": data_for_ai["fear_greed"].get("classification", None)
    }
    
    # 뉴스 데이터 최적화 (상위 3개 뉴스만)
    optimized_data["news"] = data_for_ai.get("crypto_news", [])[:3]
    
    logging.info("데이터 최적화 완료.")
    return optimized_data

import openai

def send_to_openai(optimized_data):
    """
    최적화된 데이터를 OpenAI API에 전송하는 함수.
    
    Parameters:
        optimized_data (dict): 최적화된 데이터 딕셔너리
    
    Returns:
        str: OpenAI의 응답 내용
    """
    # JSON 형식으로 데이터를 변환
    prompt = json.dumps(optimized_data, ensure_ascii=False)
    
    # OpenAI API 호출
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a crypto investment assistant."},
                {"role": "user", "content": f"Analyze the following crypto data and provide investment insights:\n{prompt}"}
            ],
            max_tokens=200  # 응답 토큰 수 제한
        )
        logging.info("OpenAI API 요청 및 응답 완료.")
        return response.choices[0].message['content']
    except Exception as e:
        print(f"OpenAI API 요청 중 오류 발생: {e}")
        logging.error(f"OpenAI API 요청 중 오류 발생: {e}")
        return "Error: Unable to get response from OpenAI API."

def get_data_for_ai():
    """
    전체 데이터를 가져와 AI에게 넘길 데이터를 준비하는 함수.
    
    Returns:
        dict: AI에게 넘길 데이터 딕셔너리
    """
    # 1. 바이낸스 시세 불러오기
    df_90, df_30, df_24h = fetch_binance_data()

    # 2. 보조지표 계산
    df_30, df_24h = compute_technical_indicators(df_30, df_24h)

    # 3. 공포/탐욕 지수 가져오기
    fear_greed = fetch_fear_greed_index()

    # 4. 잔고 조회
    balances = fetch_balances()

    # 5. CryptoPanic 뉴스 가져오기
    crypto_news = fetch_crypto_news(api_key=CRYPTOPANIC_API_KEY, limit=3)

    # 6. AI에게 넘길 데이터 구성
    data_for_ai = prepare_data_for_ai(df_90, df_30, df_24h, fear_greed, balances, crypto_news)

    return data_for_ai

if __name__ == "__main__":
    try:
        data_for_ai = get_data_for_ai()
        
        # 데이터 최적화
        optimized_data = preprocess_data_for_api(data_for_ai, recent_points=5)
        
        # OpenAI API에 전송 및 응답 받기
        analysis = send_to_openai(optimized_data)
        
        # 결과 출력
        print("Analysis by OpenAI:")
        print(analysis)
    
    except TypeError as te:
        print(f"TypeError 발생: {te}")
        logging.error(f"TypeError 발생: {te}")
    except KeyError as ke:
        print(f"KeyError 발생: {ke}")
        logging.error(f"KeyError 발생: {ke}")
    except ValueError as ve:
        print(f"ValueError 발생: {ve}")
        logging.error(f"ValueError 발생: {ve}")
    except Exception as e:
        print(f"예상치 못한 에러 발생: {e}")
        logging.error(f"예상치 못한 에러 발생: {e}")

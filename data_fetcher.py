# data_fetcher.py
# 데이터를 처리하고 이를 OpenAI API에 넘김

import os
import pyupbit
import requests
import pandas as pd
import json

# 보조지표 ta 라이브러리
from ta import add_all_ta_features
from ta.utils import dropna

# .env에서 불러오려면 필요
from dotenv import load_dotenv
load_dotenv()

# 업비트 로그인
ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY")
SECRET_KEY = os.getenv("UPBIT_SECRET_KEY")
upbit = pyupbit.Upbit(ACCESS_KEY, SECRET_KEY)


def fetch_upbit_data(symbol="KRW-BTC", count_day_90=100, count_day_30=50, count_min_60=50):
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


def rename_columns(df):
    """
    데이터프레임의 컬럼명을 대문자로 변경하고 인덱스를 'Date'로 설정하는 함수.

    Parameters:
        df (DataFrame): 컬럼명을 변경할 데이터프레임

    Returns:
        DataFrame: 컬럼명이 변경된 데이터프레임
    """
    df.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume"
    }, inplace=True)
    df.reset_index(inplace=True)
    df.rename(columns={"index": "Date"}, inplace=True)
    return df


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
        cols[cols[cols == dup].index.values.tolist()] = [
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
    # 보조지표 추가
    try:
        # 'add_all_ta_features'를 사용하여 모든 보조지표 추가
        df_30 = add_all_ta_features(
            df_30, open="Open", high="High", low="Low", close="Close", volume="Volume",
            fillna=True
        )

        df_24h = add_all_ta_features(
            df_24h, open="Open", high="High", low="Low", close="Close", volume="Volume",
            fillna=True
        )

    except KeyError as ke:
        # 보조지표 컬럼을 None으로 설정
        ta_columns_30 = [col for col in df_30.columns if col not in ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
        ta_columns_24h = [col for col in df_24h.columns if col not in ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
        df_30[ta_columns_30] = None
        df_24h[ta_columns_24h] = None
    except Exception:
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
    except Exception:
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


def fetch_crypto_news(api_key, limit=5):
    """
    CryptoPanic API를 사용하여 BTC, ETH, XRP에 관련된 최신 뉴스 헤드라인을 가져오는 함수.

    Parameters:
        api_key (str): CryptoPanic API 키
        limit (int): 가져올 뉴스 개수 (기본값: 5)

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
        keywords = ["btc", "eth", "xrp", "bitcoin", "ethereum", "ripple"]  # 필터링할 키워드
        for post in data.get("results", []):
            title = post.get("title", "").lower()
            if any(keyword in title for keyword in keywords):
                news_list.append({
                    "title": post.get("title", ""),
                    "published_at": post.get("published_at", "")
                })
                if len(news_list) >= limit:
                    break  # 원하는 수의 뉴스만 수집
        return news_list
    except requests.exceptions.RequestException as e:
        # 예외 발생 시 빈 리스트 반환
        return []


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
    # 불필요한 'value' 컬럼 제거 (필요 시 유지)
    df_90 = df_90.drop(columns=['value'], errors='ignore')
    df_30 = df_30.drop(columns=['value'], errors='ignore')
    df_24h = df_24h.drop(columns=['value'], errors='ignore')

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


def get_data_for_ai():
    """
    전체 데이터를 가져와 AI에게 넘길 데이터를 준비하는 함수.

    Returns:
        dict: AI에게 넘길 데이터 딕셔너리
    """
    # 1. 업비트 시세 불러오기
    df_90, df_30, df_24h = fetch_upbit_data()

    # 2. 컬럼명 변경 및 인덱스 처리
    df_90 = rename_columns(df_90)
    df_30 = rename_columns(df_30)
    df_24h = rename_columns(df_24h)

    # 3. 보조지표 계산
    df_30, df_24h = compute_technical_indicators(df_30, df_24h)

    # 4. 공포/탐욕 지수 가져오기
    fear_greed = fetch_fear_greed_index()

    # 5. 잔고 조회
    balances = fetch_balances()

    # 6. CryptoPanic 뉴스 가져오기
    crypto_news_api_key = os.getenv("CRYPTOPANIC_API_KEY")  # .env에 CRYPTOPANIC_API_KEY 추가 필요
    crypto_news = fetch_crypto_news(api_key=crypto_news_api_key, limit=5)

    # 7. AI에게 넘길 데이터 구성
    data_for_ai = prepare_data_for_ai(df_90, df_30, df_24h, fear_greed, balances, crypto_news)

    return data_for_ai


if __name__ == "__main__":
    try:
        data_for_ai = get_data_for_ai()
        # data_for_ai라는 dict가 있다고 가정

        # 정제된 최신 뉴스 헤드라인 출력
        print("Latest Crypto News:")
        for news in data_for_ai["crypto_news"]:
            print(f"Title: {news['title']}")
            print(f"Published at: {news['published_at']}")
            print()  # 각 뉴스 항목 사이에 빈 줄 추가

    except TypeError as te:
        # 적절한 예외 처리 추가 가능
        pass
    except KeyError as ke:
        # 적절한 예외 처리 추가 가능
        pass
    except Exception:
        # 적절한 예외 처리 추가 가능
        pass

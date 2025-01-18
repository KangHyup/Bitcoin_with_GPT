# data_fetcher.py
import os
import json
import requests
import pandas as pd
import logging
import base64
import time
from io import BytesIO
from PIL import Image

from binance import Client
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


load_dotenv()

logging.basicConfig(
    filename='data_fetcher.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s'
)

class DataFetcher:
    def __init__(self, 
                 binance_api_key=None, 
                 binance_api_secret=None, 
                 cryptopanic_api_key=None, 
                 binance_testnet=False):
        # 바이낸스 API
        self.binance_api_key = binance_api_key or os.getenv("BINANCE_API_KEY")
        self.binance_api_secret = binance_api_secret or os.getenv("BINANCE_API_SECRET")
        self.binance_testnet = binance_testnet
        
        # 바이낸스 클라이언트 초기화
        self.client = Client(self.binance_api_key, self.binance_api_secret, testnet=self.binance_testnet)
        if self.binance_testnet:
            self.client.API_URL = 'https://testnet.binance.vision/api'

        # CryptoPanic API
        self.cryptopanic_api_key = cryptopanic_api_key or os.getenv("CRYPTOPANIC_API_KEY")

    # -------------------- 바이낸스 데이터 -------------------- #
    def fetch_binance_data(self, symbol="BTCUSDT", count_day_30=30, count_min_60=60):
        """
        바이낸스에서 시세 데이터를 불러오는 메서드.
        """
        def get_historical_klines(symbol, interval, lookback):
            klines = self.client.get_historical_klines(symbol, interval, lookback)
            df = pd.DataFrame(klines, columns=[
                'Date', 'Open', 'High', 'Low', 'Close', 'Volume',
                'Close_time', 'Quote_asset_volume', 'Number_of_trades',
                'Taker_buy_base_asset_volume', 'Taker_buy_quote_asset_volume', 'Ignore'
            ])
            df['Date'] = pd.to_datetime(df['Date'], unit='ms')
            df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            return df

        df_30 = get_historical_klines(symbol, Client.KLINE_INTERVAL_1DAY, f"{count_day_30} day ago UTC")
        df_24h = get_historical_klines(symbol, Client.KLINE_INTERVAL_1HOUR, f"{count_min_60} hour ago UTC")

        logging.info("바이낸스 데이터 수집 완료.")
        return df_30, df_24h

    # -------------------- 보조지표 -------------------- #
    def compute_technical_indicators(self, df_30, df_24h):
        """
        보조지표(RSI, SMA 등)를 계산하여 데이터프레임에 추가하는 메서드.
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

            df_30.dropna(inplace=True)
            df_24h.dropna(inplace=True)
            logging.info("기술적 지표 계산 완료 및 결측치 제거됨.")
        except KeyError as ke:
            logging.error(f"KeyError 발생: {ke}")
            self._set_ta_columns_none(df_30)
            self._set_ta_columns_none(df_24h)
        except Exception as e:
            logging.error(f"Technical indicators computation error: {e}")
            self._set_ta_columns_none(df_30)
            self._set_ta_columns_none(df_24h)

        # 중복 컬럼명 확인 및 처리
        df_30 = self._make_unique_columns(df_30)
        df_24h = self._make_unique_columns(df_24h)
        self._verify_unique_columns(df_30, "df_30")
        self._verify_unique_columns(df_24h, "df_24h")

        return df_30, df_24h

    def _set_ta_columns_none(self, df):
        """
        보조지표 컬럼을 None으로 설정하는 내부 헬퍼 메서드.
        """
        ta_columns = [col for col in df.columns 
                      if col not in ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
        df[ta_columns] = None

    def _make_unique_columns(self, df):
        """
        데이터프레임의 컬럼명을 고유하게 만드는 내부 헬퍼 메서드.
        """
        cols = pd.Series(df.columns)
        for dup in cols[cols.duplicated()].unique():
            cols[cols[cols == dup].index.tolist()] = [
                dup + '_' + str(i) if i != 0 else dup for i in range(sum(cols == dup))
            ]
        df.columns = cols
        return df

    def _verify_unique_columns(self, df, name):
        """
        데이터프레임의 모든 컬럼명이 고유한지 확인하는 내부 헬퍼 메서드.
        """
        duplicates = df.columns[df.columns.duplicated()].tolist()
        if duplicates:
            raise ValueError(f"{name} has duplicate columns: {duplicates}")

    # -------------------- 공포/탐욕 지수 -------------------- #
    def fetch_fear_greed_index(self):
        """
        공포/탐욕 지수를 가져오는 메서드.
        """
        url = "https://api.alternative.me/fng/?limit=1"
        try:
            response = requests.get(url, timeout=5)
            fng_data = response.json()
            if "data" in fng_data and len(fng_data["data"]) > 0:
                fng_value = fng_data["data"][0].get("value", None)
                fng_classification = fng_data["data"][0].get("value_classification", None)
            else:
                fng_value = None
                fng_classification = None
            logging.info("공포/탐욕 지수 수집 완료.")
        except Exception as e:
            logging.error(f"Fear & Greed Index API 요청 중 오류 발생: {e}")
            fng_value = None
            fng_classification = None

        return {
            "value": fng_value,
            "classification": fng_classification
        }

    # -------------------- 잔고 -------------------- #
    def fetch_balances(self):
        """
        바이낸스에서 잔고를 조회하는 메서드.
        """
        try:
            account_info = self.client.get_account()
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
            logging.error(f"잔고 조회 중 오류 발생: {e}")
            return {}

    # -------------------- CryptoPanic 뉴스 -------------------- #
    def fetch_crypto_news(self, limit=3):
        """
        CryptoPanic API를 사용하여 BTC, ETH, XRP에 관련된 최신 뉴스 헤드라인을 가져오는 메서드.
        """
        base_url = "https://cryptopanic.com/api/v1/posts/"
        params = {
            "auth_token": self.cryptopanic_api_key,
            "filter": "news",
            "regions": "en",
            "limit": 50
        }
        try:
            response = requests.get(base_url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            news_list = []
            keywords = ["btc", "eth", "xrp"]
            for post in data.get("results", []):
                title = post.get("title", "").lower()
                if any(keyword in title for keyword in keywords):
                    news_list.append({
                        "title": post.get("title", ""),
                        "pub_at": post.get("published_at", "")
                    })
                    if len(news_list) >= limit:
                        break
            logging.info("CryptoPanic 뉴스 수집 완료.")
            return news_list
        except requests.exceptions.RequestException as e:
            logging.error(f"CryptoPanic API 요청 중 오류 발생: {e}")
            return []

    # -------------------- 스크린샷 캡처 -------------------- #
    def capture_chart_image(self, url, save_path="Captured_image/full_screenshot.png"):
        folder_path = os.path.dirname(save_path)
        if folder_path and not os.path.exists(folder_path):
            os.makedirs(folder_path)
            logging.info(f"폴더 생성 완료: {folder_path}")

        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--enable-unsafe-swiftshader")
        chrome_options.add_argument("--disable-webgl")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-infobars")

        try:
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logging.error(f"WebDriver 초기화 중 오류 발생: {e}")
            return None

        try:
            driver.get(url)
            
            # 페이지가 완전히 로딩될 때까지 잠시 대기 (필요하다면 WebDriverWait으로 대체 가능)
            time.sleep(5)
            
            # 1) "시간 메뉴" 버튼 클릭 (드롭다운 열기)
            try:
                menu_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, '//*[@id="fullChartiq"]/div/div/div[1]/div/div/cq-menu[1]/span/cq-clickable')
                    )
                )
                menu_button.click()
                logging.info("시간 메뉴 버튼 클릭 완료.")
                
                # 드롭다운이 열리는 데 시간이 걸릴 수 있으므로 잠시 대기
                time.sleep(2)
            except Exception as e:
                logging.warning(f"시간 메뉴 버튼을 찾지 못했습니다: {e}")

            # 2) "4시간" 항목 클릭 (cq-item[9])
            try:
                four_hour_option = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, '//*[@id="fullChartiq"]/div/div/div[1]/div/div/cq-menu[1]/cq-menu-dropdown/cq-item[9]')
                    )
                )
                four_hour_option.click()
                logging.info('"4시간" 옵션 클릭 완료.')
                
                # 4시간봉 차트가 반영될 때까지 잠시 대기
                time.sleep(3)
            except Exception as e:
                logging.warning(f'"4시간" 옵션을 찾지 못했습니다: {e}')

            # 3) 스크린샷 찍기
            driver.save_screenshot(save_path)
            logging.info(f"스크린샷 저장 완료: {save_path}")
            return save_path

        except Exception as e:
            logging.error(f"스크린샷 캡처 중 오류 발생: {e}")
            return None

        finally:
            driver.quit()


    # -------------------- 데이터 검증 -------------------- #
    def validate_data(self, df, name):
        """
        데이터프레임의 무결성을 검증하는 메서드.
        """
        if df.empty:
            raise ValueError(f"{name} 데이터프레임이 비어 있습니다.")
        if df.isnull().values.any():
            raise ValueError(f"{name} 데이터프레임에 결측치가 존재합니다.")

    # -------------------- 이미지 인코딩 -------------------- #
    def encode_image_to_base64(self, image_path):
        """
        이미지 파일을 Base64 문자열로 인코딩하는 메서드.
        """
        try:
            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            logging.info(f"이미지 인코딩 완료: {image_path}")
            return encoded_string
        except Exception as e:
            logging.error(f"이미지 인코딩 중 오류 발생: {e}")
            return None

    # -------------------- AI 데이터 준비 -------------------- #
    def prepare_data_for_ai(self, df_30, df_24h, fear_greed, balances, crypto_news, chart_image_path=None):
        """
        AI에게 넘길 데이터를 구성하는 메서드.
        """
        self.validate_data(df_30, "df_30")
        self.validate_data(df_24h, "df_24h")

        day_30_records = df_30.to_dict(orient='records')
        hour_24_records = df_24h.to_dict(orient='records')

        data_for_ai = {
            "balance": balances,
            "chart_data": {
                "day_30": day_30_records,
                "hour_24": hour_24_records
            },
            "fear_greed": fear_greed,
            "crypto_news": crypto_news
        }

        if chart_image_path:
            encoded_image = self.encode_image_to_base64(chart_image_path)
            if encoded_image:
                data_for_ai["chart_image"] = encoded_image

        return data_for_ai

    def preprocess_data_for_api(self, data_for_ai, recent_points=5):
        """
        AI에 전송할 데이터를 최적화하는 메서드.
        """
        optimized_data = {}
        
        optimized_data["bal"] = data_for_ai["balance"]
        optimized_data["charts"] = {}

        for chart_key, chart_data in data_for_ai["chart_data"].items():
            recent_chart_data = chart_data[-recent_points:]
            optimized_chart = []
            for entry in recent_chart_data:
                # Date 컬럼 처리
                date_val = (entry["Date"].strftime("%Y-%m-%d %H:%M:%S")
                            if isinstance(entry["Date"], pd.Timestamp)
                            else entry["Date"])
                optimized_chart.append({
                    "Date": date_val,
                    "Close": entry["Close"],
                    "Volume": entry["Volume"],
                    "RSI14": round(entry.get("RSI14", 0), 2),
                    "SMA20": round(entry.get("SMA20", 0), 2)
                })
            optimized_data["charts"][chart_key] = optimized_chart

        optimized_data["fg"] = {
            "value": data_for_ai["fear_greed"].get("value", None),
            "class": data_for_ai["fear_greed"].get("classification", None)
        }
        optimized_data["news"] = data_for_ai.get("crypto_news", [])[:3]

        if "chart_image" in data_for_ai:
            optimized_data["chart_image"] = data_for_ai["chart_image"]

        logging.info("데이터 최적화 완료.")
        return optimized_data

    # -------------------- 메인 호출 메서드 -------------------- #
    def get_data_for_ai(self):
        """
        전체 데이터를 가져와 AI에게 넘길 데이터를 준비하는 메서드.
        """
        # 1. 바이낸스 시세 불러오기
        df_30, df_24h = self.fetch_binance_data()

        # 2. 보조지표 계산
        df_30, df_24h = self.compute_technical_indicators(df_30, df_24h)

        # 3. 공포/탐욕 지수 가져오기
        fear_greed = self.fetch_fear_greed_index()

        # 4. 잔고 조회
        balances = self.fetch_balances()

        # 5. 뉴스 수집
        crypto_news = self.fetch_crypto_news(limit=3)

        # 6. 차트 이미지 캡처
        chart_url = "https://upbit.com/full_chart?code=CRIX.UPBIT.KRW-BTC"
        chart_image_path = self.capture_chart_image(url=chart_url, 
                                            save_path="Captured_image/full_screenshot.png")


        # 7. 데이터 구성
        data_for_ai = self.prepare_data_for_ai(df_30, df_24h, fear_greed, balances, crypto_news, chart_image_path)

        return data_for_ai

# -------------------- 모듈 직접 실행 시 -------------------- #
if __name__ == "__main__":
    try:
        fetcher = DataFetcher()
        data_for_ai = fetcher.get_data_for_ai()
        
        # 예시: 데이터 최적화
        optimized_data = fetcher.preprocess_data_for_api(data_for_ai, recent_points=5)
        print("Optimized data ready for AI:", optimized_data)

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

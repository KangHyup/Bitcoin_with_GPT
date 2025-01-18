# main.py
import time
import data_fetcher
import openai_trader  # Vision API 호출도 이쪽에서 진행
import logging
import json
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 로깅 설정 (openai_trader.py, data_fetcher.py에서 이미 하셨다면 중복 불필요)
logging.basicConfig(
    filename='main.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s'
)

def main_loop(interval_minutes=30):
    """
    Main loop for auto trading.
    1. 데이터 수집 (data_fetcher)
    2. openai_trader.get_ai_decision_with_chart()로 Vision API에 데이터 전송해 매매 결정 받기
    3. 결정에 따라 매매 실행
    4. 일정 시간 대기 후 반복
    """
    interval_seconds = interval_minutes * 60
    while True:
        try:
            print("\n=== 데이터 수집 및 매매 실행 시작 ===")
            logging.info("데이터 수집 및 매매 실행 시작.")

            # 1. 데이터 가져오기
            data_for_ai = data_fetcher.get_data_for_ai()

            # 2. 데이터 최적화
            optimized_data = data_fetcher.preprocess_data_for_api(data_for_ai, recent_points=5)

            # 3. Vision API 호출: buy/sell/hold 결정 받기
            decision, reason = openai_trader.get_ai_decision_with_chart(optimized_data)
            logging.info(f"AI 결정: {decision}, 이유: {reason}")

            # 4. 매매 실행
            openai_trader.execute_trade(decision, reason)

            # 5. 대기
            print(f">>> Sleep for {interval_minutes} minutes ({interval_seconds} seconds)")
            logging.info(f"Sleep for {interval_minutes} minutes.")
            time.sleep(interval_seconds)

        except KeyboardInterrupt:
            print("\n자동 매매를 중지합니다.")
            logging.info("자동 매매 중지.")
            break

        except Exception as e:
            print(f"메인 루프에서 오류 발생: {e}")
            logging.error(f"메인 루프에서 오류 발생: {e}")
            print(f">>> Sleep for {interval_minutes} minutes before retrying.")
            logging.info(f"Sleep for {interval_minutes} minutes before retrying due to error.")
            time.sleep(interval_seconds)

if __name__ == "__main__":
    main_loop(30)  # 30분 간격

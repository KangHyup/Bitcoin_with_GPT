# main.py
# 데이터를 수집하고 OpenAI를 통해 매매 결정을 실행하는 메인 스크립트

import time
import data_fetcher
import openai_trader
import logging

# 로깅 설정 (main.py에서 별도로 설정할 필요 없음, openai_trader.py와 data_fetcher.py에서 설정됨)

def main_loop(interval_minutes=30):
    """
    Main loop for auto trading.
    1. 데이터 가져오기 (data_fetcher)
    2. OpenAI로 보내고, 매매 결정 받기 (openai_trader)
    3. 일정 시간 대기 후 반복
    """
    interval_seconds = interval_minutes * 60
    while True:
        try:
            print("\n=== 데이터 수집 및 매매 실행 시작 ===")
            logging.info("데이터 수집 및 매매 실행 시작.")

            # 1 데이터 가져오기
            data_for_ai = data_fetcher.get_data_for_ai()

            # 2 OpenAI API 호출 + 매매 로직
            openai_trader.send_to_openai_and_trade(data_for_ai)

            # 3 대기
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

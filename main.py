# main.py

import time
import data_fetcher
import openai_trader

def main_loop(time):
    """
    Main loop for auto trading.
    1. 데이터 가져오기 (data_fetcher)
    2. OpenAI로 보내고, 매매 결정 받기 (openai_trader)
    3. 일정 시간 대기 후 반복
    """
    while True:
        # 1) 데이터 가져오기
        data_for_ai = data_fetcher.get_data_for_ai()

        # 2) OpenAI API 호출 + 매매 로직
        decision, reason = openai_trader.send_to_openai_and_trade(data_for_ai)

        # 3) 대기
        print(">>> Sleep 10 seconds")
        time.sleep(time)


if __name__ == "__main__":
    main_loop(10000)

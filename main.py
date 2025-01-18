# main.py
# 데이터를 수집하고 OpenAI를 통해 매매 결정을 실행하는 메인 스크립트

import time
import data_fetcher
import openai_trader
import logging
import openai
import json
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# OpenAI API 키 로드
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# 로깅 설정 (main.py에서 별도로 설정할 필요 없음, openai_trader.py와 data_fetcher.py에서 설정됨)

def send_to_openai(data):
    """
    OpenAI API에 데이터를 전송하고 응답을 받아 매매 결정을 반환하는 함수.

    Parameters:
        data (dict): OpenAI에 전송할 데이터

    Returns:
        tuple: (decision, reason)
    """
    try:
        with open("gpt_prompt.txt", "r", encoding="utf-8") as f:
            system_prompt = f.read()
        logging.info("gpt_prompt.txt 로드 완료.")
    except FileNotFoundError:
        system_prompt = (
            "You are a crypto investment assistant. Analyze the provided crypto data, including chart images, and provide buy/sell/hold recommendations with reasons."
        )
        logging.warning("gpt_prompt.txt 파일을 찾을 수 없어 기본 프롬프트 사용.")

    # OpenAI Chat API 호출
    user_content = json.dumps(data, ensure_ascii=False)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",  # 또는 "gpt-3.5-turbo"
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Analyze the following crypto data and provide buy/sell/hold decision.\n{user_content}"}
            ],
            max_tokens=200  # 응답 토큰 수 제한
        )
        ai_answer = response.choices[0].message.content.strip()
        logging.info("OpenAI API 응답 수신 완료.")
        print("[AI Raw Answer]", ai_answer)
    except Exception as e:
        logging.error(f"OpenAI API 요청 중 오류 발생: {e}")
        print(f"OpenAI API 요청 중 오류 발생: {e}")
        return ("hold", "OpenAI API 요청 중 오류 발생")

    # AI 응답 파싱 (JSON 형식 가정)
    try:
        ai_result = json.loads(ai_answer)
        decision = ai_result.get("decision", "hold").lower()
        reason = ai_result.get("reason", "No reason provided.")
        logging.info(f"AI 결정: {decision}, 이유: {reason}")
    except json.JSONDecodeError:
        decision = "hold"
        reason = "JSON 파싱 실패"
        logging.warning("AI 응답을 JSON으로 파싱하는 데 실패했습니다.")
    except Exception as e:
        decision = "hold"
        reason = "Error parsing AI response"
        logging.error(f"AI 응답 파싱 중 오류 발생: {e}")

    return (decision, reason)

def main_loop(interval_minutes=30):
    """
    Main loop for auto trading.
    1. 데이터 가져오기 (data_fetcher)
    2. OpenAI로 데이터 전송하고 매매 결정 받기
    3. 매매 결정에 따라 매매 실행 (openai_trader)
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

            # 3. OpenAI API 호출 및 매매 결정 받기
            decision, reason = send_to_openai(optimized_data)

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

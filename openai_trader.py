# openai_trader.py

import os
import json
import pyupbit
import openai
from dotenv import load_dotenv

load_dotenv()

# 업비트 로그인 (매매 주문용)
access = os.getenv("UPBIT_ACCESS_KEY")
secret = os.getenv("UPBIT_SECRET_KEY")
upbit = pyupbit.Upbit(access, secret)

# OpenAI Key
openai.api_key = os.getenv("OPENAI_API_KEY")

def send_to_openai_and_trade(data_for_ai):
    """
    1. data_for_ai를 OpenAI API에 전송
    2. AI 응답(JSON)에서 매매 결정을 파싱
    3. 업비트 매매 로직 실행
    """
    
    # ---------------------------
    # (1) 프롬프트 불러오기 (시스템 메시지)
    # ---------------------------
    try:
        with open("gpt_prompt.txt", "r", encoding="utf-8") as f:
            system_prompt = f.read()
    except:
        system_prompt = (
            "You are a helpful assistant. You will receive crypto data and respond with a buy/sell/hold decision."
        )

    # ---------------------------
    # (2) OpenAI Chat API 호출
    # ---------------------------
    user_content = json.dumps(data_for_ai, ensure_ascii=False)
    
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",  # 또는 gpt-4
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
    )

    ai_answer = response.choices[0].message.content.strip()
    print("[AI Raw Answer]", ai_answer)

    # ---------------------------
    # (3) AI 응답 파싱 (JSON 가정)
    # ---------------------------
    # 예: {"decision":"buy","reason":"단기 추세 반등 예상"}
    try:
        ai_result = json.loads(ai_answer)
    except:
        ai_result = {"decision": "hold", "reason": "JSON 파싱 실패"}

    decision = ai_result.get("decision", "hold")

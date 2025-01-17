#데이터를 기반으로 프롬프트를 작성해 실제 코인을 매매

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

    # ---------------------------
    # (3) 매매 로직 실행
    # ---------------------------
    # 수수료 등을 고려해 원화 잔고는 조금 줄인다 (예: *0.9995)
    my_krw = my_krw * 0.9995

    if decision == "buy":
        # KRW 5,000 이상이면 시장가 매수
        if my_krw >= 5000:
            print(">>> BUY (market order) KRW-BTC")
            buy_result = upbit.buy_market_order("KRW-BTC", my_krw)
            print(buy_result)
            print("buy reason:", reason)
        else:
            print("매수불가 : 보유 KRW가 5000원 미만입니다.")

    elif decision == "sell":
        # 내가 가진 BTC 평가 금액이 5,000원 이상인지 확인
        current_price = pyupbit.get_orderbook("KRW-BTC")['orderbook_units'][0]["ask_price"]
        if (my_btc * current_price) >= 5000:
            print(">>> SELL (market order) KRW-BTC")
            sell_result = upbit.sell_market_order("KRW-BTC", my_btc)
            print(sell_result)
            print("sell reason:", reason)
        else:
            print("매도불가 : 보유 BTC 평가액이 5000원 미만입니다.")

    else:
        # hold 상태면 아무 매매도 하지 않는다
        print("hold:", reason)
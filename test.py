# 텍스트 파일 읽기
with open("gpt_prompt.txt", "r", encoding="utf-8") as file:
    file_content = file.read()  # 파일 내용을 변수에 저장

# 변수 출력
print(file_content)

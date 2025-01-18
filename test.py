import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def capture_fullpage_screenshot(url, save_path="Captured_image/full_screenshot.png"):
    """
    주어진 URL의 전체 페이지 스크린샷을 캡처하고, 
    'Captured_image' 폴더에 저장하는 함수.

    Parameters:
        url (str): 캡처할 웹페이지의 URL
        save_path (str): 스크린샷을 저장할 경로 (기본값: 'Captured_image/full_screenshot.png')
    """

    # 캡처 이미지를 저장할 폴더가 없으면 생성
    folder_path = os.path.dirname(save_path)
    if folder_path and not os.path.exists(folder_path):
        os.makedirs(folder_path)
        print(f"폴더 생성 완료: {folder_path}")

    # 크롬 브라우저 옵션 설정
    chrome_options = Options()
    chrome_options.add_argument("--headless")             # 브라우저 창을 열지 않는 헤드리스 모드
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--enable-unsafe-swiftshader") # WebGL 관련 오류 방지 플래그
    chrome_options.add_argument("--disable-webgl")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")

    # 웹드라이버 초기화 (ChromeDriver 경로가 PATH에 등록되어 있거나, 아래처럼 직접 지정 가능)
    # driver = webdriver.Chrome(executable_path="/path/to/chromedriver", options=chrome_options)
    driver = webdriver.Chrome(options=chrome_options)

    try:
        # 페이지 접속
        driver.get(url)
        # 페이지가 완전히 로드될 수 있도록 잠시 대기 (필요시 WebDriverWait 사용 가능)
        time.sleep(10)

        # 전체 페이지 스크린샷 찍기
        driver.save_screenshot(save_path)
        print(f"스크린샷이 정상적으로 저장되었습니다: {save_path}")

    except Exception as e:
        print(f"오류 발생: {e}")

    finally:
        driver.quit()

if __name__ == "__main__":
    # Binance Futures 페이지 전체화면 스크린샷 캡처 예제
    target_url = "https://upbit.com/full_chart?code=CRIX.UPBIT.KRW-BTC"
    capture_fullpage_screenshot(url=target_url, save_path="Captured_image/full_screenshot.png")
    

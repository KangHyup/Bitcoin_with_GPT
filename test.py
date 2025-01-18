import logging

logging.basicConfig(
    filename='data_fetcher.log', 
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s',
    encoding='utf-8'  # Python 3.9+ 에서 가능
)
logging.info("한글 로그 테스트")

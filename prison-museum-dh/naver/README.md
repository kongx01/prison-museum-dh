# Naver Blog Scraper

서대문형무소역사관 관련 네이버 블로그 포스트를 수집하는 스크립트.

## 사용 환경

- Python 3.10 이상
- `pip install -r requirements.txt`

## 사용 방법

```bash
python naver_blog_scraper.py
```

## 주의 사항

- 한국 외 지역에서 접속할 경우 PROXY_URL 설정이 필요할 수 있다.
- 서버 부하를 고려해 요청 사이에 0.8초의 대기 시간을 둔다.
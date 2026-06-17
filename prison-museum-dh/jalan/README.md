# Jalan Kuchikomi Scraper

자란(じゃらん)에서 아바시리감옥박물관에 대한 일본인 관람객 후기를 수집하는 스크립트.

## 사용 환경

- Python 3.10 이상
- `pip install -r requirements.txt`

## 사용 방법

```bash
python jalan_kuchikomi_scraper.py
```

## 옵션

- `--url`: 시작 URL (기본값: 아바시리감옥박물관)
- `--out`: 출력 CSV 경로
- `--delay`: 페이지 간 대기 시간(초)
- `--max-pages`: 최대 페이지 수 제한
- `--debug`: 디버그 모드
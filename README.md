# 한국 주식 모멘텀 분석 웹

FinanceDataReader를 사용해 KRX(한국거래소) 데이터를 분석하고, 모멘텀·RSI·거래량 추세 기반의 참고용 종목 목록을 보여주는 웹 애플리케이션입니다.

## ⚠ 주의사항

- **투자 권유가 아닙니다.** 10% 이상 상승을 보장하지 않습니다.
- 한국증권전산원·키움증권·미래에셋증권 등 실시간/공식 API와 무관합니다.
- 공개 데이터(FinanceDataReader)를 이용한 교육·참고용 도구입니다.
- 투자 결정과 손실은 전적으로 본인 책임입니다.

## 설치 및 실행

```bash
# 가상환경 (선택)
python -m venv venv
venv\Scripts\activate   # Windows

# 패키지 설치
pip install -r requirements.txt

# 서버 실행
python app.py
```

브라우저에서 http://127.0.0.1:5000 접속

## 기능

- KRX 상장 종목 기반 모멘텀·RSI·거래량 분석
- 점수 기반 상위 종목 추천 (5/10/15/20종목 선택 가능)
- 카드형 UI로 종목별 요약 정보 표시

## 데이터 소스

- FinanceDataReader (KRX, 네이버 금융 등)
- FinanceDataReader 미사용 시 yfinance로 대체 시도

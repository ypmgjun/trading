"""
한국 주식 분석 웹 애플리케이션
- FinanceDataReader를 사용한 KRX 데이터 분석
- 참고용이며, 투자 권유가 아님
"""

from flask import Flask, render_template, jsonify, request
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

app = Flask(__name__)

# FinanceDataReader 시도 (한국 주식 전문)
try:
    import FinanceDataReader as fdr
    USE_FDR = True
except ImportError:
    USE_FDR = False
    try:
        import yfinance as yf
    except ImportError:
        yf = None


def get_krx_stock_list():
    """KRX 상장 종목 목록 조회"""
    if USE_FDR:
        try:
            df = fdr.StockListing('KRX')
            return df[['Code', 'Name', 'Market']].dropna() if df is not None else pd.DataFrame()
        except Exception:
            return _get_sample_stocks()
    return _get_sample_stocks()


def _get_sample_stocks():
    """샘플 종목 (삼성전자, SK하이닉스, LG에너지솔루션 등)"""
    return pd.DataFrame({
        'Code': ['005930', '000660', '373220', '035420', '051910', '006400', '000270', '035720', '068270', '207940'],
        'Name': ['삼성전자', 'SK하이닉스', 'LG에너지솔루션', 'NAVER', 'LG화학', '삼성SDI', '기아', '카카오', '셀트리온', '삼성바이오로직스'],
        'Market': ['KOSPI'] * 10
    })


def get_stock_data(code, days=60):
    """개별 종목 시세 조회"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    if USE_FDR:
        try:
            ticker = code if len(str(code)) == 6 else str(code).zfill(6)
            df = fdr.DataReader(ticker, start_date, end_date)
            if df is not None and not df.empty:
                return df
        except Exception:
            pass

    # yfinance fallback
    if 'yf' in dir() and yf:
        suffix = '.KS' if code in ['005930', '000660', '035420', '051910', '006400', '000270', '035720', '068270', '207940'] else '.KQ'
        ticker = str(code).zfill(6) + suffix
        try:
            df = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=True)
            if df is not None and not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [c[0] for c in df.columns]
                return df
        except Exception:
            pass

    return pd.DataFrame()


def calculate_technical_indicators(df):
    """기술적 지표 계산"""
    if df is None or df.empty or len(df) < 5:
        return {}

    close = df['Close'] if 'Close' in df.columns else df.iloc[:, 3]  # Close 컬럼
    high = df['High'] if 'High' in df.columns else close
    low = df['Low'] if 'Low' in df.columns else close

    # 5일/20일 모멘텀
    momentum_5 = (close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) >= 6 else 0
    momentum_20 = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) >= 21 else momentum_5

    # RSI (간단 버전)
    delta = close.diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)
    avg_gain = gain.rolling(14).mean().iloc[-1] if len(gain) >= 14 else 0
    avg_loss = loss.rolling(14).mean().iloc[-1] if len(loss) >= 14 else 0
    rs = avg_gain / avg_loss if avg_loss != 0 else 100
    rsi = 100 - (100 / (1 + rs)) if avg_loss != 0 else 50

    # 거래량 추세
    if 'Volume' in df.columns:
        vol_recent = df['Volume'].tail(5).mean()
        vol_prev = df['Volume'].tail(20).head(15).mean()
        vol_trend = (vol_recent / vol_prev - 1) * 100 if vol_prev != 0 else 0
    else:
        vol_trend = 0

    # 종합 점수 (참고용 - 절대적 예측 아님)
    score = (
        min(momentum_5 * 2, 30) +           # 최근 상승 모멘텀
        min(momentum_20, 20) +               # 중기 추세
        (50 - abs(rsi - 50)) * 0.3 +        # RSI 극단 회피
        min(max(vol_trend, -10), 20)        # 거래량 증가
    )

    # 매수 적정가: 20일 이평(지지선) 참고. RSI 과매수 시 조정 구간 반영
    ma5 = close.rolling(5).mean().iloc[-1] if len(close) >= 5 else float(close.iloc[-1])
    ma20 = close.rolling(20).mean().iloc[-1] if len(close) >= 20 else ma5
    current = float(close.iloc[-1])
    if rsi >= 70:
        buy_price = round(min(ma20, current * 0.97), 0)  # 과매수: 조정 시 20일선 또는 -3% 구간
    elif rsi <= 30:
        buy_price = round(current, 0)  # 과매도: 현재가 근처 매수
    else:
        buy_price = round(ma20, 0)  # 기본: 20일 이평 지지선

    # 차트용 최근 20거래일 가격 이력
    try:
        chart_dates = [pd.Timestamp(x).strftime('%m/%d') for x in df.index[-20:]]
    except (AttributeError, TypeError):
        chart_dates = [str(i + 1) for i in range(min(20, len(close)))]
    chart_prices = [float(p) for p in close.tail(20).tolist()]

    return {
        'momentum_5': round(momentum_5, 2),
        'momentum_20': round(momentum_20, 2),
        'rsi': round(rsi, 1),
        'vol_trend': round(vol_trend, 1),
        'score': round(max(0, score), 1),
        'current_price': current,
        'change_1d': round((close.iloc[-1] / close.iloc[-2] - 1) * 100, 2) if len(close) >= 2 else 0,
        'buy_price': int(buy_price),
        'buy_discount': round((1 - buy_price / current) * 100, 1),  # 현재가 대비 할인율
        'chart_dates': chart_dates,
        'chart_prices': chart_prices
    }


def analyze_and_rank_stocks(max_stocks=50, top_n=10):
    """
    종목 분석 및 순위 산출
    주의: 이 분석은 참고용이며, 10% 상승을 보장하지 않습니다.
    """
    stock_list = get_krx_stock_list()
    results = []

    # 샘플 모드: 상위 N개만 분석 (전체는 시간 오래 걸림)
    codes = stock_list['Code'].tolist()[:max_stocks]
    names = stock_list['Name'].tolist()[:max_stocks]
    markets = stock_list['Market'].tolist()[:max_stocks]

    for code, name, market in zip(codes, names, markets):
        try:
            df = get_stock_data(code)
            if df is not None and len(df) >= 10:
                indicators = calculate_technical_indicators(df)
                if indicators:
                    results.append({
                        'code': str(code).zfill(6),
                        'name': name,
                        'market': str(market) if pd.notna(market) else 'KOSPI',
                        **indicators
                    })
        except Exception:
            continue

    # 점수 기준 정렬
    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:top_n]


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/recommendations')
def api_recommendations():
    """추천 종목 API"""
    try:
        top_n = request.args.get('top', 10, type=int)
        top_n = min(max(top_n, 5), 20)
        stocks = analyze_and_rank_stocks(max_stocks=80, top_n=top_n)
        return jsonify({'success': True, 'data': stocks, 'updated': datetime.now().strftime('%Y-%m-%d %H:%M')})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/search')
def api_search():
    """종목 검색"""
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify({'success': True, 'data': []})

    stock_list = get_krx_stock_list()
    if query.isdigit():
        matched = stock_list[stock_list['Code'].astype(str).str.contains(query)]
    else:
        matched = stock_list[stock_list['Name'].str.contains(query, case=False, na=False)]

    results = matched.head(10).to_dict('records')
    return jsonify({'success': True, 'data': results})


if __name__ == '__main__':
    print("=" * 50)
    print("한국 주식 분석 웹 - 참고용 (투자권유 아님)")
    print("http://127.0.0.1:5000 에서 실행")
    print("=" * 50)
    app.run(debug=True, port=5000)

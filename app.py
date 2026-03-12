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


# 목표가: 최근 출처(네이버 금융)에서 파싱. 실패 시 참고용 샘플
BROKER_TARGETS_FALLBACK = {
    '005930': [('컨센서스(참고)', 85000)],
    '000660': [('컨센서스(참고)', 280000)],
    '035420': [('컨센서스(참고)', 235000)],
}


def fetch_target_from_naver(code):
    """네이버 금융 종목분석 페이지에서 목표주가 파싱 (최근 출처 분석)"""
    import re
    code = str(code).zfill(6)
    url = f'https://finance.naver.com/item/coinfo.naver?code={code}'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    try:
        import requests
        r = requests.get(url, headers=headers, timeout=8)
        r.encoding = r.apparent_encoding or 'euc-kr'
        html = r.text
    except Exception:
        return None, None

    # 목표주가 패턴 (네이버 종목분석 페이지: 투자의견|목표주가| 4.00매수 l 243,040)
    match = re.search(r'목표\s*주가[^0-9]*([0-9,]+)', html)
    if not match:
        match = re.search(r'목표주가[^0-9]*([0-9,]+)', html)
    if not match:
        match = re.search(r'[\d.]+\s*매수\s*[l|]\s*([0-9,]+)', html)
    if not match:
        match = re.search(r'투자의견[^0-9]*([0-9,]+)', html)
    if not match:
        match = re.search(r'(\d{1,3}(?:,\d{3})+)\s*원', html)
    if match:
        num_str = match.group(1).replace(',', '')
        if num_str.isdigit():
            price = int(num_str)
            if 1000 <= price <= 99999999:
                return [{'broker': '네이버 금융(컨센서스)', 'target_price': price}], url
    return None, url


def get_broker_targets(code):
    """목표가: 최근 출처(웹) 분석 후 반환, 출처 URL 1개"""
    code = str(code).zfill(6)
    targets, source_url = fetch_target_from_naver(code)
    if targets:
        return {'targets': targets, 'source_url': source_url}
    raw = BROKER_TARGETS_FALLBACK.get(code, [])
    return {
        'targets': [{'broker': b, 'target_price': p} for b, p in raw],
        'source_url': f'https://finance.naver.com/item/coinfo.naver?code={code}' if raw else None
    }


def get_stock_data(code, days=400):
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

    # 매수/매도 적정가
    ma5 = close.rolling(5).mean().iloc[-1] if len(close) >= 5 else float(close.iloc[-1])
    ma20 = close.rolling(20).mean().iloc[-1] if len(close) >= 20 else ma5
    high20 = float(close.tail(20).max()) if len(close) >= 20 else float(close.iloc[-1])
    current = float(close.iloc[-1])

    if rsi >= 70:
        buy_price = round(min(ma20, current * 0.97), 0)
    elif rsi <= 30:
        buy_price = round(current, 0)
    else:
        buy_price = round(ma20, 0)

    # 매도 적정가: 20일 고점·이평 상단 참고. RSI 과매도 시 보수적 목표
    if rsi <= 30:
        sell_price = round(current * 1.05, 0)  # 과매도: 5% 회복 목표
    else:
        sell_price = round(max(high20 * 1.02, ma20 * 1.05, current * 1.03), 0)

    # 차트용 기간별 가격 이력 (20일, 60일=월간, 252일=연간)
    def make_chart_data(n):
        tail = close.tail(n)
        try:
            dates = [pd.Timestamp(x).strftime('%m/%d') for x in df.index[-n:]]
        except (AttributeError, TypeError):
            dates = [str(i + 1) for i in range(len(tail))]
        return {'dates': dates, 'prices': [float(p) for p in tail.tolist()]}

    chart_20 = make_chart_data(min(20, len(close)))
    chart_60 = make_chart_data(min(60, len(close)))
    chart_252 = make_chart_data(min(252, len(close)))

    return {
        'momentum_5': round(momentum_5, 2),
        'momentum_20': round(momentum_20, 2),
        'rsi': round(rsi, 1),
        'vol_trend': round(vol_trend, 1),
        'score': round(max(0, score), 1),
        'current_price': current,
        'change_1d': round((close.iloc[-1] / close.iloc[-2] - 1) * 100, 2) if len(close) >= 2 else 0,
        'buy_price': int(buy_price),
        'sell_price': int(sell_price),
        'buy_discount': round((1 - buy_price / current) * 100, 1),
        'sell_premium': round((sell_price / current - 1) * 100, 1),
        'chart_20': chart_20,
        'chart_60': chart_60,
        'chart_252': chart_252
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

    # 점수 기준 정렬 후 상위 N개만 목표가 조회 (출처 요청 최소화)
    results.sort(key=lambda x: x['score'], reverse=True)
    top = results[:top_n]
    for row in top:
        gt = get_broker_targets(row['code'])
        row['broker_targets'] = gt.get('targets', [])
        row['target_source_url'] = gt.get('source_url') or ''
    return top


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


@app.route('/api/price')
def api_price():
    """단일 종목 최신가 조회 (갱신용)"""
    code = request.args.get('code', '')
    if not code or len(str(code)) < 5:
        return jsonify({'success': False, 'error': '종목코드 필요'})
    code = str(code).zfill(6)
    try:
        df = get_stock_data(code, days=30)
        if df is None or len(df) < 2:
            return jsonify({'success': False, 'error': '데이터 없음'})
        close = df['Close'] if 'Close' in df.columns else df.iloc[:, 3]
        current = float(close.iloc[-1])
        change = round((close.iloc[-1] / close.iloc[-2] - 1) * 100, 2) if len(close) >= 2 else 0
        return jsonify({
            'success': True,
            'current_price': current,
            'change_1d': change,
            'updated': datetime.now().strftime('%H:%M')
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/search')
def api_search():
    """종목 검색 (자동완성용)"""
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


@app.route('/api/analyze')
def api_analyze():
    """종목명/코드 입력 시 단일 종목 분석"""
    import re
    query = request.args.get('q', '').strip()
    m = re.search(r'\((\d{6})\)', query)
    if m:
        query = m.group(1)
    if not query:
        return jsonify({'success': False, 'error': '종목명 또는 코드를 입력해 주세요.'})

    stock_list = get_krx_stock_list()
    if query.isdigit():
        matched = stock_list[stock_list['Code'].astype(str) == str(query).zfill(6)]
        if matched.empty:
            matched = stock_list[stock_list['Code'].astype(str).str.contains(query)]
    else:
        matched = stock_list[stock_list['Name'].str.contains(query, case=False, na=False)]

    if matched.empty:
        return jsonify({'success': False, 'error': f'"{query}"에 해당하는 종목을 찾을 수 없습니다.'})

    row = matched.iloc[0]
    code = str(row['Code']).zfill(6)
    name = str(row['Name'])
    market = str(row['Market']) if pd.notna(row['Market']) else 'KOSPI'

    try:
        df = get_stock_data(code)
        if df is None or len(df) < 10:
            return jsonify({'success': False, 'error': f'"{name}"의 시세 데이터를 불러올 수 없습니다.'})

        indicators = calculate_technical_indicators(df)
        if not indicators:
            return jsonify({'success': False, 'error': '분석 결과를 산출할 수 없습니다.'})

        result = {'code': code, 'name': name, 'market': market, **indicators}
        gt = get_broker_targets(code)
        result['broker_targets'] = gt.get('targets', [])
        result['target_source_url'] = gt.get('source_url') or ''
        return jsonify({'success': True, 'data': result, 'updated': datetime.now().strftime('%Y-%m-%d %H:%M')})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


if __name__ == '__main__':
    print("=" * 50)
    print("한국 주식 분석 웹 - 참고용 (투자권유 아님)")
    print("http://127.0.0.1:5000 에서 실행")
    print("=" * 50)
    app.run(debug=True, port=5000)

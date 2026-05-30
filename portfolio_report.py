# portfolio_report.py
# 포트폴리오 중심 일일 보고서 생성기 (풀버전)
# 포함 기법:
#   - 터틀 트레이딩 (20캔들 신고가/신저가)
#   - 3단계 분할 익절
#   - ATR 변동성 맞춤 익절
#   - RSI 과매도/과매수
#   - 골든크로스/데드크로스
#   - 이동평균선 이탈 방어매도
#   - 분할 추가매수 (-5%, -10%)
#   - 거래량 동반 하락 감지
#   - VIX 시장 환경 필터
#   - 공포/탐욕 지수
#   - 장단기 금리차 (경기침체 신호)
#   - 계절성 알림
#   - 섹터 로테이션
#   - 포지션 사이징
#   - 외국인/기관 수급
#   - 심리 체크리스트
#   - 종목별 추천 익절 기법
# pip install requests pandas yfinance beautifulsoup4

import requests
import pandas as pd
import yfinance as yf
import json
import os
import datetime as dt
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup
import warnings
warnings.filterwarnings("ignore")

KST = dt.timezone(dt.timedelta(hours=9))

# =====================================================
# ✅ 설정값
# =====================================================
APP_KEY            = os.environ.get("APP_KEY", "")
APP_SECRET         = os.environ.get("APP_SECRET", "")
ACCOUNT_NO         = os.environ.get("ACCOUNT_NO", "")
ACCOUNT_CODE       = "01"
GMAIL_ADDRESS      = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
RECEIVE_ADDRESS    = os.environ.get("RECEIVE_ADDRESS", "")
TOKEN_FILE         = "token.json"
TOTAL_ASSETS       = 24_000_000  # 총 자산 2,400만원

# =====================================================
# 포트폴리오
# =====================================================
HOLDINGS = [
    ("005490", "POSCO홀딩스",                  7,   435500, "KR"),
    ("005930", "삼성전자",                      4,    60100, "KR"),
    ("005935", "삼성전자우",                    5,   187520, "KR"),
    ("007660", "이수페타시스",                  5,   133960, "KR"),
    ("010780", "아이에스동서",                  1,    38450, "KR"),
    ("094360", "챔스미디어",                    9,    27361, "KR"),
    ("247540", "에코프로비엠",                  4,   268000, "KR"),
    ("304100", "솔트룩스",                      3,    29383, "KR"),
    ("010120", "LS ELECTRIC",                   4,   259375, "KR"),
    ("QQQ",    "Invesco QQQ",                   1,   907209, "US"),
    ("SPYG",   "SPDR S&P500 Growth",            7,   157479, "US"),
    ("SCHD",   "Schwab Dividend",              26,    40186, "US"),
    ("VOO",    "Vanguard S&P500",               2,   907785, "US"),
    ("BOTT",   "THEMES HUMANOID ROBOTICS ETF",  3,    82969, "US"),
    ("360750", "TIGER 미국S&P500",             55,    24635, "ETF_KR"),
    ("426030", "TIME 나스닥100",               30,    35102, "ETF_KR"),
    ("458730", "TIGER 미국배당다운존스",        56,    14074, "ETF_KR"),
    ("364970", "TIGER 바이오TOP10",            10,     7520, "ETF_KR"),
    ("465580", "RISE 미국AI밸류체인",          47,    17987, "ETF_KR"),
    ("464310", "TIGER 글로벌AI&로보틱스INDXX", 10,    17165, "ETF_KR"),
    ("441680", "TIGER 나스닥100커버드콜",     111,    10719, "ETF_KR"),
    ("466920", "SOL AI반도체TOP2플러스",        5,    21215, "ETF_KR"),
    ("461950", "AI반도체TOP2플러스",            3,    45856, "ETF_KR"),
]

SWING_CANDIDATES = [
    ("005930", "삼성전자"),
    ("000660", "SK하이닉스"),
    ("035420", "NAVER"),
    ("329180", "HD현대중공업"),
    ("051910", "LG화학"),
    ("006400", "삼성SDI"),
    ("207940", "삼성바이오로직스"),
    ("068270", "셀트리온"),
    ("005490", "POSCO홀딩스"),
    ("010120", "LS ELECTRIC"),
]

THEME_KEYWORDS = {
    "AI/반도체": ["AI", "반도체", "HBM", "SK하이닉스", "이수페타시스", "솔트룩스"],
    "전력/전기": ["전력", "전기", "LS", "효성"],
    "2차전지":   ["에코프로", "삼성SDI", "LG화학"],
    "조선/해운": ["HD현대", "조선", "해운"],
    "바이오":    ["바이오", "셀트리온", "삼성바이오"],
    "로봇":      ["로봇", "ROBOT", "HUMANOID"],
}

# =====================================================
# 유틸
# =====================================================
def get_theme(name):
    for theme, words in THEME_KEYWORDS.items():
        if any(w.lower() in name.lower() for w in words):
            return theme
    return "일반"

def get_recommend_method(name, market):
    etf_kw    = ["TIGER","RISE","SOL","TIME","KODEX","ACE","QQQ","VOO","SCHD","SPYG","BOTT"]
    large_kw  = ["삼성전자","POSCO","LS ELECTRIC","SK하이닉스","현대","삼성바이오","셀트리온"]
    small_kw  = ["챔스미디어","솔트룩스","에코프로","아이에스동서","이수페타시스"]
    if market in ("ETF_KR","US") or any(k in name for k in etf_kw):
        return "📊 분할익절", "#27ae60", "ETF/안정형 → 단계별 익절"
    elif any(k in name for k in large_kw):
        return "🐢 터틀익절", "#8e44ad", "대형주 → 추세 끝까지"
    elif any(k in name for k in small_kw):
        return "📈 ATR익절", "#e74c3c", "소형/테마주 → 변동성 맞춤"
    return "📊 분할익절", "#27ae60", "기본 → 분할익절"

# =====================================================
# 토큰 관리
# =====================================================
def get_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE,"r") as f:
            data = json.load(f)
        if data.get("issued_at") == dt.datetime.now(KST).strftime("%Y-%m-%d"):
            return data["access_token"]
    url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    res = requests.post(url, headers={"content-type":"application/json"},
                        data=json.dumps({"grant_type":"client_credentials","appkey":APP_KEY,"appsecret":APP_SECRET}))
    token_data = res.json()
    token_data["issued_at"] = dt.datetime.now(KST).strftime("%Y-%m-%d")
    with open(TOKEN_FILE,"w") as f:
        json.dump(token_data,f)
    return token_data["access_token"]

# =====================================================
# 국내주식 현재가
# =====================================================
def get_kr_price(token, code):
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
        "content-type":"application/json",
        "authorization":f"Bearer {token}",
        "appkey":APP_KEY,"appsecret":APP_SECRET,
        "tr_id":"FHKST01010100",
    }
    try:
        res    = requests.get(url, headers=headers, params={"FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":code}, timeout=10)
        output = res.json().get("output",{})
        return (int(output.get("stck_prpr",0)), float(output.get("prdy_ctrt",0)),
                int(output.get("acml_vol",0)), int(output.get("w52_hgpr",0)), int(output.get("w52_lwpr",0)))
    except:
        return 0,0,0,0,0

# =====================================================
# 해외주식 현재가
# =====================================================
def get_us_price(ticker):
    try:
        t   = yf.Ticker(ticker)
        info = t.info
        usd = info.get("currentPrice") or info.get("regularMarketPrice",0)
        fx  = yf.Ticker("USDKRW=X").info.get("regularMarketPrice",1380)
        return usd, int(usd*fx), info.get("regularMarketChangePercent",0), info.get("fiftyTwoWeekHigh",0), info.get("fiftyTwoWeekLow",0), fx
    except:
        return 0,0,0,0,0,1380

# =====================================================
# 거시경제
# =====================================================
def get_macro():
    tickers = {
        "S&P500":"^GSPC","나스닥":"^IXIC","다우":"^DJI",
        "VIX(공포지수)":"^VIX","달러인덱스":"DX-Y.NYB",
        "원달러환율":"USDKRW=X","WTI유가":"CL=F","금":"GC=F",
        "미국10년금리":"^TNX","미국2년금리":"^IRX",
    }
    result = {}
    for name, sym in tickers.items():
        try:
            hist = yf.Ticker(sym).history(period="2d").dropna()
            if len(hist) >= 2:
                prev  = hist["Close"].iloc[-2]
                today = hist["Close"].iloc[-1]
                result[name] = {"가격":round(today,2),"등락률":round((today-prev)/prev*100,2)}
            else:
                result[name] = {"가격":0,"등락률":0}
        except:
            result[name] = {"가격":0,"등락률":0}
    return result

# =====================================================
# 공포/탐욕 지수
# =====================================================
def get_fear_greed():
    try:
        res  = requests.get("https://fear-and-greed-index.p.rapidapi.com/v1/fgi",
                            headers={"X-RapidAPI-Key":"demo","X-RapidAPI-Host":"fear-and-greed-index.p.rapidapi.com"},
                            timeout=5)
        data = res.json()
        val  = data.get("fgi",{}).get("now",{}).get("value",50)
        txt  = data.get("fgi",{}).get("now",{}).get("valueText","Neutral")
        return int(val), txt
    except:
        # fallback: VIX로 대체 계산
        try:
            vix = yf.Ticker("^VIX").history(period="1d").dropna()["Close"].iloc[-1]
            if vix >= 40:   return 10,  "극단적 공포"
            elif vix >= 30: return 25,  "공포"
            elif vix >= 20: return 50,  "중립"
            elif vix >= 15: return 70,  "탐욕"
            else:           return 85,  "극단적 탐욕"
        except:
            return 50, "중립"

# =====================================================
# 장단기 금리차 (경기침체 신호)
# =====================================================
def get_yield_curve(macro):
    try:
        y10 = macro.get("미국10년금리",{}).get("가격",0)
        y2  = macro.get("미국2년금리",{}).get("가격",0)
        diff = round(y10 - y2, 3)
        if diff < -0.5:   signal = "🔴 심각한 역전 (경기침체 위험)"
        elif diff < 0:    signal = "🟡 역전 (경기침체 주의)"
        elif diff < 0.5:  signal = "🟢 정상화 중"
        else:             signal = "🟢 정상 (경기 양호)"
        return diff, signal
    except:
        return 0, "-"

# =====================================================
# 계절성 알림
# =====================================================
def get_seasonality():
    month = dt.datetime.now(KST).month
    season_map = {
        1:  ("🟢 1월 효과", "1월은 역사적으로 상승 확률 높음. 신규 자금 유입 시기"),
        2:  ("🟡 2월 조정", "1월 랠리 후 조정 구간. 선별적 매매 권장"),
        3:  ("🟢 3월 반등", "분기말 기관 매수. 기술적 반등 가능성"),
        4:  ("🟡 4월 주의", "실적 시즌 변동성 확대. 눌림매수 기회"),
        5:  ("🔴 5월 경고", "Sell in May! 5~10월 역사적 약세 구간 시작"),
        6:  ("🟡 6월 보합", "여름 거래 감소. 방어적 포지션 권장"),
        7:  ("🟢 7월 반등", "여름 랠리 가능성. 실적 호조 종목 주목"),
        8:  ("🟡 8월 변동", "변동성 확대 구간. 리스크 관리 강화"),
        9:  ("🔴 9월 경고", "역사적으로 최악의 달! 비중 축소 고려"),
        10: ("🟢 10월 기회", "역사적 바닥 구간. 역발상 매수 기회"),
        11: ("🟢 11월 강세", "산타랠리 준비. 공격적 매매 가능"),
        12: ("🟢 12월 랠리", "산타랠리! 연말 기관 매수. 상승 확률 높음"),
    }
    return season_map.get(month, ("🟡 보통", "특별한 계절성 없음"))

# =====================================================
# VIX 시장 환경 필터
# =====================================================
def get_vix_signal(macro):
    vix = macro.get("VIX(공포지수)",{}).get("가격",20)
    if vix >= 40:
        return "🟢 극단적 공포 → 역발상 매수 기회!", "#27ae60"
    elif vix >= 30:
        return "🔴 공포 구간 → 단타 금지, 스윙 신중", "#e74c3c"
    elif vix >= 25:
        return "🟡 불안 구간 → 보수적 매매 권장", "#f39c12"
    elif vix >= 20:
        return "🟡 주의 구간 → 리스크 관리 강화", "#f39c12"
    else:
        return "🟢 안정 구간 → 적극적 매매 가능", "#27ae60"

# =====================================================
# 섹터 로테이션
# =====================================================
def get_sector_rotation():
    sectors = {
        "기술(XLK)":    "XLK",
        "금융(XLF)":    "XLF",
        "헬스케어(XLV)": "XLV",
        "에너지(XLE)":  "XLE",
        "산업재(XLI)":  "XLI",
        "소재(XLB)":    "XLB",
        "유틸리티(XLU)": "XLU",
    }
    result = []
    for name, ticker in sectors.items():
        try:
            hist = yf.Ticker(ticker).history(period="5d").dropna()
            if len(hist) >= 2:
                rate = (hist["Close"].iloc[-1] - hist["Close"].iloc[-5]) / hist["Close"].iloc[-5] * 100
                result.append({"섹터": name, "5일수익률": round(rate, 2)})
        except:
            pass
    return sorted(result, key=lambda x: x["5일수익률"], reverse=True)

# =====================================================
# RSI 계산
# =====================================================
def get_rsi(code, market, period=14):
    try:
        ticker = code + ".KS" if market in ("KR","ETF_KR") else code
        hist   = yf.Ticker(ticker).history(period="2mo").dropna()
        if len(hist) < period+1:
            return 50
        delta = hist["Close"].diff()
        gain  = delta.where(delta>0,0).rolling(period).mean()
        loss  = (-delta.where(delta<0,0)).rolling(period).mean()
        rs    = gain / loss
        rsi   = 100 - (100/(1+rs))
        return round(rsi.iloc[-1], 1)
    except:
        return 50

# =====================================================
# 골든크로스/데드크로스
# =====================================================
def get_ma_cross(code, market):
    try:
        ticker = code + ".KS" if market in ("KR","ETF_KR") else code
        hist   = yf.Ticker(ticker).history(period="4mo").dropna()
        if len(hist) < 60:
            return "-", "#888"
        ma20 = hist["Close"].rolling(20).mean().iloc[-1]
        ma60 = hist["Close"].rolling(60).mean().iloc[-1]
        curr = hist["Close"].iloc[-1]
        if ma20 > ma60 and curr > ma20:
            return "🟢 골든크로스 (강세)", "#27ae60"
        elif ma20 < ma60 and curr < ma20:
            return "🔴 데드크로스 (약세)", "#e74c3c"
        elif curr > ma20 > ma60:
            return "🟢 상승추세 유지", "#27ae60"
        elif curr < ma20:
            return "🟡 20일선 하회 주의", "#f39c12"
        else:
            return "🟡 횡보 구간", "#888"
    except:
        return "-", "#888"

# =====================================================
# ATR 계산
# =====================================================
def get_atr(code, market, period=14):
    try:
        ticker = code + ".KS" if market in ("KR","ETF_KR") else code
        hist   = yf.Ticker(ticker).history(period="1mo").dropna()
        if len(hist) < period:
            return 0, "중간"
        hist["TR"] = hist.apply(
            lambda r: max(r["High"]-r["Low"],
                          abs(r["High"]-hist["Close"].shift(1).get(r.name,r["Close"])),
                          abs(r["Low"]-hist["Close"].shift(1).get(r.name,r["Close"]))), axis=1)
        atr_pct = hist["TR"].tail(period).mean() / hist["Close"].iloc[-1] * 100
        vol = "높음" if atr_pct>=4 else "낮음" if atr_pct<2 else "중간"
        return round(atr_pct,2), vol
    except:
        return 0, "중간"

# =====================================================
# 거래량 동반 하락 감지
# =====================================================
def get_volume_signal(code, market, current_rate):
    try:
        ticker  = code + ".KS" if market in ("KR","ETF_KR") else code
        hist    = yf.Ticker(ticker).history(period="1mo").dropna()
        if len(hist) < 5:
            return "확인불가"
        avg_vol = hist["Volume"].tail(20).mean()
        now_vol = hist["Volume"].iloc[-1]
        vol_ratio = now_vol / avg_vol if avg_vol > 0 else 1
        if current_rate < -2 and vol_ratio > 1.5:
            return "⚠️ 거래량 동반 하락 (추가매수 금지!)"
        elif current_rate < -2 and vol_ratio < 0.7:
            return "✅ 저거래량 하락 (추가매수 고려)"
        elif current_rate > 3 and vol_ratio > 2:
            return "🔥 거래량 급증 + 상승 (강세 신호)"
        return "정상"
    except:
        return "확인불가"

# =====================================================
# 포지션 사이징 (신호 개수에 따라 투자금 결정)
# =====================================================
def get_position_size(rsi, ma_signal, turtle_signal, vix_signal):
    score = 0
    if rsi <= 35:          score += 1  # RSI 과매도
    if "골든크로스" in ma_signal or "상승추세" in ma_signal: score += 1
    if "매수신호" in turtle_signal: score += 1
    if "안정" in vix_signal or "기회" in vix_signal: score += 1

    max_loss = TOTAL_ASSETS * 0.02
    if score >= 3:
        return f"🔥 풀 투자 ({score}개 신호 일치)", int(max_loss * 3)
    elif score == 2:
        return f"⭐ 절반 투자 ({score}개 신호 일치)", int(max_loss * 1.5)
    elif score == 1:
        return f"⚠️ 소액만 ({score}개 신호)", int(max_loss * 0.5)
    else:
        return "❌ 진입 금지 (신호 없음)", 0

# =====================================================
# 외국인/기관 수급 (네이버 증권)
# =====================================================
def get_investor_flow(code, market):
    if market not in ("KR","ETF_KR"):
        return "-", "-"
    try:
        url = f"https://finance.naver.com/item/frgn.naver?code={code}"
        res = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=5)
        res.encoding = "euc-kr"
        soup = BeautifulSoup(res.text, "html.parser")
        rows = soup.select("table.type2 tr")
        if len(rows) >= 2:
            tds = rows[1].select("td")
            if len(tds) >= 5:
                foreign = tds[3].get_text(strip=True)
                inst    = tds[4].get_text(strip=True) if len(tds) > 4 else "-"
                return foreign, inst
        return "-", "-"
    except:
        return "-", "-"

# =====================================================
# 3가지 익절 기법 + 분할 추가매수
# =====================================================
def calc_signals(avg, current, code, market, qty, high52, low52, current_rate):
    if current == 0 or avg == 0:
        return {k:"-" for k in ["추가매수","방어매도","터틀익절","분할익절","atr익절","변동성","거래량신호"]}

    profit_rate = (current - avg) / avg * 100

    # 분할 추가매수
    vol_signal = get_volume_signal(code, market, current_rate)
    if "추가매수 금지" in vol_signal:
        add_buy = f"⛔ {vol_signal}"
    elif current <= avg * 0.90:
        add_buy = f"2차추가 {int(current*0.97):,}원 (평단-10%)"
    elif current <= avg * 0.95:
        add_buy = f"1차추가 {int(current*0.97):,}원 (평단-5%)"
    else:
        add_buy = "-"

    # 방어매도 (이동평균선 이탈 포함)
    ma_cross, _ = get_ma_cross(code, market)
    if current <= avg * 0.92:
        def_sell = f"{int(avg*0.92):,}원 ⚠️ 손절"
    elif current <= avg * 0.97:
        def_sell = f"{int(avg*0.95):,}원 (방어)"
    elif "데드크로스" in ma_cross:
        def_sell = f"⚠️ 데드크로스 → 비중 축소 고려"
    else:
        def_sell = "-"

    # 터틀 익절
    try:
        ticker = code+".KS" if market in ("KR","ETF_KR") else code
        hist   = yf.Ticker(ticker).history(period="2mo").dropna()
        low20  = int(hist["Low"].tail(20).min()) if len(hist)>=20 else int(avg*0.93)
        turtle_sell = f"{low20:,}원 (20캔들저점 이탈→전량)"
    except:
        turtle_sell = "-"

    # 3단계 분할 익절
    q1,q2 = max(1,int(qty*0.3)), max(1,int(qty*0.3))
    q3    = max(1, qty-q1-q2)
    p1,p2,p3 = int(avg*1.10), int(avg*1.20), int(avg*1.30)
    if profit_rate >= 30:
        split_sell = f"✅3차({q3}주/{p3:,}원) ← 현재"
    elif profit_rate >= 20:
        split_sell = f"✅2차({q2}주/{p2:,}원) ← 현재 | 3차({q3}주/{p3:,}원)"
    elif profit_rate >= 10:
        split_sell = f"✅1차({q1}주/{p1:,}원) ← 현재 | 2차({q2}주/{p2:,}원)"
    else:
        split_sell = f"1차({q1}주/{p1:,}원)|2차({q2}주/{p2:,}원)|3차({q3}주/{p3:,}원)"

    # ATR 변동성 익절
    atr_pct, vol = get_atr(code, market)
    if vol == "높음":
        atr_sell = f"{int(avg*1.20):,}/{int(avg*1.40):,}원 (고변동)"
    elif vol == "낮음":
        atr_sell = f"{int(avg*1.07):,}/{int(avg*1.12):,}원 (저변동)"
    else:
        atr_sell = f"{int(avg*1.10):,}/{int(avg*1.20):,}원 (중간)"

    return {
        "추가매수": add_buy, "방어매도": def_sell,
        "터틀익절": turtle_sell, "분할익절": split_sell,
        "atr익절": atr_sell, "변동성": f"{vol}({atr_pct}%)",
        "거래량신호": vol_signal,
    }

# =====================================================
# 터틀 신호 (스윙 추천용)
# =====================================================
def get_turtle_signal(code, current_price):
    try:
        hist   = yf.Ticker(code+".KS").history(period="2mo").dropna()
        if len(hist) < 20: return "-","#888","-","-","-"
        high20 = int(hist["High"].tail(20).max())
        low20  = int(hist["Low"].tail(20).min())
        curr   = current_price or int(hist["Close"].iloc[-1])
        if curr >= high20:   sig,col = "🔴 매수신호(신고가돌파)","#e74c3c"
        elif curr <= low20:  sig,col = "🔵 매도신호(신저가이탈)","#2980b9"
        else:
            gap  = round((high20-curr)/curr*100,1)
            sig,col = f"⏳ 대기(신고가까지{gap}%)","#888"
        loss_pct = (curr-low20)/curr*100 if curr>low20 else 1
        rec      = int(TOTAL_ASSETS*0.02/(loss_pct/100)) if loss_pct>0 else 0
        return sig, col, f"{high20:,}원", f"{low20:,}원", f"{rec:,}원"
    except:
        return "-","#888","-","-","-"

# =====================================================
# 스윙 추천 (RSI + 골든크로스 + 터틀 통합)
# =====================================================
def get_swing_picks(token):
    picks = []
    for code, name in SWING_CANDIDATES:
        price, rate, volume, high52, low52 = get_kr_price(token, code)
        if price == 0: continue
        score, reason = 0, []
        if low52>0 and (price-low52)/low52*100<=30: score+=20; reason.append("52주저가근접")
        if high52>0 and -20<=(price-high52)/high52*100<=-5: score+=20; reason.append("고점눌림")
        if 1<=rate<=5:    score+=20; reason.append("안정상승")
        elif rate>5:      score+=10; reason.append("강한상승")
        elif -3<=rate<0:  score+=5;  reason.append("소폭하락(기회)")
        if volume>=1_000_000: score+=20; reason.append("거래량풍부")
        elif volume>=500_000: score+=10; reason.append("거래량양호")
        theme = get_theme(name)
        if theme!="일반": score+=20; reason.append(f"{theme}테마")

        rsi = get_rsi(code, "KR")
        ma_sig, ma_col = get_ma_cross(code, "KR")
        if rsi <= 35:    score+=15; reason.append(f"RSI과매도({rsi})")
        elif rsi >= 70:  score-=10
        if "골든크로스" in ma_sig: score+=15; reason.append("골든크로스")
        elif "데드크로스" in ma_sig: score-=15

        turtle_sig, turtle_col, high20, low20, rec_buy = get_turtle_signal(code, price)
        if "매수신호" in turtle_sig: score+=15; reason.append("터틀매수신호")

        picks.append({
            "종목명":name,"현재가":price,"추천매수가":int(price*0.98),
            "추천주수":max(1,int(1_000_000//(price*0.98))),
            "점수":score,"근거":", ".join(reason) or "기본관찰",
            "기간":"1~2주 스윙",
            "RSI":rsi,"MA신호":ma_sig,"MA색상":ma_col,
            "터틀신호":turtle_sig,"터틀색상":turtle_col,
            "20캔들고점":high20,"20캔들저점":low20,"추천투자금":rec_buy,
        })
    return sorted(picks,key=lambda x:x["점수"],reverse=True)[:5]

# =====================================================
# 심리 체크리스트
# =====================================================
def get_psychology_checklist(macro, fear_greed_val):
    vix = macro.get("VIX(공포지수)",{}).get("가격",20)
    checks = []
    if fear_greed_val >= 75:
        checks.append("🔴 시장 탐욕 과열 — FOMO 매수 조심! 고점일 수 있음")
    elif fear_greed_val <= 25:
        checks.append("🟢 극단적 공포 — 역발상 매수 기회 탐색")
    if vix >= 30:
        checks.append("🔴 VIX 고점 — 단타 금지, 스윙도 신중하게")
    checks.append("💭 오늘 매매 전 체크: 감정이 아닌 시스템 신호를 따르고 있는가?")
    checks.append("✂️ 손절 신호 나왔는데 버티고 있지는 않은가?")
    checks.append("💰 익절 신호 나왔는데 더 오를 것 같아 안 팔고 있지는 않은가?")
    checks.append("📊 오늘 진입은 2% 룰 안에서 이루어지고 있는가?")
    return checks

# =====================================================
# 이메일 전송
# =====================================================
def send_email(subject, html_body):
    msg = MIMEMultipart()
    msg["From"] = GMAIL_ADDRESS
    msg["To"]   = RECEIVE_ADDRESS
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body,"html","utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com",465) as smtp:
            smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            smtp.send_message(msg)
            print("✅ 이메일 전송 성공!")
    except Exception as e:
        print(f"❌ 이메일 전송 실패: {e}")

# =====================================================
# HTML 보고서 생성
# =====================================================
def build_report(token):
    today = dt.datetime.now(KST).strftime("%Y년 %m월 %d일 %H:%M")

    print("🌍 거시경제 수집 중...")
    macro = get_macro()

    print("😱 공포/탐욕 지수 수집 중...")
    fg_val, fg_text = get_fear_greed()

    print("📈 장단기 금리차 분석 중...")
    yield_diff, yield_signal = get_yield_curve(macro)

    print("📅 계절성 분석 중...")
    season_title, season_desc = get_seasonality()

    print("🌡️ VIX 필터 분석 중...")
    vix_signal, vix_color = get_vix_signal(macro)

    print("🔄 섹터 로테이션 분석 중...")
    sectors = get_sector_rotation()

    print("💼 포트폴리오 수집 중...")
    portfolio_rows = []
    total_invest = total_current = 0

    for code, name, qty, avg, market in HOLDINGS:
        print(f"  → {name} 조회 중...")
        if market in ("KR","ETF_KR"):
            price,rate,volume,high52,low52 = get_kr_price(token,code)
            price_display = f"{price:,}원" if price else "-"
        else:
            usd,price,rate,high52,low52,fx = get_us_price(code)
            price_display = f"${usd:,.2f}(≈{price:,}원)" if price else "-"

        invest      = avg*qty
        current_val = price*qty if price else 0
        profit      = current_val-invest
        profit_rate = (price-avg)/avg*100 if avg>0 and price>0 else 0
        total_invest  += invest
        total_current += current_val if price else invest

        signals  = calc_signals(avg,price,code,market,qty,high52,low52,rate)
        rsi      = get_rsi(code,market)
        ma_sig, ma_col = get_ma_cross(code,market)
        foreign, inst  = get_investor_flow(code,market)
        rec_method, rec_color, rec_reason = get_recommend_method(name,market)

        # 포지션 사이징
        turtle_s,_,_,_,_ = get_turtle_signal(code,price) if market in ("KR","ETF_KR") else ("-","#888","-","-","-")
        pos_label, pos_amount = get_position_size(rsi,ma_sig,turtle_s,vix_signal)

        rsi_color = "#e74c3c" if rsi>=70 else "#27ae60" if rsi<=35 else "#333"

        portfolio_rows.append({
            "name":name,"market":market,"qty":qty,"avg":avg,
            "price":price,"price_display":price_display,
            "rate":rate,"profit":profit,"profit_rate":profit_rate,
            "rate_color":"#e74c3c" if rate<0 else "#27ae60",
            "profit_color":"#e74c3c" if profit<0 else "#27ae60",
            "signals":signals,"rsi":rsi,"rsi_color":rsi_color,
            "ma_sig":ma_sig,"ma_col":ma_col,
            "foreign":foreign,"inst":inst,
            "rec_method":rec_method,"rec_color":rec_color,"rec_reason":rec_reason,
            "pos_label":pos_label,"pos_amount":pos_amount,
        })

    print("🎯 스윙 추천 분석 중...")
    swing_picks = get_swing_picks(token)

    total_profit      = total_current-total_invest
    total_profit_rate = total_profit/total_invest*100 if total_invest>0 else 0
    total_color       = "#e74c3c" if total_profit<0 else "#27ae60"
    max_loss          = int(TOTAL_ASSETS*0.02)

    print("🧠 심리 체크리스트 생성 중...")
    psych_checks = get_psychology_checklist(macro,fg_val)

    # ── HTML 조립 ──
    macro_rows = ""
    for name,val in macro.items():
        if name in ("미국10년금리","미국2년금리"): continue
        emoji = "🔴" if val["등락률"]<0 else "🟢"
        color = "#e74c3c" if val["등락률"]<0 else "#27ae60"
        macro_rows += f"<tr><td>{name}</td><td>{val['가격']:,}</td><td style='color:{color}'>{emoji} {val['등락률']:+.2f}%</td></tr>"

    sector_rows = "".join([
        f"<tr><td><b>{s['섹터']}</b></td><td style='color:{'#e74c3c' if s['5일수익률']<0 else '#27ae60'}'>{s['5일수익률']:+.2f}%</td></tr>"
        for s in sectors
    ])

    fg_color = "#e74c3c" if fg_val>=70 else "#27ae60" if fg_val<=30 else "#f39c12"
    fg_bar   = int(fg_val)

    port_rows = ""
    for r in portfolio_rows:
        s = r["signals"]
        port_rows += f"""
        <tr>
          <td><b>{r['name']}</b><br><small style="color:#999">{r['market']}</small></td>
          <td>{r['qty']:,}주</td>
          <td>{r['avg']:,}원</td>
          <td>{r['price_display']}</td>
          <td style="color:{r['rate_color']}">{r['rate']:+.2f}%</td>
          <td style="color:{r['profit_color']}">{r['profit']:+,.0f}원<br>({r['profit_rate']:+.1f}%)</td>
          <td style="color:{r['rsi_color']};font-weight:bold">{r['rsi']}</td>
          <td style="color:{r['ma_col']};font-size:11px">{r['ma_sig']}</td>
          <td style="color:#2980b9;font-size:11px">{r['foreign']}</td>
          <td style="color:#e67e22;font-size:11px">{r['inst']}</td>
          <td style="background:{r['rec_color']}22;color:{r['rec_color']};font-size:11px;font-weight:bold">
            {r['rec_method']}<br><small>{r['rec_reason']}</small>
          </td>
          <td style="color:#2980b9;font-size:11px">{s['추가매수']}</td>
          <td style="color:#e67e22;font-size:11px">{s['방어매도']}</td>
          <td style="color:#8e44ad;font-size:11px">{s['터틀익절']}</td>
          <td style="color:#27ae60;font-size:11px">{s['분할익절']}</td>
          <td style="color:#e74c3c;font-size:11px">{s['atr익절']}</td>
          <td style="font-size:11px">{s['변동성']}</td>
          <td style="font-size:11px">{s['거래량신호']}</td>
          <td style="font-size:11px">{r['pos_label']}<br><b>{r['pos_amount']:,}원</b></td>
        </tr>"""

    swing_rows = ""
    for i,p in enumerate(swing_picks,1):
        swing_rows += f"""
        <tr>
          <td><b>{i}. {p['종목명']}</b></td>
          <td>{p['현재가']:,}원</td>
          <td style="color:#2980b9"><b>{p['추천매수가']:,}원</b></td>
          <td>{p['추천주수']:,}주</td>
          <td>{p['기간']}</td>
          <td style="font-size:11px">{p['근거']}</td>
          <td style="color:{p['MA색상']};font-size:11px">{p['MA신호']}</td>
          <td style="color:{'#e74c3c' if p['RSI']>=70 else '#27ae60' if p['RSI']<=35 else '#333'}">{p['RSI']}</td>
          <td style="color:{p['터틀색상']};font-weight:bold;font-size:11px">{p['터틀신호']}</td>
          <td style="color:#e74c3c;font-size:11px">{p['20캔들고점']}</td>
          <td style="color:#2980b9;font-size:11px">{p['20캔들저점']}</td>
          <td style="color:#27ae60;font-size:11px">{p['추천투자금']}</td>
        </tr>"""

    psych_html = "".join([f"<li style='margin-bottom:6px'>{c}</li>" for c in psych_checks])

    html = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
  body{{font-family:'Malgun Gothic',sans-serif;background:#f5f7fa;color:#333;margin:0;padding:20px}}
  .container{{max-width:1600px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.1)}}
  .header{{background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);color:white;padding:30px;text-align:center}}
  .header h1{{margin:0;font-size:24px;letter-spacing:2px}}
  .header p{{margin:8px 0 0;opacity:0.8;font-size:14px}}
  .section{{padding:20px;border-bottom:1px solid #eee}}
  .section-title{{font-size:15px;font-weight:bold;color:#1a1a2e;margin-bottom:14px;padding-left:10px;border-left:4px solid #0f3460}}
  table{{width:100%;border-collapse:collapse;font-size:11px}}
  th{{background:#1a1a2e;color:white;padding:9px 7px;text-align:center}}
  td{{padding:8px 7px;text-align:center;border-bottom:1px solid #f0f0f0;vertical-align:middle}}
  tr:hover{{background:#f8f9ff}}
  .grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
  .grid-3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:16px}}
  .card{{background:#f8f9ff;border-radius:10px;padding:16px;border:1px solid #e0e4f0}}
  .card .label{{font-size:12px;color:#888;margin-bottom:6px}}
  .card .value{{font-size:18px;font-weight:bold}}
  .summary-box{{display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap}}
  .summary-card{{flex:1;min-width:130px;background:#f8f9ff;border-radius:10px;padding:14px;text-align:center;border:1px solid #e0e4f0}}
  .summary-card .label{{font-size:11px;color:#888;margin-bottom:5px}}
  .summary-card .value{{font-size:16px;font-weight:bold}}
  .fg-bar{{height:20px;border-radius:10px;background:linear-gradient(to right,#e74c3c,#f39c12,#27ae60);position:relative;margin:8px 0}}
  .fg-pointer{{position:absolute;top:-5px;width:4px;height:30px;background:#333;border-radius:2px;transform:translateX(-50%)}}
  .alert-box{{border-radius:8px;padding:12px 16px;margin-bottom:10px;font-size:13px}}
  .legend-box{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}}
  .legend-item{{padding:6px 12px;border-radius:6px;font-size:11px;font-weight:bold}}
  .psych-box{{background:#f0f8ff;border:1px solid #3498db;border-radius:8px;padding:16px}}
  .footer{{background:#f8f9ff;padding:16px;text-align:center;font-size:11px;color:#999}}
</style>
</head>
<body>
<div class="container">

  <!-- 헤더 -->
  <div class="header">
    <h1>📊 포트폴리오 일일 보고서 (풀버전)</h1>
    <p>{today} 기준 | 15개 기법 통합 분석</p>
  </div>

  <!-- 시장 환경 종합 -->
  <div class="section">
    <div class="section-title">🌡️ 오늘의 시장 환경 종합</div>
    <div class="grid-3">
      <div class="card">
        <div class="label">VIX 시장 필터</div>
        <div class="value" style="font-size:13px;color:{vix_color}">{vix_signal}</div>
      </div>
      <div class="card">
        <div class="label">📅 계절성</div>
        <div class="value" style="font-size:13px">{season_title}</div>
        <div style="font-size:11px;color:#888;margin-top:4px">{season_desc}</div>
      </div>
      <div class="card">
        <div class="label">📉 장단기 금리차 (10년-2년)</div>
        <div class="value" style="font-size:13px">{yield_diff:+.3f}%</div>
        <div style="font-size:11px;color:#888;margin-top:4px">{yield_signal}</div>
      </div>
    </div>

    <!-- 공포/탐욕 지수 -->
    <div class="card" style="margin-bottom:16px">
      <div class="label">😱 공포/탐욕 지수 (Fear & Greed Index)</div>
      <div style="display:flex;align-items:center;gap:16px">
        <div class="value" style="color:{fg_color};font-size:28px">{fg_val}</div>
        <div>
          <div style="font-weight:bold;color:{fg_color}">{fg_text}</div>
          <div class="fg-bar" style="width:300px">
            <div class="fg-pointer" style="left:{fg_bar}%"></div>
          </div>
          <div style="display:flex;justify-content:space-between;width:300px;font-size:10px;color:#888">
            <span>극단적공포(0)</span><span>중립(50)</span><span>극단적탐욕(100)</span>
          </div>
        </div>
        <div style="font-size:12px;color:#666">
          {'🟢 역발상 매수 기회 탐색' if fg_val<=25 else '🔴 탐욕 과열 - 매도 준비' if fg_val>=75 else '🟡 중립 - 선별적 매매'}
        </div>
      </div>
    </div>

    <div class="grid-2">
      <!-- 거시경제 -->
      <div>
        <div style="font-weight:bold;margin-bottom:8px;font-size:13px">🌍 글로벌 시장</div>
        <table><tr><th>지표</th><th>가격</th><th>등락률</th></tr>{macro_rows}</table>
      </div>
      <!-- 섹터 로테이션 -->
      <div>
        <div style="font-weight:bold;margin-bottom:8px;font-size:13px">🔄 섹터 로테이션 (5일 수익률)</div>
        <table><tr><th>섹터</th><th>5일수익률</th></tr>{sector_rows}</table>
        <div style="font-size:11px;color:#888;margin-top:6px">
          💡 상위 섹터에 자금 집중 → 해당 섹터 비중 확대 고려
        </div>
      </div>
    </div>
  </div>

  <!-- 포트폴리오 현황 -->
  <div class="section">
    <div class="section-title">💼 내 포트폴리오 현황 (15개 기법 통합)</div>
    <div class="summary-box">
      <div class="summary-card"><div class="label">총 투자금</div><div class="value">{total_invest:,.0f}원</div></div>
      <div class="summary-card"><div class="label">현재 평가금</div><div class="value">{total_current:,.0f}원</div></div>
      <div class="summary-card"><div class="label">평가 손익</div><div class="value" style="color:{total_color}">{total_profit:+,.0f}원</div></div>
      <div class="summary-card"><div class="label">수익률</div><div class="value" style="color:{total_color}">{total_profit_rate:+.2f}%</div></div>
      <div class="summary-card"><div class="label">1회 최대손실(2%)</div><div class="value" style="color:#e74c3c">{max_loss:,}원</div></div>
    </div>

    <div class="legend-box">
      <div class="legend-item" style="background:#8e44ad22;color:#8e44ad">🐢 터틀익절: 대형주</div>
      <div class="legend-item" style="background:#27ae6022;color:#27ae60">📊 분할익절: ETF</div>
      <div class="legend-item" style="background:#e74c3c22;color:#e74c3c">📈 ATR익절: 소형/테마주</div>
      <div class="legend-item" style="background:#2980b922;color:#2980b9">RSI≤35: 과매도(매수기회)</div>
      <div class="legend-item" style="background:#e74c3c22;color:#e74c3c">RSI≥70: 과매수(익절고려)</div>
    </div>

    <div style="overflow-x:auto">
    <table>
      <tr>
        <th>종목명</th><th>수량</th><th>평단가</th><th>현재가</th>
        <th>등락률</th><th>평가손익</th>
        <th>RSI</th><th>MA신호</th>
        <th>외국인</th><th>기관</th>
        <th>⭐추천기법</th>
        <th>추가매수</th><th>방어매도</th>
        <th>🐢터틀익절</th><th>📊분할익절</th><th>📈ATR익절</th>
        <th>변동성</th><th>거래량신호</th><th>포지션사이징</th>
      </tr>
      {port_rows}
    </table>
    </div>
  </div>

  <!-- 스윙 추천 -->
  <div class="section">
    <div class="section-title">🎯 스윙 추천 TOP5 (RSI + MA + 터틀 통합)</div>
    <div style="overflow-x:auto">
    <table>
      <tr>
        <th>종목명</th><th>현재가</th><th>추천매수가</th><th>추천주수</th>
        <th>기간</th><th>근거</th>
        <th>MA신호</th><th>RSI</th>
        <th>터틀신호</th><th>20캔들고점</th><th>20캔들저점</th><th>추천투자금</th>
      </tr>
      {swing_rows}
    </table>
    </div>
  </div>

  <!-- 심리 체크리스트 -->
  <div class="section">
    <div class="section-title">🧠 오늘의 심리 체크리스트</div>
    <div class="psych-box">
      <ul style="margin:0;padding-left:20px;line-height:1.8">
        {psych_html}
      </ul>
    </div>
  </div>

  <div class="footer">
    ⚠️ 본 보고서는 참고용이며 투자 판단의 최종 책임은 본인에게 있습니다.<br>
    적용 기법: 터틀 트레이딩 | 3단계 분할익절 | ATR변동성 | RSI | 골든크로스 | 이동평균선이탈 |
    분할추가매수 | 거래량감지 | VIX필터 | 공포탐욕지수 | 장단기금리차 | 계절성 | 섹터로테이션 | 포지션사이징 | 심리체크
  </div>
</div>
</body>
</html>
"""
    return html

# =====================================================
# 메인 실행
# =====================================================
def main():
    print("="*60)
    print("📊 포트폴리오 일일 보고서 (풀버전) 생성 시작")
    print("="*60)
    token = get_token()
    html  = build_report(token)
    with open("portfolio_report.html","w",encoding="utf-8") as f:
        f.write(html)
    print("✅ 보고서 저장 완료")
    today_str = dt.datetime.now(KST).strftime("%Y/%m/%d")
    send_email(f"📊 [{today_str}] 포트폴리오 일일 보고서 (풀버전)", html)
    print("="*60)
    print("✅ 완료!")

if __name__ == "__main__":
    main()

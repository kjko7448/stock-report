# portfolio_report.py - 풀버전 (투자 원칙서 기반)
# Google Sheets + Claude AI + FRED + 탑다운 + 주도주 + 시장신호등 + 매수체크리스트
# pip install requests pandas yfinance

import requests
import pandas as pd
import yfinance as yf
import json
import os
import datetime as dt
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import warnings
warnings.filterwarnings("ignore")

KST = dt.timezone(dt.timedelta(hours=9))

APP_KEY            = os.environ.get("APP_KEY", "")
APP_SECRET         = os.environ.get("APP_SECRET", "")
GMAIL_ADDRESS      = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
RECEIVE_ADDRESS    = os.environ.get("RECEIVE_ADDRESS", "")
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
FRED_API_KEY       = os.environ.get("FRED_API_KEY", "")
TOKEN_FILE         = "token.json"
TOTAL_ASSETS       = 24_000_000
CASH_LIMIT         = 6_000_000   # 절대 사수 현금
MONTHLY_LIMIT_PCT  = 0.20        # 월 매수 한도 (현금의 20%)
SHEET_ID           = "1-7TeKv9OucJYMvXN55yQ5w0Rg0Fwi8QQH44jmUfzElg"

NARRATIVE_MAP = {
    "NVDA": ["SK하이닉스","이수페타시스","한미반도체","리노공업"],
    "GEV":  ["LS ELECTRIC","일진전기","효성중공업","제룡전기","HD현대일렉트릭"],
    "MSFT": ["NAVER","카카오","솔트룩스"],
    "PLTR": ["솔트룩스","셀바스AI"],
    "LMT":  ["한화에어로스페이스","LIG넥스원","한국항공우주"],
    "TSLA": ["에코프로비엠","포스코퓨처엠","삼성SDI"],
}

SECTORS = {
    "AI/반도체":         {"type":"조류","us_etf":"SMH","stocks":[("005930","삼성전자"),("000660","SK하이닉스"),("042700","한미반도체"),("007660","이수페타시스"),("058470","리노공업")]},
    "전력/전기인프라":   {"type":"조류","us_etf":"GRID","stocks":[("010120","LS ELECTRIC"),("103590","일진전기"),("267270","HD현대일렉트릭"),("094870","효성중공업"),("033100","제룡전기")]},
    "로봇/자동화":       {"type":"조류","us_etf":"BOTZ","stocks":[("454910","두산로보틱스"),("277810","레인보우로보틱스"),("064350","현대로템"),("031860","에스피지")]},
    "방산/우주":         {"type":"조류","us_etf":"ITA","stocks":[("012450","한화에어로스페이스"),("079550","LIG넥스원"),("047810","한국항공우주"),("065650","빅텍")]},
    "바이오/헬스케어":   {"type":"조류","us_etf":"XLV","stocks":[("207940","삼성바이오로직스"),("068270","셀트리온"),("000100","유한양행"),("128940","한미약품"),("185750","종근당")]},
    "AI소프트웨어":      {"type":"조류","us_etf":"IGV","stocks":[("035420","NAVER"),("035720","카카오"),("304100","솔트룩스"),("208370","셀바스AI")]},
    "원전/신재생에너지": {"type":"조류","us_etf":"URNM","stocks":[("034020","두산에너빌리티"),("130660","한전기술"),("112610","씨에스윈드"),("099220","비에이치아이")]},
    "사이버보안":        {"type":"조류","us_etf":"HACK","stocks":[("053800","안랩"),("067920","이글루시큐리티"),("263800","드림시큐리티"),("411080","지니언스"),("411790","샌즈랩")]},
    "2차전지소재":       {"type":"조류","us_etf":"LIT","stocks":[("247540","에코프로비엠"),("003670","포스코퓨처엠"),("066970","엘앤에프"),("278280","천보")]},
    "게임/콘텐츠":       {"type":"조류","us_etf":"HERO","stocks":[("259960","크래프톤"),("251270","넷마블"),("036570","엔씨소프트"),("352820","하이브")]},
    "조선/해운":         {"type":"파도","us_etf":"BOAT","stocks":[("329180","HD현대중공업"),("042660","한화오션"),("010140","삼성중공업"),("011200","HMM")]},
    "소재/화학":         {"type":"파도","us_etf":"XLB","stocks":[("005490","POSCO홀딩스"),("051910","LG화학"),("011170","롯데케미칼"),("011780","금호석유")]},
    "금융/보험/증권":    {"type":"파도","us_etf":"XLF","stocks":[("105560","KB금융"),("055550","신한지주"),("086790","하나금융"),("006800","미래에셋증권")]},
    "자동차/부품":       {"type":"파도","us_etf":"CARZ","stocks":[("005380","현대차"),("000270","기아"),("012330","현대모비스"),("204320","만도")]},
    "철강/금속":         {"type":"파도","us_etf":"XME","stocks":[("004020","현대제철"),("010130","고려아연"),("103140","풍산")]},
    "에너지/정유":       {"type":"파도","us_etf":"XLE","stocks":[("096770","SK이노베이션"),("010950","S-Oil"),("078930","GS")]},
    "건설/부동산":       {"type":"파도","us_etf":"XHB","stocks":[("000720","현대건설"),("006360","GS건설"),("047040","대우건설")]},
    "디스플레이/가전":   {"type":"파도","us_etf":"XLY","stocks":[("066570","LG전자"),("034220","LG디스플레이"),("009150","삼성전기")]},
    "물류/운송/항공":    {"type":"파도","us_etf":"IYT","stocks":[("000120","CJ대한통운"),("086280","현대글로비스"),("003490","대한항공")]},
    "필수소비재/식품":   {"type":"방어","us_etf":"XLP","stocks":[("097950","CJ제일제당"),("271560","오리온"),("004370","농심"),("000080","하이트진로")]},
    "통신":              {"type":"방어","us_etf":"XLC","stocks":[("017670","SK텔레콤"),("030200","KT"),("032640","LG유플러스")]},
    "유틸리티/인프라":   {"type":"방어","us_etf":"XLU","stocks":[("015760","한국전력"),("036460","한국가스공사")]},
    "유통/리테일":       {"type":"방어","us_etf":"XRT","stocks":[("139480","이마트"),("027410","BGF리테일"),("004170","신세계")]},
}

# =====================================================
# Google Sheets
# =====================================================
def load_holdings_from_sheets():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
    try:
        print("📊 구글 시트에서 포트폴리오 읽는 중...")
        df = pd.read_csv(url, dtype=str)
        df.columns = df.columns.str.strip()
        holdings = []
        for _, row in df.iterrows():
            try:
                code   = str(row["종목코드"]).strip()
                name   = str(row["종목명"]).strip()
                qty    = int(str(row["수량"]).replace(",","").strip())
                avg    = int(str(row["평단가"]).replace(",","").strip())
                market = str(row["시장"]).strip()
                if code and name and qty>0 and avg>0:
                    holdings.append((code,name,qty,avg,market))
            except: continue
        print(f"✅ {len(holdings)}개 종목 로드 완료")
        return holdings
    except Exception as e:
        print(f"⚠️ 구글 시트 읽기 실패: {e}")
        return get_default_holdings()

def get_default_holdings():
    return [
        ("005490","POSCO홀딩스",10,424550,"KR"),
        ("005930","삼성전자",4,60100,"KR"),
        ("005935","삼성전자우",5,187520,"KR"),
        ("007660","이수페타시스",5,133960,"KR"),
        ("010780","아이에스동서",1,38450,"KR"),
        ("094360","챔스미디어",9,27361,"KR"),
        ("247540","에코프로비엠",8,235750,"KR"),
        ("304100","솔트룩스",3,29383,"KR"),
        ("010120","LS ELECTRIC",6,253417,"KR"),
        ("103590","일진전기",10,92400,"KR"),
        ("035420","NAVER",10,252000,"KR"),
        ("329180","HD현대중공업",2,647000,"KR"),
        ("QQQ","Invesco QQQ",1,907209,"US"),
        ("SPYG","SPDR S&P500 Growth",7,157479,"US"),
        ("SCHD","Schwab Dividend",26,40186,"US"),
        ("VOO","Vanguard S&P500",2,907785,"US"),
        ("BOTT","THEMES HUMANOID ROBOTICS ETF",3,82969,"US"),
        ("360750","TIGER 미국S&P500",55,24635,"ETF_KR"),
        ("426030","TIME 나스닥100",30,35102,"ETF_KR"),
        ("458730","TIGER 미국배당다운존스",56,14074,"ETF_KR"),
        ("364970","TIGER 바이오TOP10",10,7520,"ETF_KR"),
        ("465580","RISE 미국AI밸류체인",47,17987,"ETF_KR"),
        ("464310","TIGER 글로벌AI&로보틱스INDXX",10,17165,"ETF_KR"),
        ("441680","TIGER 나스닥100커버드콜",111,10719,"ETF_KR"),
        ("0167A0","SOL AI반도체TOP2플러스",5,21215,"ETF_KR"),
        ("395160","KODEX AI반도체TOP2플러스",3,45856,"ETF_KR"),
        ("445290","KODEX 로봇액티브",20,48250,"ETF_KR"),
        ("487240","KODEX AI전력핵심설비",20,50775,"ETF_KR"),
    ]

# =====================================================
# FRED 유동성
# =====================================================
def get_fred_data(series_id, limit=2):
    try:
        res = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={"series_id":series_id,"api_key":FRED_API_KEY,
                    "file_type":"json","sort_order":"desc","limit":limit},
            timeout=10)
        obs = res.json().get("observations",[])
        if len(obs)>=1:
            latest = float(obs[0]["value"]) if obs[0]["value"]!="." else 0
            prev   = float(obs[1]["value"]) if len(obs)>=2 and obs[1]["value"]!="." else latest
            return latest, latest-prev, obs[0]["date"]
        return 0,0,"-"
    except: return 0,0,"-"

def get_liquidity_data():
    print("💧 FRED 유동성 지표 수집 중...")
    indicators = {
        "역레포(RRP)":      ("RRPONTSYD","$B","감소=유동성 공급"),
        "TGA 잔액":         ("WTREGEN","$B","감소=유동성 공급"),
        "연준 총자산":      ("WALCL","$B","감소=QT 진행"),
        "지급준비금":       ("WRESBAL","$B","3조↑=안정"),
        "하이일드 스프레드":("BAMLH0A0HYM2","%","8↑=위기"),
        "금융스트레스지수": ("STLFSI4","","0↑=스트레스"),
        "M2 통화량":        ("M2SL","$B","증가=유동성↑"),
        "장단기 금리차":    ("T10Y2Y","%","음수=침체경고"),
    }
    result = {}
    for name,(series_id,unit,desc) in indicators.items():
        val,change,date = get_fred_data(series_id)
        result[name] = {"값":round(val,2),"변화":round(change,2),"날짜":date,"단위":unit,"설명":desc}
    return result

def get_liquidity_score(liquidity):
    score = 50; signals = []
    rrp = liquidity.get("역레포(RRP)",{})
    if rrp.get("변화",0)<-10:  score+=10; signals.append("✅ 역레포 감소")
    elif rrp.get("변화",0)>10: score-=10; signals.append("⚠️ 역레포 증가")
    tga = liquidity.get("TGA 잔액",{})
    if tga.get("변화",0)<-20:  score+=10; signals.append("✅ TGA 감소")
    elif tga.get("변화",0)>20: score-=10; signals.append("⚠️ TGA 증가")
    hy = liquidity.get("하이일드 스프레드",{})
    if hy.get("값",5)<4:   score+=10; signals.append("✅ 하이일드 정상")
    elif hy.get("값",5)>6: score-=15; signals.append("🔴 하이일드 확대")
    fsi = liquidity.get("금융스트레스지수",{})
    if fsi.get("값",0)<0:   score+=10; signals.append("✅ 금융스트레스 낮음")
    elif fsi.get("값",0)>1: score-=15; signals.append("🔴 금융스트레스 높음")
    spread = liquidity.get("장단기 금리차",{})
    if spread.get("값",0)>0.5:    score+=10; signals.append("✅ 금리차 정상")
    elif spread.get("값",0)<-0.5: score-=10; signals.append("⚠️ 금리차 역전")
    score = max(0,min(100,score))
    if score>=70:   phase,color = "🟢 유동성 확장","#27ae60"
    elif score>=50: phase,color = "🟡 유동성 중립","#f39c12"
    else:           phase,color = "🔴 유동성 수축","#e74c3c"
    return score,phase,color,signals

# =====================================================
# ★ 시장 신호등 (핵심 추가!)
# =====================================================
def get_market_signal(macro, liq_score):
    """
    시장 신호등 판단
    🟢 불장: 추세추종 적극 매수
    🟡 횡보: 선별적 매수
    🔴 하락: 현금 보유
    """
    vix = macro.get("VIX",{}).get("가격",20)
    nq_rate = macro.get("나스닥",{}).get("등락률",0)

    # 코스피 이동평균 확인
    try:
        kospi = yf.Ticker("^KS11").history(period="6mo").dropna()
        curr  = kospi["Close"].iloc[-1]
        ma20  = kospi["Close"].rolling(20).mean().iloc[-1]
        ma60  = kospi["Close"].rolling(60).mean().iloc[-1]
        ma_bull = curr > ma20 > ma60
        ma_bear = curr < ma20 < ma60
    except:
        ma_bull = ma_bear = False

    # 점수 계산
    bull_score = 0
    bear_score = 0

    if vix < 20:      bull_score += 1
    elif vix >= 30:   bear_score += 1

    if liq_score >= 60: bull_score += 1
    elif liq_score < 40: bear_score += 1

    if ma_bull: bull_score += 1
    elif ma_bear: bear_score += 1

    if nq_rate > 0: bull_score += 1
    elif nq_rate < -1: bear_score += 1

    # 신호등 결정
    if vix >= 40:
        return "🟢 VIX 극단공포 → 역발상 매수!", "#27ae60", "불장", "역발상", vix
    elif bear_score >= 3:
        return "🔴 하락장 → 현금 보유!", "#e74c3c", "하락장", "하락", vix
    elif bear_score >= 2:
        return "🟠 조심스러운 하락 → 매수 자제", "#e67e22", "하락장", "주의", vix
    elif bull_score >= 3:
        return "🟢 강한 불장 → 추세추종 적극 매수!", "#27ae60", "불장", "불장", vix
    elif bull_score >= 2:
        return "🟢 불장 → 주도주 65점↑ 매수", "#27ae60", "불장", "불장", vix
    else:
        return "🟡 횡보장 → 선별적 매수만", "#f39c12", "횡보장", "횡보", vix

# =====================================================
# ★ 매수 체크리스트 (핵심 추가!)
# =====================================================
def get_buy_checklist(market_type, liq_score, vix, leader_score, cycle_pct, rsi, cash):
    """
    매수 전 9가지 체크리스트 자동 확인
    """
    monthly_limit = cash * MONTHLY_LIMIT_PCT
    safe_cash     = cash - CASH_LIMIT

    checks = [
        ("시장 신호등 🟢 불장", market_type == "불장" or market_type == "역발상"),
        ("주도주 점수 65점 이상", leader_score >= 65),
        ("FRED 유동성 50점 이상", liq_score >= 50),
        ("사이클 위치 60% 이하", cycle_pct <= 60),
        ("RSI 70 미만 (과열 아님)", rsi < 70),
        ("현금 600만원 사수 가능", safe_cash >= 0),
        ("이번달 한도 남아있음", monthly_limit > 0),
        ("한 종목 20% 한도 이내", True),
        ("FOMO 아닌 근거 있는 매수", leader_score >= 65),
    ]

    passed = sum(1 for _, v in checks)
    ok     = all(v for _, v in checks)

    return checks, ok, monthly_limit

# =====================================================
# 기본 함수들
# =====================================================
def get_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE,"r") as f: data=json.load(f)
        if data.get("issued_at")==dt.datetime.now(KST).strftime("%Y-%m-%d"):
            return data["access_token"]
    url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    res = requests.post(url,headers={"content-type":"application/json"},
        data=json.dumps({"grant_type":"client_credentials","appkey":APP_KEY,"appsecret":APP_SECRET}),
        timeout=10)
    token_data=res.json()
    token_data["issued_at"]=dt.datetime.now(KST).strftime("%Y-%m-%d")
    with open(TOKEN_FILE,"w") as f: json.dump(token_data,f)
    return token_data["access_token"]

def get_kr_price(token, code):
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {"content-type":"application/json","authorization":f"Bearer {token}",
               "appkey":APP_KEY,"appsecret":APP_SECRET,"tr_id":"FHKST01010100"}
    try:
        res=requests.get(url,headers=headers,
            params={"FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":code},timeout=10)
        output=res.json().get("output",{})
        return (int(output.get("stck_prpr",0)),float(output.get("prdy_ctrt",0)),
                int(output.get("acml_vol",0)),int(output.get("w52_hgpr",0)),int(output.get("w52_lwpr",0)))
    except: return 0,0,0,0,0

def get_us_price(ticker):
    try:
        t=yf.Ticker(ticker); info=t.info
        usd=info.get("currentPrice") or info.get("regularMarketPrice",0)
        fx=yf.Ticker("USDKRW=X").info.get("regularMarketPrice",1380)
        return usd,int(usd*fx),info.get("regularMarketChangePercent",0),\
               info.get("fiftyTwoWeekHigh",0),info.get("fiftyTwoWeekLow",0),fx
    except: return 0,0,0,0,0,1380

def get_macro():
    tickers={"S&P500":"^GSPC","나스닥":"^IXIC","다우":"^DJI","VIX":"^VIX",
             "달러인덱스":"DX-Y.NYB","원달러환율":"USDKRW=X","WTI유가":"CL=F","금":"GC=F"}
    result={}
    for name,sym in tickers.items():
        try:
            hist=yf.Ticker(sym).history(period="2d").dropna()
            if len(hist)>=2:
                prev=hist["Close"].iloc[-2]; today=hist["Close"].iloc[-1]
                result[name]={"가격":round(today,2),"등락률":round((today-prev)/prev*100,2)}
            else: result[name]={"가격":0,"등락률":0}
        except: result[name]={"가격":0,"등락률":0}
    return result

def get_rsi(code, market, period=14):
    try:
        ticker=code+".KS" if market in ("KR","ETF_KR") else code
        hist=yf.Ticker(ticker).history(period="2mo").dropna()
        if len(hist)<period+1: return 50
        delta=hist["Close"].diff()
        gain=delta.where(delta>0,0).rolling(period).mean()
        loss=(-delta.where(delta<0,0)).rolling(period).mean()
        rs=gain/loss
        return round((100-(100/(1+rs))).iloc[-1],1)
    except: return 50

def get_ma_cross(code, market):
    try:
        ticker=code+".KS" if market in ("KR","ETF_KR") else code
        hist=yf.Ticker(ticker).history(period="4mo").dropna()
        if len(hist)<60: return "-","#888"
        ma20=hist["Close"].rolling(20).mean().iloc[-1]
        ma60=hist["Close"].rolling(60).mean().iloc[-1]
        curr=hist["Close"].iloc[-1]
        if ma20>ma60 and curr>ma20:   return "🟢 골든크로스","#27ae60"
        elif ma20<ma60 and curr<ma20: return "🔴 데드크로스","#e74c3c"
        elif curr>ma20>ma60:          return "🟢 상승추세","#27ae60"
        elif curr<ma20:               return "🟡 20일선하회","#f39c12"
        return "🟡 횡보","#888"
    except: return "-","#888"

def get_atr(code, market, period=14):
    try:
        ticker=code+".KS" if market in ("KR","ETF_KR") else code
        hist=yf.Ticker(ticker).history(period="1mo").dropna()
        if len(hist)<period: return 0,"중간"
        hist["TR"]=hist.apply(lambda r: max(r["High"]-r["Low"],
            abs(r["High"]-hist["Close"].shift(1).get(r.name,r["Close"])),
            abs(r["Low"]-hist["Close"].shift(1).get(r.name,r["Close"]))),axis=1)
        atr_pct=hist["TR"].tail(period).mean()/hist["Close"].iloc[-1]*100
        vol="높음" if atr_pct>=4 else "낮음" if atr_pct<2 else "중간"
        return round(atr_pct,2),vol
    except: return 0,"중간"

def get_seasonality():
    month=dt.datetime.now(KST).month
    m={1:"🟢 1월효과",2:"🟡 2월조정",3:"🟢 3월반등",4:"🟡 4월주의",
       5:"🔴 5월경고",6:"🟡 6월보합",7:"🟢 7월반등",8:"🟡 8월변동",
       9:"🔴 9월경고",10:"🟢 10월기회",11:"🟢 11월강세",12:"🟢 12월랠리"}
    return m.get(month,"🟡 보통")

# =====================================================
# ★ 주도주 스코어링
# =====================================================
def get_leader_score(code, name, price, rate, volume, high52, low52, sector_name):
    score=0; details=[]
    try:
        ticker=code+".KS"
        hist=yf.Ticker(ticker).history(period="3mo").dropna()
        if len(hist)<20: return 0,[],"-","➖",50,0,0
        curr=hist["Close"].iloc[-1]
        kospi=yf.Ticker("^KS11").history(period="3mo").dropna()

        # ① 신고가 근접도
        if high52>low52: cycle=round((curr-low52)/(high52-low52)*100,1)
        else: cycle=50
        if cycle>=80:   score+=20; details.append(f"신고가근처({cycle}%)")
        elif cycle>=60: score+=15; details.append(f"상승중({cycle}%)")
        elif cycle>=30: score+=8;  details.append(f"중간({cycle}%)")
        else:           score+=5;  details.append(f"저점({cycle}%)")

        # ② 코스피 대비 아웃퍼폼
        outperform=0
        if len(hist)>=20 and len(kospi)>=20:
            s20=(hist["Close"].iloc[-1]-hist["Close"].iloc[-20])/hist["Close"].iloc[-20]*100
            k20=(kospi["Close"].iloc[-1]-kospi["Close"].iloc[-20])/kospi["Close"].iloc[-20]*100
            outperform=round(s20-k20,1)
            if outperform>=10:  score+=15; details.append(f"강한아웃퍼폼(+{outperform}%)")
            elif outperform>=5: score+=10; details.append(f"아웃퍼폼(+{outperform}%)")
            elif outperform>=0: score+=5
            else:               score-=5;  details.append(f"언더퍼폼({outperform}%)")

        # ③ 모멘텀 가속도
        if len(hist)>=20:
            r1w=(hist["Close"].iloc[-1]-hist["Close"].iloc[-5])/hist["Close"].iloc[-5]*100
            r1m=(hist["Close"].iloc[-1]-hist["Close"].iloc[-20])/hist["Close"].iloc[-20]*100
            if r1w>r1m/4: score+=10; details.append("모멘텀가속")
            elif r1w>0:   score+=5

        # ④ 거래량
        if len(hist)>=20:
            avg_vol=hist["Volume"].tail(20).mean()
            vol_r=volume/avg_vol if avg_vol>0 else 1
            if vol_r>=2:   score+=15; details.append(f"거래량폭발({vol_r:.1f}배)")
            elif vol_r>=1.5: score+=10; details.append(f"거래량급증")
            elif vol_r>=1: score+=5

        # ⑤ 글로벌 트렌드
        us_etf=SECTORS.get(sector_name,{}).get("us_etf","")
        if us_etf:
            try:
                uh=yf.Ticker(us_etf).history(period="7d").dropna()
                if len(uh)>=2:
                    ur=(uh["Close"].iloc[-1]-uh["Close"].iloc[0])/uh["Close"].iloc[0]*100
                    if ur>=3:   score+=15; details.append(f"글로벌강세(+{ur:.1f}%)")
                    elif ur>=1: score+=10
                    elif ur>=0: score+=5
                    else:       score-=5; details.append(f"글로벌약세")
            except: pass

        # ⑥ 내러티브 확장성
        for us_t, kr_stocks in NARRATIVE_MAP.items():
            if name in kr_stocks:
                try:
                    uh=yf.Ticker(us_t).history(period="7d").dropna()
                    if len(uh)>=2:
                        ur=(uh["Close"].iloc[-1]-uh["Close"].iloc[0])/uh["Close"].iloc[0]*100
                        if ur>=3:   score+=10; details.append(f"{us_t}연동강세")
                        elif ur>=0: score+=5
                except: pass
                break

        # 사이클 위치
        if cycle<=30:   entry="🟢 초기(강력매수)"
        elif cycle<=60: entry="🟡 중기(분할매수)"
        elif cycle<=80: entry="🟠 후기(소량진입)"
        else:           entry="🔴 고점주의(신중)"

        score=max(0,min(100,score))
        if score>=80:   grade="🔥🔥 슈퍼주도주"
        elif score>=65: grade="🔥 강력주도주"
        elif score>=50: grade="⭐ 주도주후보"
        else:           grade="➖ 일반종목"

        return score,details,entry,grade,cycle,outperform,volume

    except: return 0,[],"-","➖",50,0,0

# =====================================================
# ★ 고점/진입 분석 + 타입별 매수가
# =====================================================
def get_entry_analysis(code, price, high52, low52, rsi):
    try:
        hist=yf.Ticker(code+".KS").history(period="2mo").dropna()
        if len(hist)<20 or price==0: return "-","-",price,"A타입(눌림형)",0,price

        ma20=hist["Close"].rolling(20).mean().iloc[-1]
        std20=hist["Close"].rolling(20).std().iloc[-1]
        bb_upper=ma20+2*std20; bb_lower=ma20-2*std20
        bb_width=(bb_upper-bb_lower)/ma20*100

        recent=hist.tail(20)
        pullback=((recent["High"]-recent["Low"])/recent["High"]*100).mean()
        near_high=(price-high52)/high52*100 if high52>0 else -10
        avg_vol=hist["Volume"].tail(20).mean()
        now_vol=hist["Volume"].iloc[-1]
        vol_surge=now_vol/avg_vol if avg_vol>0 else 1
        ret_5d=(hist["Close"].iloc[-1]-hist["Close"].iloc[-5])/hist["Close"].iloc[-5]*100 if len(hist)>=5 else 0

        b_score=a_score=c_score=0
        if pullback<1.5:    b_score+=3
        elif pullback<3.0:  a_score+=3
        else:               c_score+=3
        if near_high>=-3:   b_score+=3
        elif near_high>=-10:a_score+=2
        else:               c_score+=2
        if vol_surge>=2:    b_score+=2
        elif vol_surge>=1.2:a_score+=1
        else:               c_score+=1
        if bb_width<5:      c_score+=3
        elif bb_width<10:   a_score+=2
        else:               b_score+=1
        if ret_5d>=3:       b_score+=2
        elif ret_5d>=0:     a_score+=1
        else:               c_score+=1

        scores={"B":b_score,"A":a_score,"C":c_score}
        best=max(scores,key=scores.get)

        if best=="B":
            rec_buy=int(price*0.995); stock_type="🚀 B타입(돌파형)"; buy_reason=f"즉시매수 {rec_buy:,}원"
        elif best=="A":
            rec_buy=int(ma20*0.99); stock_type="📉 A타입(눌림형)"; buy_reason=f"MA20기준 {rec_buy:,}원"
            if price<ma20: rec_buy=int(bb_lower*0.99); buy_reason=f"BB하단 {rec_buy:,}원"
        else:
            rec_buy=int(bb_lower); stock_type="📦 C타입(횡보형)"; buy_reason=f"BB하단 {rec_buy:,}원"
            if rec_buy<price*0.90: rec_buy=int(ma20*0.98); buy_reason=f"MA20 {rec_buy:,}원"

        if rec_buy>price: rec_buy=int(price*0.995)

        # ★ ATR 손절가 계산
        atr_val=hist["High"].tail(14).mean()-hist["Low"].tail(14).min()
        atr_stop=int(price-atr_val*2)

        overheat=0
        if rsi>=70: overheat+=1
        if price>bb_upper: overheat+=1
        if price>ma20*1.15: overheat+=1
        if overheat>=2: heat="🔴 과열 → 눌림 대기"
        elif overheat==1: heat="🟠 약과열 → 신중"
        else: heat="🟢 정상 → 진입 가능"

        atr_target=int(price+atr_val*3)
        upside=round((atr_target-price)/price*100,1)

        return heat, f"목표 {atr_target:,}원(+{upside}%) | {stock_type} | {buy_reason}", rec_buy, stock_type, atr_stop, atr_val

    except: return "-","-",price,"A타입(눌림형)",int(price*0.90),0

# =====================================================
# 섹터 건강도
# =====================================================
def get_sector_health(liquidity_score):
    print("📊 섹터 건강도 분석 중...")
    results=[]
    for sector_name,sector_info in SECTORS.items():
        us_etf=sector_info.get("us_etf",""); rate_5d=0
        try:
            if us_etf:
                hist=yf.Ticker(us_etf).history(period="7d").dropna()
                if len(hist)>=2:
                    rate_5d=round((hist["Close"].iloc[-1]-hist["Close"].iloc[0])/hist["Close"].iloc[0]*100,2)
        except: pass
        stype=sector_info["type"]
        if liquidity_score>=70:
            if stype=="조류":   fit_score=90; fit="⭐ 최우선"
            elif stype=="파도": fit_score=60; fit="✅ 보통"
            else:               fit_score=30; fit="⚠️ 비추"
        elif liquidity_score>=50:
            if stype=="조류":   fit_score=70; fit="✅ 우선"
            elif stype=="방어": fit_score=60; fit="✅ 보통"
            else:               fit_score=40; fit="⚠️ 주의"
        else:
            if stype=="방어":   fit_score=90; fit="⭐ 최우선"
            elif stype=="조류": fit_score=40; fit="⚠️ 주의"
            else:               fit_score=20; fit="❌ 비추"

        # ETF 약세면 조류여도 패널티
        etf_bonus=min(40,max(-40,rate_5d*4))
        if rate_5d<-2 and stype=="조류": fit_score-=20
        total=fit_score+etf_bonus

        results.append({"섹터":sector_name,"타입":stype,"us_etf":us_etf,
                        "5일수익률":rate_5d,"적합도":fit,"종합점수":round(total,1)})
    return sorted(results,key=lambda x:x["종합점수"],reverse=True)

def get_recommended_sectors(liquidity_score):
    if liquidity_score>=70:
        priority=[n for n,s in SECTORS.items() if s["type"]=="조류"]
        extra=[n for n,s in SECTORS.items() if s["type"]=="파도" and n in ["조선/해운","자동차/부품","금융/보험/증권"]]
        phase="🟢 성장주 우위"
    elif liquidity_score>=50:
        priority=[n for n,s in SECTORS.items() if s["type"]=="조류" and n in ["AI/반도체","전력/전기인프라","바이오/헬스케어","방산/우주"]]
        extra=[n for n,s in SECTORS.items() if s["type"]=="방어"]
        phase="🟡 중립"
    else:
        priority=[n for n,s in SECTORS.items() if s["type"]=="방어"]
        extra=[n for n,s in SECTORS.items() if s["type"]=="조류" and n in ["바이오/헬스케어","AI/반도체"]]
        phase="🔴 방어주 우위"
    return priority+extra, phase

# =====================================================
# 탑다운 + 주도주 스크리너
# =====================================================
def run_topdown_screener(token, liquidity_score, sector_health, market_type):
    print(f"\n🔍 탑다운 + 주도주 스크리너 실행")
    rec_sectors,phase_msg=get_recommended_sectors(liquidity_score)
    top_sectors=[s["섹터"] for s in sector_health[:8]]
    target=[s for s in rec_sectors if s in top_sectors][:6]

    kr_picks=[]
    for sector_name in target:
        if sector_name not in SECTORS: continue
        sector_info=SECTORS[sector_name]
        print(f"  → {sector_name} 스크리닝 중...")
        sector_results=[]

        for code,name in sector_info["stocks"][:3]:
            price,rate,volume,high52,low52=get_kr_price(token,code)
            if price==0: continue
            rsi=get_rsi(code,"KR")
            ma_sig,ma_col=get_ma_cross(code,"KR")
            leader_score,leader_details,entry_timing,grade,cycle_pct,outperform,vol=\
                get_leader_score(code,name,price,rate,volume,high52,low52,sector_name)
            heat_msg,upside_msg,rec_buy,stock_type,atr_stop,atr_val=\
                get_entry_analysis(code,price,high52,low52,rsi)

            # 시장별 전략 반영
            if market_type=="하락장" and leader_score<80: continue
            if market_type=="횡보" and leader_score<70: continue

            # 매수 판단
            if leader_score>=80:
                buy_action="🔥🔥 적극매수"; buy_color="#e74c3c"; invest_pct=1.0
            elif leader_score>=65:
                buy_action="🔥 분할매수"; buy_color="#e67e22"; invest_pct=0.3
            else:
                buy_action="👀 관망"; buy_color="#888"; invest_pct=0.0

            max_loss=TOTAL_ASSETS*0.02
            try:
                hist=yf.Ticker(code+".KS").history(period="2mo").dropna()
                low20=int(hist["Low"].tail(20).min()) if len(hist)>=20 else int(price*0.95)
                loss_pct=(price-low20)/price*100 if price>low20 else 2
                rec_invest=int(max_loss/(loss_pct/100)*invest_pct) if loss_pct>0 else 0
            except: rec_invest=0

            sector_results.append({
                "섹터":sector_name,"섹터타입":sector_info["type"],
                "종목명":name,"현재가":price,"추천매수가":rec_buy,
                "종목타입":stock_type,"등락률":rate,"RSI":rsi,
                "MA신호":ma_sig,"MA색상":ma_col,
                "주도주점수":leader_score,"주도주등급":grade,
                "사이클위치":cycle_pct,"진입타이밍":entry_timing,
                "과열도":heat_msg,"업사이드":upside_msg,
                "ATR손절가":atr_stop,"ATR":round(atr_val),
                "매수판단":buy_action,"매수색상":buy_color,
                "추천투자금":rec_invest,
                "근거":", ".join(leader_details[:3]) if leader_details else "기본분석",
            })

        sector_results.sort(key=lambda x:x["주도주점수"],reverse=True)
        if sector_results: kr_picks.append(sector_results[0])

    kr_picks.sort(key=lambda x:x["주도주점수"],reverse=True)

    # 미국 ETF TOP2
    us_picks=[]
    for s in sector_health:
        if s["us_etf"] and s["us_etf"]!="-" and s["타입"]=="조류":
            try:
                hist=yf.Ticker(s["us_etf"]).history(period="2mo").dropna()
                if len(hist)<20: continue
                curr=hist["Close"].iloc[-1]
                high52=hist["High"].max(); low52=hist["Low"].min()
                rsi_val=get_rsi(s["us_etf"],"US")
                cycle=round((curr-low52)/(high52-low52)*100,1) if high52>low52 else 50
                ma20=hist["Close"].rolling(20).mean().iloc[-1]
                std20=hist["Close"].rolling(20).std().iloc[-1]
                bb_upper=ma20+2*std20
                atr_v=hist["High"].tail(14).mean()-hist["Low"].tail(14).min()
                atr_stop_us=round(curr-atr_v*2,2)
                overheat=rsi_val>=70 or curr>bb_upper
                heat="🟠 약과열" if overheat else "🟢 정상"
                rec_buy_etf=round(curr*0.98 if overheat else curr*0.995,2)
                target_p=round(curr+atr_v*3,2)
                upside=round((target_p-curr)/curr*100,1)
                us_picks.append({
                    "섹터":s["섹터"],"ETF코드":s["us_etf"],
                    "현재가":f"${curr:.2f}","추천매수가":f"${rec_buy_etf:.2f}",
                    "ATR손절가":f"${atr_stop_us:.2f}",
                    "5일수익률":s["5일수익률"],"RSI":rsi_val,
                    "사이클":f"{cycle}%","과열도":heat,
                    "업사이드":f"+{upside}%","종합점수":s["종합점수"],
                })
            except: pass
        if len(us_picks)>=2: break

    return kr_picks[:5],us_picks[:2],rec_sectors,phase_msg

# =====================================================
# 포트폴리오 매매 신호
# =====================================================
def calc_signals(avg, current, code, market, qty, high52, low52, current_rate):
    if current==0 or avg==0:
        return {k:"-" for k in ["추가매수","방어매도","터틀익절","분할익절","atr익절","atr손절","변동성"]}
    profit_rate=(current-avg)/avg*100
    try:
        ticker=code+".KS" if market in ("KR","ETF_KR") else code
        hist=yf.Ticker(ticker).history(period="2mo").dropna()
        avg_vol=hist["Volume"].tail(20).mean()
        now_vol=hist["Volume"].iloc[-1]
        vol_bad=current_rate<-2 and now_vol>avg_vol*1.5
        ma20=hist["Close"].rolling(20).mean().iloc[-1]
        std20=hist["Close"].rolling(20).std().iloc[-1]
        bb_lower=ma20-2*std20
        recent=hist.tail(20)
        pullback=((recent["High"]-recent["Low"])/recent["High"]*100).mean()
        # ATR 손절가
        atr_v=hist["High"].tail(14).mean()-hist["Low"].tail(14).min()
        atr_stop=int(current-atr_v*2)
    except:
        vol_bad=False; ma20=current; bb_lower=current*0.95; pullback=2.0; atr_stop=int(current*0.90); atr_v=0

    # 타입별 추가매수가
    if vol_bad:
        add_buy="⛔ 거래량 동반 하락 (추가매수 금지!)"
    elif current<=avg*0.90:
        if pullback<1.5:   add_buy=f"🚀 B타입 즉시추가 {int(current*0.995):,}원"
        elif pullback<3.0: add_buy=f"📉 A타입 MA20 {int(ma20*0.99):,}원"
        else:              add_buy=f"📦 C타입 BB하단 {int(bb_lower):,}원"
    elif current<=avg*0.95:
        if pullback<1.5:   add_buy=f"🚀 B타입 1차 {int(current*0.995):,}원"
        else:              add_buy=f"📉 MA20대기 {int(ma20*0.99):,}원"
    else: add_buy="-"

    ma_sig,_=get_ma_cross(code,market)
    if current<=avg*0.92:        def_sell=f"{int(avg*0.92):,}원 ⚠️ 손절"
    elif current<=avg*0.97:      def_sell=f"{int(avg*0.95):,}원 (방어)"
    elif "데드크로스" in ma_sig: def_sell="⚠️ 데드크로스 → 비중 축소"
    else:                        def_sell="-"

    try:
        ticker=code+".KS" if market in ("KR","ETF_KR") else code
        hist2=yf.Ticker(ticker).history(period="2mo").dropna()
        low20=int(hist2["Low"].tail(20).min()) if len(hist2)>=20 else int(avg*0.93)
        turtle_sell=f"{low20:,}원 (이탈시 전량)"
    except: turtle_sell="-"

    q1,q2=max(1,int(qty*0.3)),max(1,int(qty*0.3))
    q3=max(1,qty-q1-q2)
    p1,p2,p3=int(avg*1.10),int(avg*1.20),int(avg*1.30)
    if profit_rate>=30:   split_sell=f"✅3차({q3}주/{p3:,}원)"
    elif profit_rate>=20: split_sell=f"✅2차({q2}주/{p2:,}원)|3차({q3}주/{p3:,}원)"
    elif profit_rate>=10: split_sell=f"✅1차({q1}주/{p1:,}원)|2차({q2}주/{p2:,}원)"
    else:                 split_sell=f"1차({q1}주/{p1:,}원)|2차({q2}주/{p2:,}원)|3차({q3}주/{p3:,}원)"

    atr_pct,vol=get_atr(code,market)
    if vol=="높음":   atr_sell=f"{int(avg*1.20):,}/{int(avg*1.40):,}원"
    elif vol=="낮음": atr_sell=f"{int(avg*1.07):,}/{int(avg*1.12):,}원"
    else:             atr_sell=f"{int(avg*1.10):,}/{int(avg*1.20):,}원"

    return {"추가매수":add_buy,"방어매도":def_sell,"터틀익절":turtle_sell,
            "분할익절":split_sell,"atr익절":atr_sell,
            "atr손절":f"{atr_stop:,}원 (-2ATR)","변동성":f"{vol}({atr_pct}%)"}

def get_recommend_method(name, market):
    etf_kw=["TIGER","RISE","SOL","TIME","KODEX","ACE","QQQ","VOO","SCHD","SPYG","BOTT"]
    large_kw=["삼성전자","POSCO","LS ELECTRIC","SK하이닉스","현대","삼성바이오","셀트리온","NAVER"]
    small_kw=["챔스미디어","솔트룩스","에코프로","아이에스동서","이수페타시스","일진전기"]
    if market in ("ETF_KR","US") or any(k in name for k in etf_kw): return "📊 분할익절","#27ae60"
    elif any(k in name for k in large_kw): return "🐢 터틀익절","#8e44ad"
    elif any(k in name for k in small_kw): return "📈 ATR익절","#e74c3c"
    return "📊 분할익절","#27ae60"

def get_vix_signal(macro):
    vix=macro.get("VIX",{}).get("가격",20)
    if vix>=40:   return "🟢 극단공포→역발상!","#27ae60",vix
    elif vix>=30: return "🔴 단타 완전 금지!","#e74c3c",vix
    elif vix>=25: return "🟠 보수적 매매","#e67e22",vix
    elif vix>=20: return "🟡 주의 구간","#f39c12",vix
    else:         return "🟢 안정→적극 매매","#27ae60",vix

# =====================================================
# Claude AI 요약
# =====================================================
def get_ai_summary(portfolio_rows, macro, vix_val, kr_picks, us_picks,
                   liquidity_score, liquidity_phase, market_signal, market_type):
    print(f"🔑 API 키: {ANTHROPIC_API_KEY[:20] if ANTHROPIC_API_KEY else '없음'}...")
    if not ANTHROPIC_API_KEY: return None

    port_summary=""
    for r in portfolio_rows:
        s=r.get("signals",{})
        line=f"{r['name']}: 등락률 {r['rate']:+.2f}%, 수익률 {r.get('profit_rate',0):+.1f}%"
        if s.get("방어매도") and s["방어매도"]!="-": line+=f", ⚠️{s['방어매도']}"
        if s.get("atr손절") and s["atr손절"]!="-": line+=f", ATR손절={s['atr손절']}"
        port_summary+=line+"\n"

    kr_summary="".join([f"{p['종목명']}({p['섹터']}): {p['주도주등급']} {p['주도주점수']}점, {p['매수판단']}, ATR손절={p['ATR손절가']:,}원\n" for p in kr_picks[:3]])
    us_summary="".join([f"{p['ETF코드']}({p['섹터']}): {p['과열도']}, ATR손절={p['ATR손절가']}\n" for p in us_picks])

    prompt=f"""당신은 투자 원칙서 기반의 주식 투자 어시스턴트입니다.

=== 시장 데이터 ===
시장신호등: {market_signal} ({market_type})
VIX: {vix_val} / 나스닥: {macro.get('나스닥',{}).get('등락률',0):+.2f}%
유동성: {liquidity_score}점 / 국면: {liquidity_phase}
계절성: {get_seasonality()}

=== 투자 원칙 ===
매수 기준: 주도주 65점↑ + 불장 + 사이클 60%↓
손절: ATR -2배 무조건
익절: 터틀 익절 (추세 끝까지)
월 한도: 현금의 20%

=== 포트폴리오 ===
{port_summary}

=== 주도주 TOP3 ===
{kr_summary}

=== 미국 ETF TOP2 ===
{us_summary}

아래 형식으로 간결하게:

📌 오늘 시장 한 줄 요약:

⚡ 오늘 단타: (가능/자제/금지 + 이유)

✅ 오늘 해야 할 일 (최대 5개):
1.
2.
3.

🚫 오늘 하지 말 것 (최대 3개):
1.
2.

🎯 주목할 주도주:

⚠️ 긴급 주의 종목: (ATR 손절 임박 종목, 없으면 없음)"""

    try:
        print("🤖 Claude API 호출 중...")
        res=requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key":ANTHROPIC_API_KEY,"anthropic-version":"2023-06-01","content-type":"application/json"},
            json={"model":"claude-haiku-4-5","max_tokens":800,"messages":[{"role":"user","content":prompt}]},
            timeout=30)
        print(f"📡 API 응답: {res.status_code}")
        data=res.json()
        if "content" in data:
            result=data["content"][0]["text"]
            print(f"✅ AI 요약 완료 ({len(result)}자)")
            return result
        return None
    except Exception as e:
        print(f"⚠️ Claude API 오류: {e}")
        return None

# =====================================================
# 이메일 전송
# =====================================================
def send_email(subject, html_body):
    msg=MIMEMultipart()
    msg["From"]=GMAIL_ADDRESS; msg["To"]=RECEIVE_ADDRESS; msg["Subject"]=subject
    msg.attach(MIMEText(html_body,"html","utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com",465) as smtp:
            smtp.login(GMAIL_ADDRESS,GMAIL_APP_PASSWORD)
            smtp.send_message(msg)
            print("✅ 이메일 전송 성공!")
    except Exception as e:
        print(f"❌ 이메일 전송 실패: {e}")

# =====================================================
# HTML 보고서 생성
# =====================================================
def build_report(token, holdings):
    today=dt.datetime.now(KST).strftime("%Y년 %m월 %d일 %H:%M")
    season=get_seasonality()

    print("🌍 거시경제 수집 중...")
    macro=get_macro()
    vix_signal,vix_color,vix_val=get_vix_signal(macro)

    print("💧 FRED 유동성 지표 수집 중...")
    liquidity=get_liquidity_data()
    liq_score,liq_phase,liq_color,liq_signals=get_liquidity_score(liquidity)

    print("🚦 시장 신호등 판단 중...")
    market_signal,market_color,market_type,market_strategy,_=get_market_signal(macro,liq_score)

    print("📊 섹터 건강도 분석 중...")
    sector_health=get_sector_health(liq_score)

    print("💼 포트폴리오 수집 중...")
    portfolio_rows=[]
    total_invest=total_current=0
    for code,name,qty,avg,market in holdings:
        print(f"  → {name} 조회 중...")
        if market in ("KR","ETF_KR"):
            price,rate,volume,high52,low52=get_kr_price(token,code)
            price_display=f"{price:,}원" if price else "-"
        else:
            usd,price,rate,high52,low52,fx=get_us_price(code)
            price_display=f"${usd:,.2f}(≈{price:,}원)" if price else "-"
        invest=avg*qty; current_val=price*qty if price else 0
        profit=current_val-invest
        profit_rate=(price-avg)/avg*100 if avg>0 and price>0 else 0
        total_invest+=invest; total_current+=current_val if price else invest
        signals=calc_signals(avg,price,code,market,qty,high52,low52,rate)
        rsi=get_rsi(code,market)
        ma_sig,ma_col=get_ma_cross(code,market)
        rec_method,rec_color=get_recommend_method(name,market)
        portfolio_rows.append({
            "name":name,"market":market,"qty":qty,"avg":avg,
            "price":price,"price_display":price_display,
            "rate":rate,"profit":profit,"profit_rate":profit_rate,
            "rate_color":"#e74c3c" if rate<0 else "#27ae60",
            "profit_color":"#e74c3c" if profit<0 else "#27ae60",
            "signals":signals,"rsi":rsi,
            "rsi_color":"#e74c3c" if rsi>=70 else "#27ae60" if rsi<=35 else "#333",
            "ma_sig":ma_sig,"ma_col":ma_col,
            "rec_method":rec_method,"rec_color":rec_color,
        })

    total_profit=total_current-total_invest
    total_profit_rate=total_profit/total_invest*100 if total_invest>0 else 0
    total_color="#e74c3c" if total_profit<0 else "#27ae60"
    max_loss=int(TOTAL_ASSETS*0.02)

    # 현금 계산 (대략)
    estimated_cash=CASH_LIMIT
    monthly_limit=int(estimated_cash*MONTHLY_LIMIT_PCT)

    print("🔍 탑다운 + 주도주 스크리너 실행 중...")
    kr_top5,us_top2,rec_sectors,phase_msg=run_topdown_screener(token,liq_score,sector_health,market_type)

    # 매수 체크리스트
    top_score=kr_top5[0]["주도주점수"] if kr_top5 else 0
    top_cycle=kr_top5[0]["사이클위치"] if kr_top5 else 50
    top_rsi=kr_top5[0]["RSI"] if kr_top5 else 50
    checks,buy_ok,m_limit=get_buy_checklist(market_type,liq_score,vix_val,top_score,top_cycle,top_rsi,estimated_cash)

    print("🤖 Claude AI 요약 생성 중...")
    ai_summary=get_ai_summary(portfolio_rows,macro,vix_val,kr_top5,us_top2,
                               liq_score,liq_phase,market_signal,market_type)

    # ── HTML 생성 ──

    # AI 요약
    if ai_summary:
        ai_html=ai_summary\
            .replace("📌 ","<br><b>📌 ").replace("⚡ ","<br><b>⚡ ")\
            .replace("✅ ","<br><b>✅ ").replace("🚫 ","<br><b>🚫 ")\
            .replace("🎯 ","<br><b>🎯 ").replace("⚠️ ","<br><b>⚠️ ")\
            .replace("\n","<br>")
        ai_section=f"""
  <div style="background:linear-gradient(135deg,#0d0d1a,#1a1a3e);color:white;padding:24px;border-bottom:3px solid #FFD700">
    <div style="font-size:16px;font-weight:bold;margin-bottom:14px;color:#FFD700">🤖 Claude AI 오늘의 핵심 요약</div>
    <div style="font-size:13px;line-height:2;color:#ECF0F1">{ai_html}</div>
  </div>"""
    else:
        ai_section="<div style='background:#f39c12;color:white;padding:14px;text-align:center'>⚠️ AI 요약 생성 실패</div>"

    # 시장 신호등 HTML
    signal_bg={"불장":"linear-gradient(135deg,#27ae60,#1e8449)",
                "역발상":"linear-gradient(135deg,#27ae60,#1e8449)",
                "횡보장":"linear-gradient(135deg,#f39c12,#d68910)",
                "하락장":"linear-gradient(135deg,#e74c3c,#c0392b)",
                "주의":"linear-gradient(135deg,#e67e22,#ca6f1e)"}
    strategy_map={
        "불장":"추세추종 전략 ON → 주도주 65점↑ 매수 / 터틀 익절 / ATR -2배 손절",
        "역발상":"VIX 극단공포 → 현금으로 ETF 역발상 매수 기회!",
        "횡보장":"선별적 매수 → RSI 30↓ + 볼린저 하단만 / 빠른 익절 +10%",
        "하락장":"현금 보유 → 매수 금지 / 보유 종목 손절 기준 강화",
        "주의":"보수적 → 신규 매수 자제 / 보유 종목 모니터링"
    }

    market_section=f"""
  <div style="background:{signal_bg.get(market_type,'linear-gradient(135deg,#888,#666)')};color:white;padding:20px;text-align:center">
    <div style="font-size:28px;font-weight:bold;margin-bottom:8px">{market_signal}</div>
    <div style="font-size:14px;opacity:0.9">{strategy_map.get(market_type,'전략 확인 필요')}</div>
    <div style="margin-top:10px;display:flex;justify-content:center;gap:20px;font-size:12px;opacity:0.8">
      <span>VIX {vix_val}</span>
      <span>유동성 {liq_score}점</span>
      <span>{season}</span>
      <span>월 매수한도 {monthly_limit:,}원</span>
    </div>
  </div>"""

    # 매수 체크리스트 HTML
    check_rows=""
    for check_name, check_result in checks:
        icon="✅" if check_result else "❌"
        color="#27ae60" if check_result else "#e74c3c"
        check_rows+=f"<tr><td style='color:{color};font-size:16px'>{icon}</td><td>{check_name}</td></tr>"

    checklist_section=f"""
  <div class="section">
    <div class="section-title">📋 오늘 매수 가능한가? (9가지 체크리스트)</div>
    <div style="display:flex;gap:16px;align-items:flex-start">
      <div style="background:{'#d5f5e3' if buy_ok else '#fadbd8'};border:2px solid {'#27ae60' if buy_ok else '#e74c3c'};border-radius:10px;padding:16px;text-align:center;min-width:140px">
        <div style="font-size:36px">{'✅' if buy_ok else '❌'}</div>
        <div style="font-size:14px;font-weight:bold;color:{'#27ae60' if buy_ok else '#e74c3c'}">{'매수 가능!' if buy_ok else '오늘은 패스!'}</div>
        <div style="font-size:11px;color:#666;margin-top:4px">월 한도: {monthly_limit:,}원</div>
      </div>
      <table style="flex:1;font-size:12px">
        {check_rows}
      </table>
    </div>
  </div>"""

    # 유동성 HTML
    liq_rows=""
    for name,val in liquidity.items():
        is_neg_good=name in ("역레포(RRP)","TGA 잔액")
        chg_color="#27ae60" if (is_neg_good and val["변화"]<0) or (not is_neg_good and val["변화"]>0) else "#e74c3c"
        liq_rows+=f"<tr><td><b>{name}</b><br><small style='color:#888'>{val['설명']}</small></td><td>{val['값']:,.1f}{val['단위']}</td><td style='color:{chg_color}'>{val['변화']:+.2f}{val['단위']}</td><td style='font-size:10px;color:#666'>{val['날짜']}</td></tr>"
    liq_signal_html="".join([f"<div style='font-size:12px;margin-bottom:4px'>{s}</div>" for s in liq_signals])

    # 섹터 건강도 HTML
    type_bg={"조류":"#EEEDFE","파도":"#E6F1FB","방어":"#EAF3DE"}
    type_color={"조류":"#3C3489","파도":"#0C447C","방어":"#27500A"}
    type_icon={"조류":"🌊","파도":"🌀","방어":"🛡️"}
    fit_colors={"⭐ 최우선":"#27ae60","✅ 우선":"#27ae60","✅ 보통":"#f39c12",
                "⚠️ 주의":"#e67e22","⚠️ 비추":"#e74c3c","❌ 비추":"#e74c3c"}
    sector_rows=""
    for i,s in enumerate(sector_health):
        rank="🥇" if i==0 else "🥈" if i==1 else "🥉" if i==2 else f"{i+1}"
        rate_color="#27ae60" if s["5일수익률"]>=0 else "#e74c3c"
        fit_color=fit_colors.get(s["적합도"],"#888")
        score_color="#27ae60" if s["종합점수"]>=70 else "#f39c12" if s["종합점수"]>=50 else "#e74c3c"
        sector_rows+=f"""<tr>
          <td>{rank}</td><td><b>{s['섹터']}</b></td>
          <td><span style="background:{type_bg[s['타입']]};color:{type_color[s['타입']]};padding:2px 5px;border-radius:4px;font-size:10px">{type_icon[s['타입']]} {s['타입']}</span></td>
          <td style="color:{rate_color}">{s['5일수익률']:+.2f}%</td>
          <td style="color:{fit_color};font-weight:bold">{s['적합도']}</td>
          <td style="color:{score_color};font-weight:bold">{s['종합점수']}점</td>
          <td style="font-size:10px;color:#2980b9">{s['us_etf']}</td>
        </tr>"""

    # 거시경제 HTML
    macro_html="".join([f"<div class='mc'><div class='ml'>{n}</div><div class='mv' style='color:{'#e74c3c' if v['등락률']<0 else '#27ae60'}'>{v['등락률']:+.2f}%</div></div>" for n,v in macro.items()])

    # 포트폴리오 HTML
    port_rows=""
    for r in portfolio_rows:
        s=r["signals"]
        atr_stop_color="#e74c3c" if s.get("atr손절","-")!="-" else "#888"
        port_rows+=f"""<tr>
          <td><b>{r['name']}</b><br><small style="color:#999">{r['market']}</small></td>
          <td>{r['price_display']}</td>
          <td style="color:{r['rate_color']}">{r['rate']:+.2f}%</td>
          <td style="color:{r['profit_color']}">{r['profit']:+,.0f}원<br>({r['profit_rate']:+.1f}%)</td>
          <td style="color:{r['rsi_color']};font-weight:bold">{r['rsi']}</td>
          <td style="color:{r['ma_col']};font-size:11px">{r['ma_sig']}</td>
          <td style="color:{r['rec_color']};font-size:11px;font-weight:bold">{r['rec_method']}</td>
          <td style="color:#2980b9;font-size:11px">{s['추가매수']}</td>
          <td style="color:#e67e22;font-size:11px">{s['방어매도']}</td>
          <td style="color:#8e44ad;font-size:11px">{s['터틀익절']}</td>
          <td style="color:#27ae60;font-size:11px">{s['분할익절']}</td>
          <td style="color:{atr_stop_color};font-size:11px;font-weight:bold">{s.get('atr손절','-')}</td>
        </tr>"""

    # 주도주 TOP5 HTML
    grade_color={"🔥🔥 슈퍼주도주":"#e74c3c","🔥 강력주도주":"#e67e22","⭐ 주도주후보":"#f39c12","➖ 일반종목":"#888"}
    entry_color={"🟢 초기(강력매수)":"#27ae60","🟡 중기(분할매수)":"#f39c12","🟠 후기(소량진입)":"#e67e22","🔴 고점주의(신중)":"#e74c3c"}
    heat_color={"🟢 정상 → 진입 가능":"#27ae60","🟠 약과열 → 신중":"#f39c12","🔴 과열 → 눌림 대기":"#e74c3c"}

    kr_rows=""
    for i,p in enumerate(kr_top5,1):
        medal="🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}위"
        tc=type_color.get(p["섹터타입"],"#888")
        tbg=type_bg.get(p["섹터타입"],"#eee")
        gc=grade_color.get(p["주도주등급"],"#888")
        ec=entry_color.get(p["진입타이밍"],"#888")
        hc=heat_color.get(p["과열도"],"#f39c12") if p["과열도"] in heat_color else "#f39c12"
        score=p["주도주점수"]
        buy_color=p["매수색상"]
        row_bg="#fff9f0" if score>=80 else "#fffff0" if score>=65 else ""
        kr_rows+=f"""<tr style="background:{row_bg}">
          <td><b>{medal} {p['종목명']}</b><br>
            <span style="background:{tbg};color:{tc};padding:2px 5px;border-radius:4px;font-size:10px">{type_icon.get(p['섹터타입'],'')} {p['섹터']}</span><br>
            <small style="color:#888">{p['종목타입']}</small>
          </td>
          <td>{p['현재가']:,}원</td>
          <td style="color:#2980b9;font-weight:bold">{p['추천매수가']:,}원</td>
          <td style="color:#e74c3c;font-weight:bold;font-size:11px">{p['ATR손절가']:,}원<br><small>(-2ATR)</small></td>
          <td style="color:{gc};font-weight:bold">{p['주도주등급']}</td>
          <td style="font-weight:bold">{score}점</td>
          <td style="background:{buy_color};color:white;font-weight:bold;font-size:11px;padding:4px;border-radius:4px">{p['매수판단']}<br><small>{p['추천투자금']:,}원</small></td>
          <td style="color:{ec};font-size:11px">{p['진입타이밍']}</td>
          <td style="color:{hc};font-size:11px">{p['과열도']}</td>
          <td style="color:#27ae60;font-size:11px">{p['업사이드']}</td>
          <td style="color:{'#e74c3c' if p['RSI']>=70 else '#27ae60' if p['RSI']<=35 else '#333'}">{p['RSI']}</td>
          <td style="font-size:10px;color:#666">{p['근거']}</td>
        </tr>"""

    # 미국 ETF TOP2 HTML
    us_rows=""
    for i,p in enumerate(us_top2,1):
        medal="🥇" if i==1 else "🥈"
        hc2="#27ae60" if "정상" in p["과열도"] else "#f39c12"
        us_rows+=f"""<tr>
          <td><b>{medal} {p['ETF코드']}</b><br><small style="color:#888">{p['섹터']}</small></td>
          <td>{p['현재가']}</td>
          <td style="color:#2980b9;font-weight:bold">{p['추천매수가']}</td>
          <td style="color:#e74c3c;font-weight:bold">{p['ATR손절가']}</td>
          <td style="color:{'#27ae60' if p['5일수익률']>=0 else '#e74c3c'}">{p['5일수익률']:+.2f}%</td>
          <td style="color:{'#e74c3c' if p['RSI']>=70 else '#27ae60' if p['RSI']<=35 else '#333'}">{p['RSI']}</td>
          <td>{p['사이클']}</td>
          <td style="color:{hc2};font-size:11px">{p['과열도']}</td>
          <td style="color:#27ae60">{p['업사이드']}</td>
        </tr>"""

    html=f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
  body{{font-family:'Malgun Gothic',sans-serif;background:#f5f7fa;color:#333;margin:0;padding:10px}}
  .container{{max-width:1500px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.1)}}
  .header{{background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);color:white;padding:20px;text-align:center}}
  .header h1{{margin:0;font-size:20px;letter-spacing:2px}}
  .section{{padding:16px;border-bottom:1px solid #eee}}
  .section-title{{font-size:13px;font-weight:bold;color:#1a1a2e;margin-bottom:10px;padding-left:8px;border-left:4px solid #0f3460}}
  table{{width:100%;border-collapse:collapse;font-size:11px}}
  th{{background:#1a1a2e;color:white;padding:7px 5px;text-align:center}}
  td{{padding:6px 5px;text-align:center;border-bottom:1px solid #f0f0f0;vertical-align:middle}}
  tr:hover{{background:#f8f9ff}}
  .summary-box{{display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap}}
  .summary-card{{flex:1;min-width:110px;background:#f8f9ff;border-radius:8px;padding:10px;text-align:center;border:1px solid #e0e4f0}}
  .summary-card .label{{font-size:10px;color:#888;margin-bottom:4px}}
  .summary-card .value{{font-size:15px;font-weight:bold}}
  .market-card{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}}
  .mc{{background:#f8f9ff;border-radius:6px;padding:8px 10px;text-align:center;border:1px solid #e0e4f0;flex:1;min-width:80px}}
  .mc .ml{{font-size:9px;color:#888}}
  .mc .mv{{font-size:13px;font-weight:bold}}
  .liq-box{{background:#f0f8ff;border:1px solid #3498db;border-radius:8px;padding:14px;margin-bottom:12px}}
  .footer{{background:#f8f9ff;padding:10px;text-align:center;font-size:10px;color:#999}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📊 포트폴리오 일일 보고서</h1>
    <p style="margin:4px 0 0;opacity:0.8;font-size:12px">{today} | {season}</p>
  </div>

  {ai_section}
  {market_section}
  {checklist_section}

  <div class="section">
    <div class="section-title">🌍 시장 현황</div>
    <div class="market-card">{macro_html}</div>
  </div>

  <div class="section">
    <div class="section-title">💧 FRED 유동성 지표</div>
    <div class="liq-box">
      <div style="display:flex;align-items:center;gap:16px;margin-bottom:10px">
        <div>
          <div style="font-size:24px;font-weight:bold;color:{liq_color}">{liq_score}점</div>
          <div style="font-size:13px;color:{liq_color};font-weight:bold">{liq_phase}</div>
        </div>
        <div>{liq_signal_html}</div>
      </div>
    </div>
    <div style="overflow-x:auto">
    <table><tr><th>지표</th><th>현재값</th><th>전주 대비</th><th>기준일</th></tr>{liq_rows}</table>
    </div>
  </div>

  <div class="section">
    <div class="section-title">📊 섹터 건강도 (23개 섹터) | 🌊 조류 🌀 파도 🛡️ 방어</div>
    <div style="overflow-x:auto">
    <table>
      <tr><th>순위</th><th>섹터명</th><th>타입</th><th>5일수익률</th><th>유동성 적합도</th><th>종합점수</th><th>미국 ETF</th></tr>
      {sector_rows}
    </table>
    </div>
  </div>

  <div class="section">
    <div class="section-title">🔥 탑다운 주도주 TOP5 (한국) | {phase_msg} | 스윙 중기 관점</div>
    <div style="font-size:11px;color:#666;margin-bottom:8px">
      📌 매수기준: 65점↑+불장+사이클60%↓ | 익절: 터틀(20캔들저점이탈) | 손절: ATR -2배 무조건
    </div>
    <div style="overflow-x:auto">
    <table>
      <tr><th>종목명/섹터/타입</th><th>현재가</th><th>추천매수가</th><th>ATR손절가</th><th>등급</th><th>점수</th><th>매수판단</th><th>진입타이밍</th><th>과열도</th><th>업사이드</th><th>RSI</th><th>근거</th></tr>
      {kr_rows if kr_rows else "<tr><td colspan='12' style='color:#999'>스크리닝 결과 없음</td></tr>"}
    </table>
    </div>
  </div>

  <div class="section">
    <div class="section-title">🌎 미국 ETF TOP2 | ATR 손절가 포함</div>
    <div style="overflow-x:auto">
    <table>
      <tr><th>ETF/섹터</th><th>현재가</th><th>추천매수가</th><th>ATR손절가</th><th>5일수익률</th><th>RSI</th><th>사이클</th><th>과열도</th><th>업사이드</th></tr>
      {us_rows if us_rows else "<tr><td colspan='9' style='color:#999'>데이터 없음</td></tr>"}
    </table>
    </div>
  </div>

  <div class="section">
    <div class="section-title">💼 포트폴리오 현황 ({len(holdings)}종목)</div>
    <div class="summary-box">
      <div class="summary-card"><div class="label">총 투자금</div><div class="value">{total_invest:,.0f}원</div></div>
      <div class="summary-card"><div class="label">현재 평가금</div><div class="value">{total_current:,.0f}원</div></div>
      <div class="summary-card"><div class="label">평가 손익</div><div class="value" style="color:{total_color}">{total_profit:+,.0f}원</div></div>
      <div class="summary-card"><div class="label">수익률</div><div class="value" style="color:{total_color}">{total_profit_rate:+.2f}%</div></div>
      <div class="summary-card"><div class="label">최대손실(2%룰)</div><div class="value" style="color:#e74c3c">{max_loss:,}원</div></div>
      <div class="summary-card"><div class="label">월 매수한도</div><div class="value" style="color:#2980b9">{monthly_limit:,}원</div></div>
    </div>
    <div style="overflow-x:auto">
    <table>
      <tr><th>종목명</th><th>현재가</th><th>등락률</th><th>평가손익</th><th>RSI</th><th>MA신호</th><th>추천기법</th><th>추가매수</th><th>방어매도</th><th>🐢터틀익절</th><th>📊분할익절</th><th>🛑ATR손절</th></tr>
      {port_rows}
    </table>
    </div>
  </div>

  <div class="footer">
    ⚠️ 본 보고서는 투자 원칙서 기반 참고용이며 투자 판단의 최종 책임은 본인에게 있습니다.<br>
    FRED + Google Sheets + Claude AI + 탑다운 스크리너 + 시장신호등 + ATR손절 + 매수체크리스트
  </div>
</div>
</body>
</html>"""
    return html

# =====================================================
# 메인
# =====================================================
def main():
    print("="*50)
    print("📊 포트폴리오 보고서 생성 시작")
    print("="*50)
    holdings=load_holdings_from_sheets()
    try:
        token=get_token()
    except Exception as e:
        print(f"⚠️ 토큰 발급 실패: {e}")
        token=""
    html=build_report(token,holdings)
    with open("portfolio_report.html","w",encoding="utf-8") as f:
        f.write(html)
    print("✅ 보고서 저장 완료")
    today_str=dt.datetime.now(KST).strftime("%Y/%m/%d")
    send_email(f"📊 [{today_str}] 포트폴리오 보고서",html)
    print("✅ 완료!")

if __name__=="__main__":
    main()

# portfolio_report.py
# 포트폴리오 중심 일일 보고서 생성기
# Google Sheets 연동 + Claude AI 요약 + FRED 유동성 지표
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

# =====================================================
# ✅ 설정값
# =====================================================
APP_KEY            = os.environ.get("APP_KEY", "")
APP_SECRET         = os.environ.get("APP_SECRET", "")
GMAIL_ADDRESS      = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
RECEIVE_ADDRESS    = os.environ.get("RECEIVE_ADDRESS", "")
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
FRED_API_KEY       = os.environ.get("FRED_API_KEY", "")
TOKEN_FILE         = "token.json"
TOTAL_ASSETS       = 24_000_000
SHEET_ID           = "1-7TeKv9OucJYMvXN55yQ5w0Rg0Fwi8QQH44jmUfzElg"

# =====================================================
# FRED 유동성 지표
# =====================================================
def get_fred_data(series_id, limit=2):
    """FRED API에서 데이터 조회"""
    try:
        url = f"https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": series_id,
            "api_key": FRED_API_KEY,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit,
        }
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        obs = data.get("observations", [])
        if len(obs) >= 1:
            latest = float(obs[0]["value"]) if obs[0]["value"] != "." else 0
            prev   = float(obs[1]["value"]) if len(obs) >= 2 and obs[1]["value"] != "." else latest
            change = latest - prev
            return latest, change, obs[0]["date"]
        return 0, 0, "-"
    except Exception as e:
        print(f"  ⚠️ FRED {series_id} 오류: {e}")
        return 0, 0, "-"

def get_liquidity_data():
    """유동성 핵심 지표 수집"""
    print("💧 FRED 유동성 지표 수집 중...")
    indicators = {
        "역레포(RRP)":      ("RRPONTSYD",  "$B", "감소=유동성 공급"),
        "TGA 잔액":         ("WTREGEN",    "$B", "감소=유동성 공급"),
        "연준 총자산":      ("WALCL",      "$B", "감소=QT 진행"),
        "지급준비금":       ("WRESBAL",    "$B", "3조↑=안정"),
        "하이일드 스프레드":("BAMLH0A0HYM2","%", "8↑=위기"),
        "금융스트레스지수": ("STLFSI4",    "",   "0↑=스트레스"),
        "M2 통화량":        ("M2SL",       "$B", "증가=유동성↑"),
        "장단기 금리차":    ("T10Y2Y",     "%",  "음수=침체경고"),
    }
    result = {}
    for name, (series_id, unit, desc) in indicators.items():
        val, change, date = get_fred_data(series_id)
        result[name] = {
            "값": round(val, 2),
            "변화": round(change, 2),
            "날짜": date,
            "단위": unit,
            "설명": desc,
        }
    return result

def get_liquidity_score(liquidity):
    """유동성 종합 점수 계산 (100점 만점)"""
    score = 50  # 기본 50점
    signals = []

    # 역레포 감소 → 유동성 공급 (긍정)
    rrp = liquidity.get("역레포(RRP)", {})
    if rrp.get("변화", 0) < -10:
        score += 10
        signals.append("✅ 역레포 감소 (유동성 공급)")
    elif rrp.get("변화", 0) > 10:
        score -= 10
        signals.append("⚠️ 역레포 증가 (유동성 흡수)")

    # TGA 감소 → 유동성 공급 (긍정)
    tga = liquidity.get("TGA 잔액", {})
    if tga.get("변화", 0) < -20:
        score += 10
        signals.append("✅ TGA 감소 (정부 지출 확대)")
    elif tga.get("변화", 0) > 20:
        score -= 10
        signals.append("⚠️ TGA 증가 (유동성 흡수)")

    # 하이일드 스프레드
    hy = liquidity.get("하이일드 스프레드", {})
    if hy.get("값", 5) < 4:
        score += 10
        signals.append("✅ 하이일드 스프레드 정상")
    elif hy.get("값", 5) > 6:
        score -= 15
        signals.append("🔴 하이일드 스프레드 확대 (신용위험)")

    # 금융스트레스지수
    fsi = liquidity.get("금융스트레스지수", {})
    if fsi.get("값", 0) < 0:
        score += 10
        signals.append("✅ 금융 스트레스 낮음")
    elif fsi.get("값", 0) > 1:
        score -= 15
        signals.append("🔴 금융 스트레스 높음")

    # 장단기 금리차
    spread = liquidity.get("장단기 금리차", {})
    if spread.get("값", 0) > 0.5:
        score += 10
        signals.append("✅ 금리차 정상 (경기 양호)")
    elif spread.get("값", 0) < -0.5:
        score -= 10
        signals.append("⚠️ 금리차 역전 (침체 경고)")

    score = max(0, min(100, score))

    if score >= 70:
        phase = "🟢 유동성 확장 (성장주 우위)"
        phase_color = "#27ae60"
    elif score >= 50:
        phase = "🟡 유동성 중립"
        phase_color = "#f39c12"
    else:
        phase = "🔴 유동성 수축 (방어주 우위)"
        phase_color = "#e74c3c"

    return score, phase, phase_color, signals

# =====================================================
# Google Sheets 연동
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
                if code and name and qty > 0 and avg > 0:
                    holdings.append((code, name, qty, avg, market))
            except:
                continue
        print(f"✅ {len(holdings)}개 종목 로드 완료")
        return holdings
    except Exception as e:
        print(f"⚠️ 구글 시트 읽기 실패: {e}")
        return get_default_holdings()

def get_default_holdings():
    return [
        ("005490", "POSCO홀딩스",                  10,  424550, "KR"),
        ("005930", "삼성전자",                       4,   60100, "KR"),
        ("005935", "삼성전자우",                     5,  187520, "KR"),
        ("007660", "이수페타시스",                   5,  133960, "KR"),
        ("010780", "아이에스동서",                   1,   38450, "KR"),
        ("094360", "챔스미디어",                     9,   27361, "KR"),
        ("247540", "에코프로비엠",                   8,  235750, "KR"),
        ("304100", "솔트룩스",                       3,   29383, "KR"),
        ("010120", "LS ELECTRIC",                    6,  253417, "KR"),
        ("103590", "일진전기",                      10,   92400, "KR"),
        ("035420", "NAVER",                         10,  252000, "KR"),
        ("329180", "HD현대중공업",                   2,  647000, "KR"),
        ("QQQ",    "Invesco QQQ",                    1,  907209, "US"),
        ("SPYG",   "SPDR S&P500 Growth",             7,  157479, "US"),
        ("SCHD",   "Schwab Dividend",               26,   40186, "US"),
        ("VOO",    "Vanguard S&P500",                2,  907785, "US"),
        ("BOTT",   "THEMES HUMANOID ROBOTICS ETF",   3,   82969, "US"),
        ("360750", "TIGER 미국S&P500",              55,   24635, "ETF_KR"),
        ("426030", "TIME 나스닥100",                30,   35102, "ETF_KR"),
        ("458730", "TIGER 미국배당다운존스",         56,   14074, "ETF_KR"),
        ("364970", "TIGER 바이오TOP10",             10,    7520, "ETF_KR"),
        ("465580", "RISE 미국AI밸류체인",           47,   17987, "ETF_KR"),
        ("464310", "TIGER 글로벌AI&로보틱스INDXX",  10,   17165, "ETF_KR"),
        ("441680", "TIGER 나스닥100커버드콜",      111,   10719, "ETF_KR"),
        ("0167A0", "SOL AI반도체TOP2플러스",         5,   21215, "ETF_KR"),
        ("395160", "KODEX AI반도체TOP2플러스",       3,   45856, "ETF_KR"),
        ("445290", "KODEX 로봇액티브",              20,   48250, "ETF_KR"),
        ("487240", "KODEX AI전력핵심설비",          20,   50775, "ETF_KR"),
    ]

SWING_CANDIDATES = [
    ("005930", "삼성전자"), ("000660", "SK하이닉스"),
    ("035420", "NAVER"), ("329180", "HD현대중공업"),
    ("051910", "LG화학"), ("006400", "삼성SDI"),
    ("207940", "삼성바이오로직스"), ("068270", "셀트리온"),
    ("005490", "POSCO홀딩스"), ("010120", "LS ELECTRIC"),
]

THEME_KEYWORDS = {
    "AI/반도체": ["AI", "반도체", "HBM", "SK하이닉스", "이수페타시스", "솔트룩스"],
    "전력/전기": ["전력", "전기", "LS", "효성", "일진"],
    "2차전지":   ["에코프로", "삼성SDI", "LG화학"],
    "조선/해운": ["HD현대", "조선", "해운"],
    "바이오":    ["바이오", "셀트리온", "삼성바이오"],
    "로봇":      ["로봇", "ROBOT", "HUMANOID"],
}

# 조류(구조적) vs 파도(사이클) 섹터 분류
STRUCTURAL_SECTORS = ["AI", "반도체", "전력", "전기", "로봇", "방산", "우주"]
CYCLICAL_SECTORS   = ["조선", "화학", "금융", "소비재", "해운"]

def get_theme(name):
    for theme, words in THEME_KEYWORDS.items():
        if any(w.lower() in name.lower() for w in words):
            return theme
    return "일반"

def get_sector_type(name):
    if any(w in name for w in STRUCTURAL_SECTORS):
        return "🌊 조류(구조적)", "#8e44ad"
    elif any(w in name for w in CYCLICAL_SECTORS):
        return "🌀 파도(사이클)", "#2980b9"
    return "일반", "#888"

def get_recommend_method(name, market):
    etf_kw   = ["TIGER","RISE","SOL","TIME","KODEX","ACE","QQQ","VOO","SCHD","SPYG","BOTT"]
    large_kw = ["삼성전자","POSCO","LS ELECTRIC","SK하이닉스","현대","삼성바이오","셀트리온","NAVER"]
    small_kw = ["챔스미디어","솔트룩스","에코프로","아이에스동서","이수페타시스","일진전기"]
    if market in ("ETF_KR","US") or any(k in name for k in etf_kw):
        return "📊 분할익절", "#27ae60"
    elif any(k in name for k in large_kw):
        return "🐢 터틀익절", "#8e44ad"
    elif any(k in name for k in small_kw):
        return "📈 ATR익절", "#e74c3c"
    return "📊 분할익절", "#27ae60"

# =====================================================
# 토큰
# =====================================================
def get_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE,"r") as f:
            data = json.load(f)
        if data.get("issued_at") == dt.datetime.now(KST).strftime("%Y-%m-%d"):
            return data["access_token"]
    url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    res = requests.post(url,
        headers={"content-type":"application/json"},
        data=json.dumps({"grant_type":"client_credentials","appkey":APP_KEY,"appsecret":APP_SECRET}))
    token_data = res.json()
    token_data["issued_at"] = dt.datetime.now(KST).strftime("%Y-%m-%d")
    with open(TOKEN_FILE,"w") as f:
        json.dump(token_data,f)
    return token_data["access_token"]

# =====================================================
# 가격 조회
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
        res    = requests.get(url, headers=headers,
            params={"FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":code}, timeout=10)
        output = res.json().get("output",{})
        return (int(output.get("stck_prpr",0)), float(output.get("prdy_ctrt",0)),
                int(output.get("acml_vol",0)), int(output.get("w52_hgpr",0)),
                int(output.get("w52_lwpr",0)))
    except:
        return 0,0,0,0,0

def get_us_price(ticker):
    try:
        t    = yf.Ticker(ticker)
        info = t.info
        usd  = info.get("currentPrice") or info.get("regularMarketPrice",0)
        fx   = yf.Ticker("USDKRW=X").info.get("regularMarketPrice",1380)
        return usd, int(usd*fx), info.get("regularMarketChangePercent",0), \
               info.get("fiftyTwoWeekHigh",0), info.get("fiftyTwoWeekLow",0), fx
    except:
        return 0,0,0,0,0,1380

# =====================================================
# 거시경제
# =====================================================
def get_macro():
    tickers = {
        "S&P500":"^GSPC","나스닥":"^IXIC","다우":"^DJI",
        "VIX":"^VIX","달러인덱스":"DX-Y.NYB",
        "원달러환율":"USDKRW=X","WTI유가":"CL=F","금":"GC=F",
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
# 기술적 분석
# =====================================================
def get_rsi(code, market, period=14):
    try:
        ticker = code+".KS" if market in ("KR","ETF_KR") else code
        hist   = yf.Ticker(ticker).history(period="2mo").dropna()
        if len(hist) < period+1: return 50
        delta = hist["Close"].diff()
        gain  = delta.where(delta>0,0).rolling(period).mean()
        loss  = (-delta.where(delta<0,0)).rolling(period).mean()
        rs    = gain/loss
        return round((100-(100/(1+rs))).iloc[-1],1)
    except:
        return 50

def get_ma_cross(code, market):
    try:
        ticker = code+".KS" if market in ("KR","ETF_KR") else code
        hist   = yf.Ticker(ticker).history(period="4mo").dropna()
        if len(hist) < 60: return "-","#888"
        ma20 = hist["Close"].rolling(20).mean().iloc[-1]
        ma60 = hist["Close"].rolling(60).mean().iloc[-1]
        curr = hist["Close"].iloc[-1]
        if ma20>ma60 and curr>ma20:   return "🟢 골든크로스","#27ae60"
        elif ma20<ma60 and curr<ma20: return "🔴 데드크로스","#e74c3c"
        elif curr>ma20>ma60:          return "🟢 상승추세","#27ae60"
        elif curr<ma20:               return "🟡 20일선하회","#f39c12"
        return "🟡 횡보","#888"
    except:
        return "-","#888"

def get_atr(code, market, period=14):
    try:
        ticker = code+".KS" if market in ("KR","ETF_KR") else code
        hist   = yf.Ticker(ticker).history(period="1mo").dropna()
        if len(hist) < period: return 0,"중간"
        hist["TR"] = hist.apply(
            lambda r: max(r["High"]-r["Low"],
                abs(r["High"]-hist["Close"].shift(1).get(r.name,r["Close"])),
                abs(r["Low"]-hist["Close"].shift(1).get(r.name,r["Close"]))), axis=1)
        atr_pct = hist["TR"].tail(period).mean()/hist["Close"].iloc[-1]*100
        vol = "높음" if atr_pct>=4 else "낮음" if atr_pct<2 else "중간"
        return round(atr_pct,2), vol
    except:
        return 0,"중간"

def get_turtle_signal(code, price):
    try:
        hist   = yf.Ticker(code+".KS").history(period="2mo").dropna()
        if len(hist) < 20: return "-","#888","-","-","-"
        high20 = int(hist["High"].tail(20).max())
        low20  = int(hist["Low"].tail(20).min())
        curr   = price or int(hist["Close"].iloc[-1])
        if curr>=high20:   sig,col = "🔴 매수신호","#e74c3c"
        elif curr<=low20:  sig,col = "🔵 매도신호","#2980b9"
        else:
            gap = round((high20-curr)/curr*100,1)
            sig,col = f"⏳ 대기({gap}%)","#888"
        loss_pct = (curr-low20)/curr*100 if curr>low20 else 1
        rec      = int(TOTAL_ASSETS*0.02/(loss_pct/100)) if loss_pct>0 else 0
        return sig,col,f"{high20:,}원",f"{low20:,}원",f"{rec:,}원"
    except:
        return "-","#888","-","-","-"

def calc_signals(avg, current, code, market, qty, high52, low52, current_rate):
    if current==0 or avg==0:
        return {k:"-" for k in ["추가매수","방어매도","터틀익절","분할익절","atr익절","변동성"]}

    profit_rate = (current-avg)/avg*100

    try:
        ticker  = code+".KS" if market in ("KR","ETF_KR") else code
        hist    = yf.Ticker(ticker).history(period="1mo").dropna()
        avg_vol = hist["Volume"].tail(20).mean()
        now_vol = hist["Volume"].iloc[-1]
        vol_bad = current_rate < -2 and now_vol > avg_vol*1.5
    except:
        vol_bad = False

    if vol_bad:
        add_buy = "⛔ 거래량 동반 하락 (추가매수 금지!)"
    elif current <= avg*0.90:
        add_buy = f"{int(current*0.97):,}원 (2차추가)"
    elif current <= avg*0.95:
        add_buy = f"{int(current*0.97):,}원 (1차추가)"
    else:
        add_buy = "-"

    ma_sig,_ = get_ma_cross(code, market)
    if current <= avg*0.92:
        def_sell = f"{int(avg*0.92):,}원 ⚠️ 손절"
    elif current <= avg*0.97:
        def_sell = f"{int(avg*0.95):,}원 (방어)"
    elif "데드크로스" in ma_sig:
        def_sell = "⚠️ 데드크로스 → 비중 축소"
    else:
        def_sell = "-"

    try:
        ticker = code+".KS" if market in ("KR","ETF_KR") else code
        hist   = yf.Ticker(ticker).history(period="2mo").dropna()
        low20  = int(hist["Low"].tail(20).min()) if len(hist)>=20 else int(avg*0.93)
        turtle_sell = f"{low20:,}원 (이탈시 전량)"
    except:
        turtle_sell = "-"

    q1,q2 = max(1,int(qty*0.3)), max(1,int(qty*0.3))
    q3    = max(1,qty-q1-q2)
    p1,p2,p3 = int(avg*1.10),int(avg*1.20),int(avg*1.30)
    if profit_rate>=30:
        split_sell = f"✅3차({q3}주/{p3:,}원)"
    elif profit_rate>=20:
        split_sell = f"✅2차({q2}주/{p2:,}원) | 3차({q3}주/{p3:,}원)"
    elif profit_rate>=10:
        split_sell = f"✅1차({q1}주/{p1:,}원) | 2차({q2}주/{p2:,}원)"
    else:
        split_sell = f"1차({q1}주/{p1:,}원) | 2차({q2}주/{p2:,}원) | 3차({q3}주/{p3:,}원)"

    atr_pct, vol = get_atr(code, market)
    if vol=="높음":   atr_sell = f"{int(avg*1.20):,}/{int(avg*1.40):,}원"
    elif vol=="낮음": atr_sell = f"{int(avg*1.07):,}/{int(avg*1.12):,}원"
    else:             atr_sell = f"{int(avg*1.10):,}/{int(avg*1.20):,}원"

    return {
        "추가매수":add_buy,"방어매도":def_sell,
        "터틀익절":turtle_sell,"분할익절":split_sell,
        "atr익절":atr_sell,"변동성":f"{vol}({atr_pct}%)",
    }

def get_swing_picks(token, liquidity_score):
    picks = []
    for code, name in SWING_CANDIDATES:
        price,rate,volume,high52,low52 = get_kr_price(token,code)
        if price==0: continue
        score,reason = 0,[]

        if low52>0 and (price-low52)/low52*100<=30: score+=20; reason.append("52주저가근접")
        if high52>0 and -20<=(price-high52)/high52*100<=-5: score+=20; reason.append("고점눌림")
        if 1<=rate<=5: score+=20; reason.append("안정상승")
        elif rate>5:   score+=10; reason.append("강한상승")
        if volume>=1_000_000: score+=20; reason.append("거래량풍부")

        rsi = get_rsi(code,"KR")
        ma_sig,ma_col = get_ma_cross(code,"KR")
        if rsi<=35: score+=15; reason.append(f"RSI과매도({rsi})")
        if "골든크로스" in ma_sig: score+=15; reason.append("골든크로스")
        elif "데드크로스" in ma_sig: score-=15

        turtle_sig,turtle_col,high20,low20,rec_buy = get_turtle_signal(code,price)
        if "매수신호" in turtle_sig: score+=15; reason.append("터틀매수")

        # 유동성 점수에 따라 섹터 가점
        sector_type, _ = get_sector_type(name)
        if liquidity_score >= 70 and "조류" in sector_type:
            score += 10; reason.append("유동성확장+구조적섹터")
        elif liquidity_score < 50 and "파도" in sector_type:
            score -= 10

        picks.append({
            "종목명":name,"현재가":price,"추천매수가":int(price*0.98),
            "추천주수":max(1,int(1_000_000//(price*0.98))),
            "점수":score,"근거":", ".join(reason) or "기본관찰",
            "RSI":rsi,"MA신호":ma_sig,"MA색상":ma_col,
            "터틀신호":turtle_sig,"터틀색상":turtle_col,
            "20캔들고점":high20,"20캔들저점":low20,"추천투자금":rec_buy,
            "섹터타입":sector_type,
        })
    return sorted(picks,key=lambda x:x["점수"],reverse=True)[:5]

def get_vix_signal(macro):
    vix = macro.get("VIX",{}).get("가격",20)
    if vix>=40:   return "🟢 극단적 공포→역발상 기회!","#27ae60",vix
    elif vix>=30: return "🔴 단타 완전 금지!","#e74c3c",vix
    elif vix>=25: return "🟠 보수적 매매","#e67e22",vix
    elif vix>=20: return "🟡 주의 구간","#f39c12",vix
    else:         return "🟢 안정→적극 매매","#27ae60",vix

def get_seasonality():
    month = dt.datetime.now(KST).month
    m = {1:"🟢 1월효과(강세)",2:"🟡 2월조정",3:"🟢 3월반등",4:"🟡 4월주의",
         5:"🔴 5월경고(약세)",6:"🟡 6월보합",7:"🟢 7월반등",8:"🟡 8월변동",
         9:"🔴 9월경고(약세)",10:"🟢 10월기회",11:"🟢 11월강세",12:"🟢 12월랠리"}
    return m.get(month,"🟡 보통")

# =====================================================
# Claude AI 요약
# =====================================================
def get_ai_summary(portfolio_rows, macro, vix_val, swing_picks, liquidity_score, liquidity_phase):
    print(f"🔑 API 키 확인: {ANTHROPIC_API_KEY[:20] if ANTHROPIC_API_KEY else '없음'}...")
    if not ANTHROPIC_API_KEY:
        return None

    port_summary = ""
    for r in portfolio_rows:
        s = r.get("signals", {})
        line = f"{r['name']}: 등락률 {r['rate']:+.2f}%, 수익률 {r.get('profit_rate',0):+.1f}%"
        if s.get("추가매수") and s["추가매수"] != "-":
            line += f", 추가매수={s['추가매수']}"
        if s.get("방어매도") and s["방어매도"] != "-":
            line += f", 방어매도={s['방어매도']}"
        port_summary += line + "\n"

    swing_summary = ""
    for p in swing_picks[:3]:
        swing_summary += f"{p['종목명']}: {p['터틀신호']}, RSI {p['RSI']}, {p['섹터타입']}\n"

    nq_rate = macro.get("나스닥",{}).get("등락률",0)
    season  = get_seasonality()

    prompt = f"""당신은 주식 투자 어시스턴트입니다. 아래 데이터를 분석해서 오늘 바로 행동할 수 있는 핵심 요약을 만들어주세요.

=== 시장 데이터 ===
VIX: {vix_val} / 나스닥: {nq_rate:+.2f}% / 계절성: {season}
유동성 점수: {liquidity_score}점 / 시장 국면: {liquidity_phase}

=== 포트폴리오 ===
{port_summary}

=== 스윙 추천 TOP3 ===
{swing_summary}

아래 형식으로 간결하게 답변:

📌 오늘 시장 한 줄 요약:

⚡ 오늘 단타: (가능/자제/금지 + 이유)

✅ 오늘 해야 할 일 (최대 5개):
1.
2.
3.

🚫 오늘 하지 말 것 (최대 3개):
1.
2.

🎯 주목할 종목 (최대 3개):

⚠️ 긴급 주의 종목: (없으면 없음)"""

    try:
        print("🤖 Claude API 호출 중...")
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": 800,
                "messages": [{"role":"user","content":prompt}]
            },
            timeout=30
        )
        print(f"📡 API 응답: {res.status_code}")
        data = res.json()
        if "content" in data:
            result = data["content"][0]["text"]
            print(f"✅ AI 요약 완료 ({len(result)}자)")
            return result
        else:
            print(f"⚠️ 응답 오류: {data}")
            return None
    except Exception as e:
        print(f"⚠️ Claude API 오류: {e}")
        return None

# =====================================================
# 이메일 전송
# =====================================================
def send_email(subject, html_body):
    msg = MIMEMultipart()
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = RECEIVE_ADDRESS
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
def build_report(token, holdings):
    today = dt.datetime.now(KST).strftime("%Y년 %m월 %d일 %H:%M")

    print("🌍 거시경제 수집 중...")
    macro = get_macro()
    vix_signal, vix_color, vix_val = get_vix_signal(macro)
    season = get_seasonality()

    print("💧 FRED 유동성 지표 수집 중...")
    liquidity = get_liquidity_data()
    liq_score, liq_phase, liq_color, liq_signals = get_liquidity_score(liquidity)

    print("💼 포트폴리오 수집 중...")
    portfolio_rows = []
    total_invest = total_current = 0

    for code, name, qty, avg, market in holdings:
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

        signals       = calc_signals(avg,price,code,market,qty,high52,low52,rate)
        rsi           = get_rsi(code,market)
        ma_sig,ma_col = get_ma_cross(code,market)
        rec_method,rec_color = get_recommend_method(name,market)
        sector_type,sector_color = get_sector_type(name)

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
            "sector_type":sector_type,"sector_color":sector_color,
        })

    print("🎯 스윙 추천 분석 중...")
    swing_picks = get_swing_picks(token, liq_score)

    print("🤖 Claude AI 요약 생성 중...")
    ai_summary = get_ai_summary(portfolio_rows, macro, vix_val, swing_picks, liq_score, liq_phase)

    total_profit      = total_current-total_invest
    total_profit_rate = total_profit/total_invest*100 if total_invest>0 else 0
    total_color       = "#e74c3c" if total_profit<0 else "#27ae60"
    max_loss          = int(TOTAL_ASSETS*0.02)

    # AI 요약 HTML
    if ai_summary:
        ai_html = ai_summary\
            .replace("📌 ","<br><b>📌 ").replace("⚡ ","<br><b>⚡ ")\
            .replace("✅ ","<br><b>✅ ").replace("🚫 ","<br><b>🚫 ")\
            .replace("🎯 ","<br><b>🎯 ").replace("⚠️ ","<br><b>⚠️ ")\
            .replace("\n","<br>")
        ai_section = f"""
  <div style="background:linear-gradient(135deg,#0d0d1a,#1a1a3e);color:white;padding:24px;border-bottom:3px solid #FFD700">
    <div style="font-size:16px;font-weight:bold;margin-bottom:14px;color:#FFD700">🤖 Claude AI 오늘의 핵심 요약</div>
    <div style="font-size:13px;line-height:2;color:#ECF0F1">{ai_html}</div>
  </div>"""
    else:
        ai_section = "<div style='background:#f39c12;color:white;padding:14px;text-align:center'>⚠️ AI 요약 생성 실패</div>"

    # 유동성 지표 HTML
    liq_rows = ""
    for name, val in liquidity.items():
        change_color = "#27ae60" if val["변화"] < 0 else "#e74c3c" if val["변화"] > 0 else "#888"
        if name in ("역레포(RRP)","TGA 잔액"):
            change_color = "#27ae60" if val["변화"] < 0 else "#e74c3c"
        liq_rows += f"""
        <tr>
          <td><b>{name}</b><br><small style="color:#888">{val['설명']}</small></td>
          <td>{val['값']:,.1f}{val['단위']}</td>
          <td style="color:{change_color}">{val['변화']:+.2f}{val['단위']}</td>
          <td style="font-size:10px;color:#666">{val['날짜']}</td>
        </tr>"""

    liq_signal_html = "".join([f"<div style='font-size:12px;margin-bottom:4px'>{s}</div>" for s in liq_signals])

    # 거시경제 HTML
    macro_html = "".join([
        f"<div class='mc'><div class='ml'>{n}</div><div class='mv' style='color:{'#e74c3c' if v['등락률']<0 else '#27ae60'}'>{v['등락률']:+.2f}%</div></div>"
        for n,v in macro.items()
    ])

    # 포트폴리오 HTML
    port_rows = ""
    for r in portfolio_rows:
        s = r["signals"]
        port_rows += f"""
        <tr>
          <td><b>{r['name']}</b><br>
            <small style="color:{r['sector_color']}">{r['sector_type']}</small>
          </td>
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
          <td style="color:#e74c3c;font-size:11px">{s['atr익절']}</td>
        </tr>"""

    # 스윙 추천 HTML
    swing_rows = ""
    for i,p in enumerate(swing_picks,1):
        swing_rows += f"""
        <tr>
          <td><b>{i}. {p['종목명']}</b><br><small style="color:#888">{p['섹터타입']}</small></td>
          <td>{p['현재가']:,}원</td>
          <td style="color:#2980b9"><b>{p['추천매수가']:,}원</b></td>
          <td style="color:{'#e74c3c' if p['RSI']>=70 else '#27ae60' if p['RSI']<=35 else '#333'}">{p['RSI']}</td>
          <td style="color:{p['MA색상']};font-size:11px">{p['MA신호']}</td>
          <td style="color:{p['터틀색상']};font-weight:bold;font-size:11px">{p['터틀신호']}</td>
          <td style="color:#27ae60;font-size:11px">{p['추천투자금']}</td>
          <td style="font-size:11px">{p['근거']}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
  body{{font-family:'Malgun Gothic',sans-serif;background:#f5f7fa;color:#333;margin:0;padding:10px}}
  .container{{max-width:1400px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.1)}}
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
    <p style="margin:4px 0 0;opacity:0.8;font-size:12px">{today} | VIX {vix_val} {vix_signal} | {season}</p>
  </div>

  {ai_section}

  <!-- 시장 현황 -->
  <div class="section">
    <div class="section-title">🌍 시장 현황</div>
    <div class="market-card">{macro_html}</div>
  </div>

  <!-- FRED 유동성 지표 -->
  <div class="section">
    <div class="section-title">💧 FRED 유동성 지표 (시장 국면 판별)</div>
    <div class="liq-box">
      <div style="display:flex;align-items:center;gap:16px;margin-bottom:12px">
        <div>
          <div style="font-size:22px;font-weight:bold;color:{liq_color}">{liq_score}점</div>
          <div style="font-size:14px;color:{liq_color};font-weight:bold">{liq_phase}</div>
        </div>
        <div>{liq_signal_html}</div>
      </div>
    </div>
    <div style="overflow-x:auto">
    <table>
      <tr><th>지표</th><th>현재값</th><th>전주 대비</th><th>기준일</th></tr>
      {liq_rows}
    </table>
    </div>
  </div>

  <!-- 포트폴리오 -->
  <div class="section">
    <div class="section-title">💼 포트폴리오 현황 ({len(holdings)}종목) | 🌊 조류(구조적) 🌀 파도(사이클)</div>
    <div class="summary-box">
      <div class="summary-card"><div class="label">총 투자금</div><div class="value">{total_invest:,.0f}원</div></div>
      <div class="summary-card"><div class="label">현재 평가금</div><div class="value">{total_current:,.0f}원</div></div>
      <div class="summary-card"><div class="label">평가 손익</div><div class="value" style="color:{total_color}">{total_profit:+,.0f}원</div></div>
      <div class="summary-card"><div class="label">수익률</div><div class="value" style="color:{total_color}">{total_profit_rate:+.2f}%</div></div>
      <div class="summary-card"><div class="label">최대손실(2%)</div><div class="value" style="color:#e74c3c">{max_loss:,}원</div></div>
    </div>
    <div style="overflow-x:auto">
    <table>
      <tr>
        <th>종목명/섹터</th><th>현재가</th><th>등락률</th><th>평가손익</th>
        <th>RSI</th><th>MA신호</th><th>추천기법</th>
        <th>추가매수</th><th>방어매도</th>
        <th>🐢터틀익절</th><th>📊분할익절</th><th>📈ATR익절</th>
      </tr>
      {port_rows}
    </table>
    </div>
  </div>

  <!-- 스윙 추천 -->
  <div class="section">
    <div class="section-title">🎯 스윙 추천 TOP5 (유동성 점수 {liq_score}점 반영)</div>
    <div style="overflow-x:auto">
    <table>
      <tr><th>종목명/섹터</th><th>현재가</th><th>추천매수가</th><th>RSI</th><th>MA신호</th><th>터틀신호</th><th>추천투자금</th><th>근거</th></tr>
      {swing_rows}
    </table>
    </div>
  </div>

  <div class="footer">⚠️ 본 보고서는 참고용이며 투자 판단의 최종 책임은 본인에게 있습니다. | FRED + Google Sheets + Claude AI</div>
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
    holdings = load_holdings_from_sheets()
    token    = get_token()
    html     = build_report(token, holdings)
    with open("portfolio_report.html","w",encoding="utf-8") as f:
        f.write(html)
    print("✅ 보고서 저장 완료")
    today_str = dt.datetime.now(KST).strftime("%Y/%m/%d")
    send_email(f"📊 [{today_str}] 포트폴리오 보고서", html)
    print("✅ 완료!")

if __name__ == "__main__":
    main()


# =====================================================
# 탑다운 스크리너 연동 (sector_screener.py 필요)
# =====================================================
def get_topdown_picks(token, liquidity_score):
    """탑다운 방식으로 오늘 매수 후보 종목 발굴"""
    try:
        from sector_screener import run_topdown_screener, get_recommended_sectors, SECTORS
        results, rec_sectors, phase_msg = run_topdown_screener(token, liquidity_score)
        return results, rec_sectors, phase_msg
    except Exception as e:
        print(f"⚠️ 탑다운 스크리너 오류: {e}")
        return [], [], "-"

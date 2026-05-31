# predictions_saver.py
# 매일 추천 데이터를 predictions.csv에 저장
# portfolio_report.py 실행 후 자동으로 호출됨

import requests
import pandas as pd
import yfinance as yf
import json
import os
import datetime as dt

KST = dt.timezone(dt.timedelta(hours=9))

APP_KEY    = os.environ.get("APP_KEY", "")
APP_SECRET = os.environ.get("APP_SECRET", "")
TOKEN_FILE = "token.json"
PRED_FILE  = "predictions.csv"

TOTAL_ASSETS = 24_000_000

# 스윙 추천 후보
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

def get_kr_price(token, code):
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
        "content-type":"application/json",
        "authorization":f"Bearer {token}",
        "appkey":APP_KEY, "appsecret":APP_SECRET,
        "tr_id":"FHKST01010100",
    }
    try:
        res = requests.get(url, headers=headers,
            params={"FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":code}, timeout=10)
        output = res.json().get("output",{})
        return int(output.get("stck_prpr",0)), float(output.get("prdy_ctrt",0))
    except:
        return 0, 0

def get_vix():
    try:
        return round(yf.Ticker("^VIX").history(period="1d").dropna()["Close"].iloc[-1], 1)
    except:
        return 0

def get_rsi(code, period=14):
    try:
        hist = yf.Ticker(code+".KS").history(period="2mo").dropna()
        if len(hist) < period+1: return 50
        delta = hist["Close"].diff()
        gain  = delta.where(delta>0,0).rolling(period).mean()
        loss  = (-delta.where(delta<0,0)).rolling(period).mean()
        rs    = gain / loss
        return round((100-(100/(1+rs))).iloc[-1], 1)
    except:
        return 50

def get_ma_signal(code):
    try:
        hist  = yf.Ticker(code+".KS").history(period="4mo").dropna()
        if len(hist) < 60: return "데이터부족"
        ma20  = hist["Close"].rolling(20).mean().iloc[-1]
        ma60  = hist["Close"].rolling(60).mean().iloc[-1]
        curr  = hist["Close"].iloc[-1]
        if ma20 > ma60 and curr > ma20:   return "골든크로스"
        elif ma20 < ma60 and curr < ma20: return "데드크로스"
        elif curr > ma20 > ma60:          return "상승추세"
        elif curr < ma20:                 return "20일선하회"
        return "횡보"
    except:
        return "-"

def get_turtle_signal(code, price):
    try:
        hist   = yf.Ticker(code+".KS").history(period="2mo").dropna()
        if len(hist) < 20: return "-", 0, 0
        high20 = int(hist["High"].tail(20).max())
        low20  = int(hist["Low"].tail(20).min())
        if price >= high20:   sig = "매수신호"
        elif price <= low20:  sig = "매도신호"
        else:                 sig = "대기"
        return sig, high20, low20
    except:
        return "-", 0, 0

def get_season():
    month = dt.datetime.now(KST).month
    season_map = {
        1:"1월효과(강세)",2:"2월조정",3:"3월반등",4:"4월주의",
        5:"5월경고(약세)",6:"6월보합",7:"7월반등",8:"8월변동",
        9:"9월경고(약세)",10:"10월기회",11:"11월강세",12:"12월랠리"
    }
    return season_map.get(month, "보통")

def save_predictions():
    print("📊 추천 데이터 저장 중...")
    today     = dt.datetime.now(KST).strftime("%Y-%m-%d")
    vix       = get_vix()
    season    = get_season()
    token     = get_token()

    # 기존 데이터 로드
    if os.path.exists(PRED_FILE):
        df = pd.read_csv(PRED_FILE, encoding="utf-8-sig")
    else:
        df = pd.DataFrame()

    # 오늘 이미 저장됐으면 스킵
    if not df.empty and today in df["날짜"].values:
        print(f"✅ 오늘({today}) 데이터 이미 저장됨")
        return

    new_rows = []
    for code, name in SWING_CANDIDATES:
        price, rate = get_kr_price(token, code)
        if price == 0: continue

        rsi          = get_rsi(code)
        ma_sig       = get_ma_signal(code)
        turtle_sig, high20, low20 = get_turtle_signal(code, price)

        # 신호 점수 계산
        score = 0
        signals = []
        if rsi <= 35:           score+=1; signals.append(f"RSI과매도({rsi})")
        if "골든크로스" in ma_sig: score+=1; signals.append("골든크로스")
        if turtle_sig=="매수신호": score+=1; signals.append("터틀매수")
        if vix < 20:            score+=1; signals.append("VIX안정")

        # 추천 매수가 (현재가 -2%)
        rec_price = int(price * 0.98)

        new_rows.append({
            "날짜":          today,
            "종목명":        name,
            "종목코드":      code,
            "현재가":        price,
            "추천매수가":    rec_price,
            "등락률":        rate,
            "RSI":           rsi,
            "MA신호":        ma_sig,
            "터틀신호":      turtle_sig,
            "20캔들고점":    high20,
            "20캔들저점":    low20,
            "신호점수":      score,
            "신호목록":      ", ".join(signals) if signals else "없음",
            "VIX":           vix,
            "계절성":        season,
            # 결과 (나중에 업데이트)
            "1일후가격":     "",
            "1일후수익률":   "",
            "1일후진입여부": "",
            "1주후가격":     "",
            "1주후수익률":   "",
            "1달후가격":     "",
            "1달후수익률":   "",
            "종목타입":      "",  # A/B/C 타입 (피드백으로 결정)
            "메모":          "",
        })

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        df     = pd.concat([df, new_df], ignore_index=True) if not df.empty else new_df
        df.to_csv(PRED_FILE, index=False, encoding="utf-8-sig")
        print(f"✅ {len(new_rows)}개 추천 저장 완료 → {PRED_FILE}")
    else:
        print("⚠️ 저장할 데이터 없음")

if __name__ == "__main__":
    save_predictions()

# results_tracker.py
# 매일 실행 - 과거 추천 결과를 자동으로 업데이트
# 1일/1주/1달 후 실제 가격 조회 및 진입 가능성 분석

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
        "appkey":APP_KEY,"appsecret":APP_SECRET,
        "tr_id":"FHKST01010100",
    }
    try:
        res = requests.get(url, headers=headers,
            params={"FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":code}, timeout=10)
        output = res.json().get("output",{})
        return int(output.get("stck_prpr",0))
    except:
        return 0

def get_min_price_since(code, since_date):
    """추천일 이후 최저가 조회 (추천가 도달 여부 확인용)"""
    try:
        ticker = code + ".KS"
        t    = yf.Ticker(ticker)
        hist = t.history(start=since_date).dropna()
        if hist.empty: return 0
        return int(hist["Low"].min())
    except:
        return 0

def update_results():
    if not os.path.exists(PRED_FILE):
        print("⚠️ predictions.csv 없음")
        return

    df    = pd.read_csv(PRED_FILE, encoding="utf-8-sig")
    today = dt.datetime.now(KST).date()
    token = get_token()

    updated = 0

    for idx, row in df.iterrows():
        try:
            rec_date  = dt.datetime.strptime(str(row["날짜"]), "%Y-%m-%d").date()
            code      = str(row["종목코드"]).zfill(6)
            rec_price = int(row["추천매수가"]) if str(row["추천매수가"]).isdigit() else 0
            org_price = int(row["현재가"]) if str(row["현재가"]).isdigit() else 0
            days_past = (today - rec_date).days

            # 현재가 조회
            current_price = get_kr_price(token, code)
            if current_price == 0: continue

            # 추천가 도달 여부 확인
            if str(row["1일후진입여부"]) == "" or pd.isna(row["1일후진입여부"]):
                min_price = get_min_price_since(code, str(row["날짜"]))
                if rec_price > 0 and min_price > 0:
                    if min_price <= rec_price:
                        df.at[idx, "1일후진입여부"] = "✅ 진입가능"
                    else:
                        gap = round((min_price - rec_price) / rec_price * 100, 1)
                        df.at[idx, "1일후진입여부"] = f"❌ 미도달 (최저가-추천가: +{gap}%)"

            # 1일 후 결과
            if days_past >= 1 and (str(row["1일후가격"]) == "" or pd.isna(row["1일후가격"])):
                price_1d = get_kr_price(token, code)
                if price_1d > 0 and org_price > 0:
                    rate = round((price_1d - org_price) / org_price * 100, 2)
                    df.at[idx, "1일후가격"]   = price_1d
                    df.at[idx, "1일후수익률"] = rate
                    updated += 1
                    print(f"  ✅ {row['종목명']} 1일후: {price_1d:,}원 ({rate:+.2f}%)")

            # 1주 후 결과
            if days_past >= 7 and (str(row["1주후가격"]) == "" or pd.isna(row["1주후가격"])):
                price_1w = get_kr_price(token, code)
                if price_1w > 0 and org_price > 0:
                    rate = round((price_1w - org_price) / org_price * 100, 2)
                    df.at[idx, "1주후가격"]   = price_1w
                    df.at[idx, "1주후수익률"] = rate
                    updated += 1
                    print(f"  ✅ {row['종목명']} 1주후: {price_1w:,}원 ({rate:+.2f}%)")

            # 1달 후 결과
            if days_past >= 30 and (str(row["1달후가격"]) == "" or pd.isna(row["1달후가격"])):
                price_1m = get_kr_price(token, code)
                if price_1m > 0 and org_price > 0:
                    rate = round((price_1m - org_price) / org_price * 100, 2)
                    df.at[idx, "1달후가격"]   = price_1m
                    df.at[idx, "1달후수익률"] = rate

                    # 종목 타입 자동 분류
                    entry_ok = "진입가능" in str(row.get("1일후진입여부",""))
                    rate_1m  = rate

                    if not entry_ok and rate_1m >= 5:
                        df.at[idx, "종목타입"] = "B타입(돌파형)"
                        df.at[idx, "메모"] = f"눌림 안 왔는데 +{rate_1m}% → 추천가 -0.5%로 조정 권장"
                    elif entry_ok and rate_1m >= 3:
                        df.at[idx, "종목타입"] = "A타입(눌림형)"
                        df.at[idx, "메모"] = "추천가 전략 유효"
                    elif rate_1m < -5:
                        df.at[idx, "종목타입"] = "손절"
                        df.at[idx, "메모"] = f"손절 구간 ({rate_1m}%)"
                    else:
                        df.at[idx, "종목타입"] = "C타입(횡보형)"

                    updated += 1
                    print(f"  ✅ {row['종목명']} 1달후: {price_1m:,}원 ({rate:+.2f}%) → {df.at[idx,'종목타입']}")

        except Exception as e:
            print(f"  ⚠️ {row.get('종목명','?')} 오류: {e}")

    df.to_csv(PRED_FILE, index=False, encoding="utf-8-sig")
    print(f"\n✅ 결과 업데이트 완료: {updated}건")

if __name__ == "__main__":
    print("="*50)
    print("🔄 결과 추적 업데이트 시작")
    print("="*50)
    update_results()

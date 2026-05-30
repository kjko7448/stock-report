# scalper_pro.py
# 초단타 / 오버나잇 분석 프로그램 (풀버전)
# 포함 기법:
#   - 갭상 눌림 매수
#   - VWAP 돌파 매수
#   - 거래량 급증 + 전고점 돌파
#   - 트레일링 스탑 (-2%)
#   - MACD 데드크로스 청산
#   - 14:30 강제 청산 알림
#   - VIX 시장 환경 필터
#   - 공포/탐욕 지수
#   - 장단기 금리차
#   - 외국인/기관 수급
#   - 오버나잇 분석
#   - 내일 갭상 예측
#   - 심리 체크리스트
# pip install requests pandas beautifulsoup4 lxml yfinance

import sys
import time
import warnings
import requests
import pandas as pd
import yfinance as yf
import os
import smtplib
import datetime as dt
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")

KST = dt.timezone(dt.timedelta(hours=9))

# =====================================================
# ✅ 설정값
# =====================================================
GMAIL_ADDRESS      = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
RECEIVE_ADDRESS    = os.environ.get("RECEIVE_ADDRESS", "")

TOTAL_BUDGET  = 1_000_000
TOTAL_ASSETS  = 24_000_000
HEADERS       = {"User-Agent": "Mozilla/5.0"}
MARKETS       = {"KOSPI": 0, "KOSDAQ": 1}
EXCLUDE_WORDS = ["스팩", "리츠", "우", "우B"]

THEME_KEYWORDS = {
    "AI/반도체": ["AI", "반도체", "HBM", "칩", "한미", "이수", "티이엠씨", "네오셈", "가온", "원익", "코세스"],
    "전력/전기": ["전력", "전기", "일렉", "파워", "LS", "효성", "제룡", "변압기"],
    "통신/데이터센터": ["광통신", "통신", "네트워크", "대한광통신", "데이터센터"],
    "로봇": ["로봇", "자동화", "레인보우", "두산로보틱스"],
    "조선/해운": ["해운", "조선", "흥아", "한화오션", "HD현대"],
    "바이오": ["바이오", "제약", "셀트리온", "헬스"],
    "2차전지": ["배터리", "에코프로", "포스코", "엘앤에프", "천보"],
}

OPEN_PRICE, PREV_PRICE, PREV_TV = {}, {}, {}
HIGH_PRICE, LOW_PRICE = {}, {}

# =====================================================
# 유틸
# =====================================================
def num(x):
    try:
        return float(str(x).replace(",","").replace("%","").replace("+","").strip())
    except:
        return 0

def get_theme(name):
    found = []
    for theme, words in THEME_KEYWORDS.items():
        if any(w.lower() in name.lower() for w in words):
            found.append(theme)
    return ", ".join(found) if found else "일반"

# =====================================================
# 시장 환경 분석
# =====================================================
def get_macro():
    tickers = {
        "VIX":        "^VIX",
        "나스닥선물":  "NQ=F",
        "S&P선물":    "ES=F",
        "달러인덱스":  "DX-Y.NYB",
        "원달러환율":  "USDKRW=X",
        "미국10년금리": "^TNX",
        "미국2년금리":  "^IRX",
    }
    result = {}
    for name, sym in tickers.items():
        try:
            hist = yf.Ticker(sym).history(period="2d").dropna()
            if len(hist) >= 2:
                prev  = hist["Close"].iloc[-2]
                today = hist["Close"].iloc[-1]
                result[name] = {"가격": round(today,2), "등락률": round((today-prev)/prev*100,2)}
            else:
                result[name] = {"가격": 0, "등락률": 0}
        except:
            result[name] = {"가격": 0, "등락률": 0}
    return result

def get_vix_signal(macro):
    vix = macro.get("VIX",{}).get("가격",20)
    if vix >= 40:   return "🟢 극단적 공포 → 역발상 기회!", "#27ae60", vix
    elif vix >= 30: return "🔴 단타 완전 금지! 시장 공포 구간", "#e74c3c", vix
    elif vix >= 25: return "🟠 단타 자제, 보수적 매매", "#e67e22", vix
    elif vix >= 20: return "🟡 주의 구간, 리스크 관리", "#f39c12", vix
    else:           return "🟢 안정 구간, 적극 매매 가능", "#27ae60", vix

def get_fear_greed():
    try:
        vix = yf.Ticker("^VIX").history(period="1d").dropna()["Close"].iloc[-1]
        if vix >= 40:   return 10,  "극단적 공포"
        elif vix >= 30: return 25,  "공포"
        elif vix >= 20: return 50,  "중립"
        elif vix >= 15: return 70,  "탐욕"
        else:           return 85,  "극단적 탐욕"
    except:
        return 50, "중립"

def get_yield_curve(macro):
    try:
        y10  = macro.get("미국10년금리",{}).get("가격",0)
        y2   = macro.get("미국2년금리",{}).get("가격",0)
        diff = round(y10-y2,3)
        if diff < -0.5:   sig = "🔴 심각한 역전 (경기침체 위험)"
        elif diff < 0:    sig = "🟡 역전 (경기침체 주의)"
        elif diff < 0.5:  sig = "🟢 정상화 중"
        else:             sig = "🟢 정상 (경기 양호)"
        return diff, sig
    except:
        return 0, "-"

# =====================================================
# 시장 데이터 수집 (네이버 증권)
# =====================================================
def fetch_market(market, sosok, pages=6):
    rows = []
    for page in range(1, pages+1):
        url = f"https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={page}"
        try:
            r = requests.get(url, headers=HEADERS, verify=False, timeout=10)
            r.encoding = "euc-kr"
            soup = BeautifulSoup(r.text, "html.parser")
            for tr in soup.select("table.type_2 tr"):
                tds = tr.select("td")
                if len(tds) < 12: continue
                name_tag = tr.select_one("a.tltle")
                if not name_tag: continue
                v = [td.get_text(strip=True) for td in tds]
                name   = name_tag.get_text(strip=True)
                price  = num(v[2])
                rate   = num(v[4])
                volume = num(v[9])
                cap    = num(v[6])
                tv     = round(price*volume/100_000_000)
                rows.append({
                    "시장":market, "종목명":name,
                    "현재가":price, "등락률":rate,
                    "거래량":volume, "거래대금_억원":tv,
                    "시가총액":cap, "테마":get_theme(name),
                })
        except Exception as e:
            print(f"[오류] {market} page {page}: {e}")
    return pd.DataFrame(rows)

def collect_market():
    dfs = []
    for market, sosok in MARKETS.items():
        df = fetch_market(market, sosok)
        if not df.empty:
            dfs.append(df)
    if not dfs: return pd.DataFrame()
    df = pd.concat(dfs, ignore_index=True)
    df = df[
        (df["현재가"]>1000) & (df["등락률"]>0) &
        (df["거래량"]>0) &
        (~df["종목명"].apply(lambda x: any(w in x for w in EXCLUDE_WORDS)))
    ].copy()
    return df

# =====================================================
# 실시간 지표
# =====================================================
def realtime(row):
    name  = row["종목명"]
    price = row["현재가"]
    tv    = row["거래대금_억원"]

    if name not in OPEN_PRICE:
        OPEN_PRICE[name] = price
        HIGH_PRICE[name] = price
        LOW_PRICE[name]  = price

    HIGH_PRICE[name] = max(HIGH_PRICE.get(name,price), price)
    LOW_PRICE[name]  = min(LOW_PRICE.get(name,price), price)

    open_price = OPEN_PRICE[name]
    high = HIGH_PRICE[name]
    low  = LOW_PRICE[name]
    prev_price = PREV_PRICE.get(name, price)
    prev_tv    = PREV_TV.get(name, tv)

    price_1m = round((price-prev_price)/prev_price*100,2) if prev_price else 0
    tv_1m    = round(tv-prev_tv,1)
    open_gap = round((price-open_price)/open_price*100,2) if open_price else 0
    high_gap = round((price-high)/high*100,2) if high else 0
    low_reb  = round((price-low)/low*100,2) if low else 0

    PREV_PRICE[name] = price
    PREV_TV[name]    = tv

    open_status = ("시가이탈" if price<open_price
                   else "시초과열" if open_gap>=4
                   else "시가유지")
    tv_status = ("거래대금감소" if tv_1m<0
                 else "거래대금둔화" if tv_1m<30
                 else "거래대금증가" if tv_1m<100
                 else "거래대금급증")

    return pd.Series({
        "시가":open_price, "고가":high, "저가":low,
        "시가대비_%":open_gap, "고가대비_%":high_gap, "저가반등_%":low_reb,
        "1분가격변화_%":price_1m, "1분거래대금증가_억원":tv_1m,
        "시가상태":open_status, "거래대금상태":tv_status,
    })

# =====================================================
# VWAP 계산
# =====================================================
def calc_vwap(code):
    """VWAP 계산 (yfinance 1분봉)"""
    try:
        ticker = code + ".KS"
        t = yf.Ticker(ticker)
        hist = t.history(period="1d", interval="1m").dropna()
        if len(hist) < 5:
            return 0, "-"
        hist["TP"] = (hist["High"] + hist["Low"] + hist["Close"]) / 3
        hist["TPV"] = hist["TP"] * hist["Volume"]
        vwap = hist["TPV"].cumsum().iloc[-1] / hist["Volume"].cumsum().iloc[-1]
        current = hist["Close"].iloc[-1]
        if current > vwap:
            signal = f"🟢 VWAP 위 (강세) VWAP={int(vwap):,}원"
        else:
            signal = f"🔴 VWAP 아래 (약세) VWAP={int(vwap):,}원"
        return round(vwap), signal
    except:
        return 0, "-"

# =====================================================
# MACD 계산
# =====================================================
def calc_macd(code):
    """MACD 데드크로스 감지"""
    try:
        ticker = code + ".KS"
        hist = yf.Ticker(ticker).history(period="3mo").dropna()
        if len(hist) < 26:
            return "-", "#888"
        ema12 = hist["Close"].ewm(span=12).mean()
        ema26 = hist["Close"].ewm(span=26).mean()
        macd  = ema12 - ema26
        signal= macd.ewm(span=9).mean()
        hist_val = macd - signal

        if hist_val.iloc[-1] > 0 and hist_val.iloc[-2] <= 0:
            return "🟢 MACD 골든크로스 (매수)", "#27ae60"
        elif hist_val.iloc[-1] < 0 and hist_val.iloc[-2] >= 0:
            return "🔴 MACD 데드크로스 (청산!)", "#e74c3c"
        elif hist_val.iloc[-1] > 0:
            return "🟢 MACD 양호", "#27ae60"
        else:
            return "🟡 MACD 주의", "#f39c12"
    except:
        return "-", "#888"

# =====================================================
# 트레일링 스탑 계산
# =====================================================
def calc_trailing_stop(price, high_today):
    """고점 대비 -2% 트레일링 스탑"""
    if high_today <= 0:
        high_today = price
    stop = round(high_today * 0.98)
    if price <= stop:
        return f"⚠️ 트레일링 스탑 발동! ({stop:,}원 이탈)", "#e74c3c"
    else:
        gap = round((price - stop) / price * 100, 1)
        return f"손절선 {stop:,}원 (고점 대비 -2%, 현재까지 {gap}% 여유)", "#888"

# =====================================================
# 외국인/기관 수급
# =====================================================
def get_investor_flow(code):
    try:
        url = f"https://finance.naver.com/item/frgn.naver?code={code}"
        res = requests.get(url, headers=HEADERS, timeout=5)
        res.encoding = "euc-kr"
        soup = BeautifulSoup(res.text, "html.parser")
        rows = soup.select("table.type2 tr")
        if len(rows) >= 2:
            tds = rows[1].select("td")
            if len(tds) >= 5:
                foreign = tds[3].get_text(strip=True)
                inst    = tds[4].get_text(strip=True) if len(tds)>4 else "-"
                return foreign, inst
        return "-", "-"
    except:
        return "-", "-"

# =====================================================
# 점수 계산
# =====================================================
def base_score(row):
    s = 0
    rate   = row["등락률"]
    tv     = row["거래대금_억원"]
    volume = row["거래량"]
    cap    = row["시가총액"]

    if 2<=rate<=8:    s+=35
    elif 8<rate<=12:  s+=20
    elif 12<rate<=18: s+=5
    elif rate>18:     s-=35

    if tv>=1000:  s+=35
    elif tv>=500: s+=28
    elif tv>=300: s+=22
    elif tv>=100: s+=10
    else:         s-=20

    if volume>=5_000_000: s+=20
    elif volume>=1_000_000: s+=15
    elif volume>=300_000: s+=8

    if 3000<=cap<=50000: s+=15
    elif cap<1000:  s-=20
    elif cap>100000: s-=10

    if row["테마"]!="일반": s+=15
    return s

def pullback_score(row):
    score = 0
    if row["시가상태"]=="시가유지":      score+=20
    elif row["시가상태"]=="시가이탈":    score-=50
    elif row["시가상태"]=="시초과열":    score-=25

    if -2.5<=row["고가대비_%"]<=-0.3:   score+=20
    if 0.3<=row["저가반등_%"]<=3.0:     score+=20

    if 0<row["1분가격변화_%"]<=2.5:     score+=20
    elif row["1분가격변화_%"]>=4:        score-=20
    elif row["1분가격변화_%"]<-2:        score-=20

    if row["1분거래대금증가_억원"]>=100: score+=20
    elif row["1분거래대금증가_억원"]>=30: score+=10
    elif row["1분거래대금증가_억원"]<0:  score-=20
    return score

# =====================================================
# 매매 신호
# =====================================================
def signal(row):
    rate    = row["등락률"]
    tv      = row["거래대금_억원"]
    open_st = row["시가상태"]
    tv_st   = row["거래대금상태"]
    pull    = row["눌림패턴점수"]
    total   = row["실전점수"]

    if open_st=="시가이탈":                                return "매수금지"
    if rate>=18 or open_st=="시초과열":                    return "추격금지"
    if tv_st in ["거래대금감소","거래대금둔화"] and pull<40: return "관망"
    if 2<=rate<=8 and tv>=300 and pull>=60:                return "눌림후재상승"
    if 2<=rate<=8 and tv>=300 and pull>=30:                return "눌림대기"
    if 8<rate<=12 and tv>=300 and total>=100:              return "돌파매수"
    return "관망"

def make_plan(price):
    half = TOTAL_BUDGET//2
    buy1 = round(price*0.985)
    buy2 = round(price*1.005)
    stop = round(price*0.970)
    tgt1 = round(price*1.030)
    tgt2 = round(price*1.060)
    return pd.Series({
        "눌림매수가":buy1, "눌림수량":int(half//buy1) if buy1 else 0,
        "돌파매수가":buy2, "돌파수량":int(half//buy2) if buy2 else 0,
        "손절가":stop, "1차익절":tgt1, "2차익절":tgt2,
    })

def exit_rule(sig):
    rules = {
        "눌림후재상승": "진입가능 | 1차(+3%) 절반, 2차(+6%) 전량 | 14:30 강제청산",
        "눌림대기":     "예약매수 가능, 09:10 미체결 취소",
        "돌파매수":     "돌파 후 눌림 확인, 실패 시 즉시 손절",
        "매수금지":     "⛔ 진입금지",
        "추격금지":     "🚫 추격금지",
    }
    return rules.get(sig, "관망")

def priority_tag(row):
    sig   = row["실전신호"]
    total = row["실전점수"]
    tv    = row["거래대금_억원"]
    if sig=="눌림후재상승" and total>=120 and tv>=500: return "🔥 1순위"
    if sig in ["눌림후재상승","돌파매수"] and total>=100: return "⭐ 2순위"
    if sig=="눌림대기" and total>=80: return "👀 관찰"
    if sig in ["매수금지","추격금지"]: return "⛔ 제외"
    return "➖ 대기"

# =====================================================
# 오버나잇 분석
# =====================================================
def overnight_score(row):
    score = 0
    rate  = row["등락률"]
    tv    = row["거래대금_억원"]
    theme = row["테마"]
    sig   = row.get("실전신호","")

    if 3<=rate<=12:  score+=20
    elif rate>18:    score-=25
    elif rate<1:     score-=10

    if tv>=1000:  score+=25
    elif tv>=500: score+=18
    elif tv>=300: score+=10

    if theme!="일반":                             score+=20
    if sig in ["눌림후재상승","돌파매수"]:         score+=15
    elif sig in ["매수금지","추격금지"]:           score-=20
    if row["시가총액"]>=3000:                     score+=10
    return score

def overnight_tag(score):
    if score>=75: return "✅ 오버나잇 가능"
    if score>=55: return "⚠️ 일부만 홀딩"
    if score>=35: return "🔄 당일청산 권장"
    return "❌ 오버나잇 금지"

# =====================================================
# 갭상 가능성
# =====================================================
def gap_up_prob(row, futures):
    score   = 0
    nq_rate = futures.get("나스닥선물",{}).get("등락률",0)
    sp_rate = futures.get("S&P선물",{}).get("등락률",0)

    if nq_rate>0.5: score+=20
    if sp_rate>0.5: score+=10
    if row["등락률"]>=5:   score+=25
    elif row["등락률"]>=2: score+=15
    if row["거래대금_억원"]>=1000: score+=25
    elif row["거래대금_억원"]>=500: score+=15
    if row["테마"]!="일반": score+=15

    if score>=75: return "🔥 갭상 유력"
    if score>=55: return "⭐ 갭상 가능"
    if score>=35: return "➖ 중립"
    return "📉 갭하 주의"

# =====================================================
# 14:30 강제 청산 알림
# =====================================================
def get_force_close_alert():
    now  = dt.datetime.now(KST)
    hour = now.hour
    minute = now.minute
    if hour==14 and minute>=20:
        return "🚨 14:30 강제 청산 10분 전! 미익절 포지션 즉시 정리하세요!", "#e74c3c"
    elif hour==14 and minute>=0:
        return "⚠️ 14시 경과! 30분 후 강제 청산. 익절 준비하세요.", "#f39c12"
    elif hour==13:
        return "🕐 13시대, 1시간 후 청산 준비 시작", "#888"
    return "", ""

# =====================================================
# 심리 체크리스트
# =====================================================
def get_psychology_checklist(vix_val, fg_val):
    checks = []
    if vix_val>=30:
        checks.append("🔴 VIX 30 이상 — 단타 금지! 시장이 너무 불안정해요")
    if fg_val>=75:
        checks.append("🔴 극단적 탐욕 구간 — FOMO 매수 절대 금지! 고점일 수 있어요")
    elif fg_val<=25:
        checks.append("🟢 극단적 공포 구간 — 역발상 매수 기회, 냉정하게 분석하세요")
    checks.append("✂️ 손절 신호 나왔을 때 즉시 실행하고 있는가?")
    checks.append("💰 1차 +3% 익절, 2차 +6% 익절 규칙을 지키고 있는가?")
    checks.append("⏰ 14:30 이전 당일청산 원칙을 지키고 있는가?")
    checks.append("🚫 추격금지 종목에 추격 매수하지 않고 있는가?")
    checks.append("📊 오늘 매매는 2% 룰 안에서 이루어지고 있는가?")
    return checks

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
            print("✅ 이메일 전송 완료!")
    except Exception as e:
        print(f"❌ 이메일 전송 실패: {e}")

# =====================================================
# 장마감 후 리포트
# =====================================================
def after_report():
    print("📊 장마감 후 데이터 수집 중...")
    df = collect_market()
    if df.empty:
        print("데이터 없음")
        return

    print("🌍 거시경제 수집 중...")
    macro = get_macro()
    vix_signal, vix_color, vix_val = get_vix_signal(macro)
    fg_val, fg_text = get_fear_greed()
    yield_diff, yield_signal = get_yield_curve(macro)
    futures = {k:v for k,v in macro.items() if "선물" in k or "달러" in k}

    df["실전신호"]     = "장마감분석"
    df["오버나잇점수"] = df.apply(overnight_score, axis=1)
    df["오버나잇판단"] = df["오버나잇점수"].apply(overnight_tag)
    df["갭상가능성"]   = df.apply(lambda r: gap_up_prob(r, macro), axis=1)

    df["익일_관찰가"]    = df["현재가"]
    df["익일_추격금지선"] = df["현재가"].apply(lambda x: round(x*1.04))
    df["익일_눌림관찰가"] = df["현재가"].apply(lambda x: round(x*0.985))
    df["익일_손절기준"]  = df["현재가"].apply(lambda x: round(x*0.97))

    df = df.sort_values(["오버나잇점수","거래대금_억원"], ascending=False)
    top30 = df.head(30)

    tomorrow  = (dt.datetime.now(KST)+dt.timedelta(days=1)).strftime("%m/%d")
    today_str = dt.datetime.now(KST).strftime("%Y/%m/%d %H:%M")

    gap_top      = top30[top30["갭상가능성"].str.contains("유력|가능")].head(5)
    overnight_ok = top30[top30["오버나잇판단"].str.contains("가능")].head(5)
    overnight_no = top30[top30["오버나잇판단"].str.contains("당일청산|금지")].head(5)

    # 심리 체크리스트
    psych_checks = get_psychology_checklist(vix_val, fg_val)
    psych_html   = "".join([f"<li style='margin-bottom:6px'>{c}</li>" for c in psych_checks])

    # 거시경제 HTML
    macro_rows = ""
    for name, val in macro.items():
        color = "#e74c3c" if val["등락률"]<0 else "#27ae60"
        emoji = "🔴" if val["등락률"]<0 else "🟢"
        macro_rows += f"<tr><td>{name}</td><td>{val['가격']:,}</td><td style='color:{color}'>{emoji} {val['등락률']:+.2f}%</td></tr>"

    def make_rows(sub_df):
        rows = ""
        for _, r in sub_df.iterrows():
            rows += f"""
            <tr>
                <td><b>{r['종목명']}</b></td>
                <td>{r['테마']}</td>
                <td>{r['현재가']:,}원</td>
                <td>{r['등락률']:+.1f}%</td>
                <td>{r['거래대금_억원']:,.0f}억</td>
                <td>{r.get('갭상가능성','-')}</td>
                <td>{r['오버나잇판단']}</td>
                <td style='color:#2980b9'>{r['익일_관찰가']:,}원</td>
                <td style='color:#27ae60'>{r['익일_눌림관찰가']:,}원</td>
                <td style='color:#e74c3c'>{r['익일_손절기준']:,}원</td>
                <td style='color:#e74c3c'>{r['익일_추격금지선']:,}원</td>
            </tr>"""
        return rows

    fg_color = "#e74c3c" if fg_val>=70 else "#27ae60" if fg_val<=30 else "#f39c12"

    html = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
  body{{font-family:'Malgun Gothic',sans-serif;background:#f5f7fa;margin:0;padding:20px;color:#333}}
  .container{{max-width:1200px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.1)}}
  .header{{background:linear-gradient(135deg,#0d0d1a,#1a1a3e,#2d1b69);color:white;padding:28px;text-align:center}}
  .header h1{{margin:0;font-size:22px;letter-spacing:2px}}
  .section{{padding:20px;border-bottom:1px solid #eee}}
  .section-title{{font-size:15px;font-weight:bold;color:#1a1a2e;margin-bottom:14px;padding-left:10px;border-left:4px solid #2d1b69}}
  table{{width:100%;border-collapse:collapse;font-size:12px}}
  th{{background:#2d1b69;color:white;padding:9px 7px;text-align:center}}
  td{{padding:8px 7px;text-align:center;border-bottom:1px solid #f0f0f0}}
  tr:hover{{background:#f8f0ff}}
  .grid-3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:16px}}
  .card{{background:#f8f9ff;border-radius:10px;padding:16px;border:1px solid #e0e4f0}}
  .card .label{{font-size:12px;color:#888;margin-bottom:6px}}
  .card .value{{font-size:16px;font-weight:bold}}
  .strategy-box{{background:#fff9e6;border:1px solid #f0c040;border-radius:8px;padding:16px;font-size:13px;line-height:1.8}}
  .psych-box{{background:#f0f8ff;border:1px solid #3498db;border-radius:8px;padding:16px}}
  .footer{{background:#f8f9ff;padding:14px;text-align:center;font-size:11px;color:#999}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>⚡ 단타 오버나잇 리포트 (풀버전)</h1>
    <p>{today_str} 기준 | 내일({tomorrow}) 전략</p>
  </div>

  <!-- 시장 환경 -->
  <div class="section">
    <div class="section-title">🌡️ 오늘의 시장 환경</div>
    <div class="grid-3">
      <div class="card">
        <div class="label">VIX 시장 필터</div>
        <div class="value" style="color:{vix_color};font-size:13px">{vix_signal}</div>
        <div style="font-size:20px;font-weight:bold;color:{vix_color}">{vix_val}</div>
      </div>
      <div class="card">
        <div class="label">😱 공포/탐욕 지수</div>
        <div class="value" style="color:{fg_color}">{fg_val} — {fg_text}</div>
        <div style="font-size:12px;color:#666;margin-top:4px">
          {'🟢 역발상 매수 기회' if fg_val<=25 else '🔴 탐욕 과열 주의' if fg_val>=75 else '🟡 중립'}
        </div>
      </div>
      <div class="card">
        <div class="label">📉 장단기 금리차</div>
        <div class="value">{yield_diff:+.3f}%</div>
        <div style="font-size:12px;color:#666;margin-top:4px">{yield_signal}</div>
      </div>
    </div>
    <table>
      <tr><th>지표</th><th>현재가</th><th>등락률</th></tr>
      {macro_rows}
    </table>
  </div>

  <!-- 갭상 후보 -->
  <div class="section">
    <div class="section-title">🔥 내일 갭상 가능성 높은 종목</div>
    <table>
      <tr><th>종목명</th><th>테마</th><th>현재가</th><th>등락률</th><th>거래대금</th><th>갭상전망</th><th>오버나잇</th><th>익일관찰가</th><th>눌림관찰가</th><th>손절기준</th><th>추격금지선</th></tr>
      {make_rows(gap_top)}
    </table>
  </div>

  <!-- 오버나잇 가능 -->
  <div class="section">
    <div class="section-title">✅ 오버나잇 가능 종목</div>
    <table>
      <tr><th>종목명</th><th>테마</th><th>현재가</th><th>등락률</th><th>거래대금</th><th>갭상전망</th><th>오버나잇</th><th>익일관찰가</th><th>눌림관찰가</th><th>손절기준</th><th>추격금지선</th></tr>
      {make_rows(overnight_ok)}
    </table>
  </div>

  <!-- 당일청산 권장 -->
  <div class="section">
    <div class="section-title">⚠️ 당일청산 / 오버나잇 금지</div>
    <table>
      <tr><th>종목명</th><th>테마</th><th>현재가</th><th>등락률</th><th>거래대금</th><th>갭상전망</th><th>오버나잇</th><th>익일관찰가</th><th>눌림관찰가</th><th>손절기준</th><th>추격금지선</th></tr>
      {make_rows(overnight_no)}
    </table>
  </div>

  <!-- 내일 아침 전략 -->
  <div class="section">
    <div class="section-title">📋 내일 아침 전략 요약</div>
    <div class="strategy-box">
      🕘 <b>09:00~09:05</b>: 시초가 확인 — 갭상 여부 체크<br>
      🕘 <b>09:05~09:10</b>: 시가 유지 종목만 진입 검토 (시가이탈 즉시 제외)<br>
      🕘 <b>09:10 이후</b>: VWAP 확인 → VWAP 위에 있는 종목만 매수 검토<br>
      📊 <b>거래량 확인</b>: 평균의 3배 이상 터지는 종목 우선 주목<br>
      🚫 <b>추격금지</b>: 시초 +4% 이상 갭상 → 눌림 올 때까지 대기<br>
      ✂️ <b>손절원칙</b>: 매수가 대비 -3% 무조건 손절<br>
      📈 <b>트레일링스탑</b>: 고점 대비 -2% 이탈 시 청산<br>
      💰 <b>익절원칙</b>: 1차 +3% 절반 익절, 2차 +6% 전량 익절<br>
      ⏰ <b>강제청산</b>: 14:30 이전 미익절 포지션 무조건 정리<br>
      📉 <b>MACD 확인</b>: 데드크로스 발생 시 즉시 청산
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
    ⚠️ 본 보고서는 참고용입니다. 투자 판단의 최종 책임은 본인에게 있습니다.<br>
    적용 기법: 갭상눌림 | VWAP돌파 | 거래량급증 | 트레일링스탑 | MACD | 14:30강제청산 | VIX필터 | 공포탐욕 | 장단기금리차
  </div>
</div>
</body>
</html>
"""
    send_email(f"⚡ [{tomorrow}] 단타 오버나잇 전략 리포트 (풀버전)", html)
    with open("scalper_report.html","w",encoding="utf-8") as f:
        f.write(html)
    print("✅ 리포트 저장 완료!")
    print(top30[["종목명","테마","현재가","등락률","거래대금_억원","갭상가능성","오버나잇판단"]].to_string(index=False))

# =====================================================
# 장중 실시간 스캔
# =====================================================
def morning_scan():
    # 14:30 강제 청산 알림
    force_alert, force_color = get_force_close_alert()
    if force_alert:
        print(f"\n{'='*50}")
        print(force_alert)
        print('='*50)

    df = collect_market()
    if df.empty:
        print("데이터 없음")
        return

    df = df.sort_values(["거래대금_억원","등락률"], ascending=False).head(100)
    rt = df.apply(realtime, axis=1)
    df = pd.concat([df,rt], axis=1)

    df["기본점수"]     = df.apply(base_score, axis=1)
    df["눌림패턴점수"] = df.apply(pullback_score, axis=1)
    df["실전점수"]     = df["기본점수"]+df["눌림패턴점수"]
    df["실전신호"]     = df.apply(signal, axis=1)

    plan = df["현재가"].apply(make_plan)
    df   = pd.concat([df,plan], axis=1)

    df["매도규칙"]     = df["실전신호"].apply(exit_rule)
    df["진입우선순위"] = df.apply(priority_tag, axis=1)
    df = df.sort_values(["실전점수","거래대금_억원"], ascending=False)

    out = df.head(30)
    out.to_csv("scalper_morning.csv", index=False, encoding="utf-8-sig")

    print("\n"+"="*120)
    print(f"⚡ 단타 스캔: {dt.datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*120)
    print(out[["진입우선순위","종목명","테마","현재가","등락률","거래대금_억원","실전신호","손절가","1차익절","2차익절"]].to_string(index=False))

# =====================================================
# 메인
# =====================================================
if __name__ == "__main__":
    mode = sys.argv[1].lower() if len(sys.argv)>=2 else "after"
    if mode=="morning":
        print("⚡ 단타 실시간 스캔 시작 (Ctrl+C로 종료)")
        while True:
            morning_scan()
            time.sleep(60)
    else:
        after_report()

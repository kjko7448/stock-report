# portfolio_report.py
# 포트폴리오 중심 일일 보고서 생성기 (터틀 트레이딩 신호 포함)
# pip install requests pandas yfinance
#
# 실행: python portfolio_report.py

import requests
import pandas as pd
import yfinance as yf
import json
import os
import datetime as dt
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

KST = dt.timezone(dt.timedelta(hours=9))

# =====================================================
# ✅ 설정값 (GitHub Secrets에서 자동으로 읽어옴)
# =====================================================
APP_KEY            = os.environ.get("APP_KEY", "")
APP_SECRET         = os.environ.get("APP_SECRET", "")
ACCOUNT_NO         = os.environ.get("ACCOUNT_NO", "")
ACCOUNT_CODE       = "01"
GMAIL_ADDRESS      = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
RECEIVE_ADDRESS    = os.environ.get("RECEIVE_ADDRESS", "")
TOKEN_FILE         = "token.json"

# =====================================================
# 총 자산 (터틀 2% 룰 계산용)
# =====================================================
TOTAL_ASSETS = 24_000_000  # 2,400만원 (주식 2000 + 현금 400)

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
}

def get_theme(name):
    for theme, words in THEME_KEYWORDS.items():
        if any(w.lower() in name.lower() for w in words):
            return theme
    return "일반"

# =====================================================
# 토큰 관리
# =====================================================
def get_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
        if data.get("issued_at") == dt.datetime.now(KST).strftime("%Y-%m-%d"):
            print("✅ 기존 토큰 재사용")
            return data["access_token"]
    print("🔄 토큰 새로 발급 중...")
    url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    res = requests.post(url, headers=headers, data=json.dumps(body))
    token_data = res.json()
    token_data["issued_at"] = dt.datetime.now(KST).strftime("%Y-%m-%d")
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f)
    print("✅ 토큰 발급 완료")
    return token_data["access_token"]

# =====================================================
# 국내주식 현재가 조회
# =====================================================
def get_kr_price(token, code):
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKST01010100",
    }
    params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code}
    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        data = res.json()
        output = data.get("output", {})
        price  = int(output.get("stck_prpr", 0))
        rate   = float(output.get("prdy_ctrt", 0))
        volume = int(output.get("acml_vol", 0))
        high52 = int(output.get("w52_hgpr", 0))
        low52  = int(output.get("w52_lwpr", 0))
        return price, rate, volume, high52, low52
    except Exception as e:
        print(f"  ⚠️ {code} 조회 실패: {e}")
        return 0, 0, 0, 0, 0

# =====================================================
# 해외주식 현재가 조회
# =====================================================
def get_us_price(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        price_usd = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        rate      = info.get("regularMarketChangePercent", 0)
        high52    = info.get("fiftyTwoWeekHigh", 0)
        low52     = info.get("fiftyTwoWeekLow", 0)
        fx        = yf.Ticker("USDKRW=X").info.get("regularMarketPrice", 1380)
        price_krw = int(price_usd * fx)
        return price_usd, price_krw, rate, high52, low52, fx
    except Exception as e:
        print(f"  ⚠️ {ticker} 조회 실패: {e}")
        return 0, 0, 0, 0, 0, 1380

# =====================================================
# 거시 경제 데이터
# =====================================================
def get_macro():
    tickers = {
        "S&P500":        "^GSPC",
        "나스닥":         "^IXIC",
        "다우":           "^DJI",
        "VIX(공포지수)":  "^VIX",
        "달러인덱스":     "DX-Y.NYB",
        "원달러환율":     "USDKRW=X",
        "WTI유가":        "CL=F",
        "금":             "GC=F",
    }
    result = {}
    for name, sym in tickers.items():
        try:
            t    = yf.Ticker(sym)
            hist = t.history(period="2d").dropna()
            if len(hist) >= 2:
                prev  = hist["Close"].iloc[-2]
                today = hist["Close"].iloc[-1]
                rate  = (today - prev) / prev * 100
                result[name] = {"가격": round(today, 2), "등락률": round(rate, 2)}
            else:
                result[name] = {"가격": 0, "등락률": 0}
        except:
            result[name] = {"가격": 0, "등락률": 0}
    return result

# =====================================================
# 매매 신호 계산
# =====================================================
def calc_signals(avg, current, high52, low52):
    if current == 0:
        return "-", "-", "-"
    profit_rate = (current - avg) / avg * 100
    if current <= avg * 0.95:
        if low52 > 0 and current <= low52 * 1.10:
            add_buy = f"{int(current * 0.97):,}원 (강력추가)"
        else:
            add_buy = f"{int(current * 0.97):,}원 (분할추가)"
    else:
        add_buy = "-"
    if current <= avg * 0.92:
        def_sell = f"{int(avg * 0.92):,}원 ⚠️ 손절검토"
    elif current <= avg * 0.97:
        def_sell = f"{int(avg * 0.95):,}원 (방어)"
    else:
        def_sell = "-"
    if profit_rate >= 8:
        profit_sell = f"1차 {int(avg * 1.10):,}원 / 2차 {int(avg * 1.20):,}원"
    else:
        profit_sell = f"목표 {int(avg * 1.10):,}원 ({round(10 - profit_rate, 1)}% 남음)"
    return add_buy, def_sell, profit_sell

# =====================================================
# 터틀 트레이딩 신호 (20캔들 기준)
# =====================================================
def get_turtle_signal(code, current_price, total_assets=TOTAL_ASSETS):
    try:
        ticker = code + ".KS"
        t = yf.Ticker(ticker)
        hist = t.history(period="2mo").dropna()

        if len(hist) < 20:
            return "-", "-", "-", "-", "-"

        recent  = hist.tail(20)
        high20  = int(recent["High"].max())
        low20   = int(recent["Low"].min())
        current = current_price if current_price > 0 else int(hist["Close"].iloc[-1])

        # 터틀 신호 판단
        if current >= high20:
            signal     = "🔴 매수신호 (신고가 돌파)"
            signal_color = "#e74c3c"
        elif current <= low20:
            signal     = "🔵 매도신호 (신저가 이탈)"
            signal_color = "#2980b9"
        else:
            gap_to_high = round((high20 - current) / current * 100, 1)
            signal      = f"⏳ 대기 (신고가까지 {gap_to_high}%)"
            signal_color = "#888"

        # 2% 손절가 계산
        max_loss     = total_assets * 0.02
        loss_pct     = (current - low20) / current * 100 if current > low20 else 1
        recommended  = int(max_loss / (loss_pct / 100)) if loss_pct > 0 else 0
        stop_2pct    = int(current - max_loss / max(1, recommended / current)) if recommended > 0 else low20

        return (
            signal,
            signal_color,
            f"{high20:,}원",
            f"{low20:,}원",
            f"{recommended:,}원"
        )
    except Exception as e:
        return "-", "#888", "-", "-", "-"

# =====================================================
# 스윙 추천 종목 (터틀 신호 포함)
# =====================================================
def get_swing_picks(token):
    picks = []
    for code, name in SWING_CANDIDATES:
        price, rate, volume, high52, low52 = get_kr_price(token, code)
        if price == 0:
            continue

        score  = 0
        reason = []

        if low52 > 0:
            low_gap = (price - low52) / low52 * 100
            if low_gap <= 30:
                score += 20
                reason.append("52주 저가 근접")

        if high52 > 0:
            high_gap = (price - high52) / high52 * 100
            if -20 <= high_gap <= -5:
                score += 20
                reason.append("고점 대비 눌림")

        if 1 <= rate <= 5:
            score += 20
            reason.append("안정적 상승")
        elif rate > 5:
            score += 10
            reason.append("강한 상승")
        elif -3 <= rate < 0:
            score += 5
            reason.append("소폭 하락 (매수 기회)")

        if volume >= 1_000_000:
            score += 20
            reason.append("거래량 풍부")
        elif volume >= 500_000:
            score += 10
            reason.append("거래량 양호")

        theme = get_theme(name)
        if theme != "일반":
            score += 20
            reason.append(f"{theme} 테마")

        # 터틀 신호 추가
        turtle_sig, turtle_color, high20, low20, rec_buy = get_turtle_signal(code, price)

        picks.append({
            "종목명":      name,
            "현재가":      price,
            "추천매수가":  int(price * 0.98),
            "추천주수":    max(1, int(1_000_000 // (price * 0.98))),
            "점수":        score,
            "근거":        ", ".join(reason) if reason else "기본 관찰",
            "기간":        "1~2주 스윙",
            "터틀신호":    turtle_sig,
            "터틀색상":    turtle_color,
            "20캔들고점":  high20,
            "20캔들저점":  low20,
            "추천투자금":  rec_buy,
        })

    picks = sorted(picks, key=lambda x: x["점수"], reverse=True)
    return picks[:5]

# =====================================================
# 이메일 전송
# =====================================================
def send_email(subject, html_body):
    msg = MIMEMultipart()
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = RECEIVE_ADDRESS
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
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

    print("🌍 거시경제 데이터 수집 중...")
    macro = get_macro()

    print("💼 포트폴리오 데이터 수집 중...")
    portfolio_rows = []
    total_invest   = 0
    total_current  = 0

    for code, name, qty, avg, market in HOLDINGS:
        print(f"  → {name} 조회 중...")
        if market in ("KR", "ETF_KR"):
            price, rate, volume, high52, low52 = get_kr_price(token, code)
            price_display = f"{price:,}원" if price else "-"
        else:
            price_usd, price, rate, high52, low52, fx = get_us_price(code)
            price_display = f"${price_usd:,.2f} (≈{price:,}원)" if price else "-"

        invest      = avg * qty
        current_val = price * qty if price else 0
        profit      = current_val - invest
        profit_rate = (price - avg) / avg * 100 if (avg > 0 and price > 0) else 0
        total_invest  += invest
        total_current += current_val if price else invest

        add_buy, def_sell, profit_sell = calc_signals(avg, price, high52, low52)
        rate_color   = "#e74c3c" if rate < 0 else "#27ae60"
        profit_color = "#e74c3c" if profit < 0 else "#27ae60"

        portfolio_rows.append({
            "name": name, "market": market, "qty": qty, "avg": avg,
            "price": price, "price_display": price_display,
            "rate": rate, "profit": profit, "profit_rate": profit_rate,
            "add_buy": add_buy, "def_sell": def_sell, "profit_sell": profit_sell,
            "rate_color": rate_color, "profit_color": profit_color,
        })

    print("🎯 스윙 추천 종목 분석 중 (터틀 신호 포함)...")
    swing_picks = get_swing_picks(token)

    total_profit      = total_current - total_invest
    total_profit_rate = (total_profit / total_invest * 100) if total_invest > 0 else 0
    total_color       = "#e74c3c" if total_profit < 0 else "#27ae60"
    max_loss_per_trade = int(TOTAL_ASSETS * 0.02)

    # 거시경제 행
    macro_rows = ""
    for name, val in macro.items():
        emoji = "🔴" if val["등락률"] < 0 else "🟢"
        color = "#e74c3c" if val["등락률"] < 0 else "#27ae60"
        macro_rows += f"<tr><td>{name}</td><td>{val['가격']:,}</td><td style='color:{color}'>{emoji} {val['등락률']:+.2f}%</td></tr>"

    # 포트폴리오 행
    port_rows = ""
    for r in portfolio_rows:
        port_rows += f"""
        <tr>
            <td><b>{r['name']}</b><br><small style="color:#999">{r['market']}</small></td>
            <td>{r['qty']:,}주</td>
            <td>{r['avg']:,}원</td>
            <td>{r['price_display']}</td>
            <td style="color:{r['rate_color']}">{r['rate']:+.2f}%</td>
            <td style="color:{r['profit_color']}">{r['profit']:+,.0f}원<br>({r['profit_rate']:+.1f}%)</td>
            <td style="color:#2980b9;font-size:12px">{r['add_buy']}</td>
            <td style="color:#e67e22;font-size:12px">{r['def_sell']}</td>
            <td style="color:#8e44ad;font-size:12px">{r['profit_sell']}</td>
        </tr>"""

    # 스윙 추천 행 (터틀 신호 포함)
    swing_rows = ""
    for i, p in enumerate(swing_picks, 1):
        swing_rows += f"""
        <tr>
            <td><b>{i}. {p['종목명']}</b></td>
            <td>{p['현재가']:,}원</td>
            <td style="color:#2980b9"><b>{p['추천매수가']:,}원</b></td>
            <td>{p['추천주수']:,}주</td>
            <td>{p['기간']}</td>
            <td style="font-size:12px">{p['근거']}</td>
            <td style="color:{p['터틀색상']};font-weight:bold;font-size:12px">{p['터틀신호']}</td>
            <td style="color:#e74c3c;font-size:12px">{p['20캔들고점']}</td>
            <td style="color:#2980b9;font-size:12px">{p['20캔들저점']}</td>
            <td style="color:#27ae60;font-size:12px">{p['추천투자금']}</td>
        </tr>"""

    html = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body {{ font-family: 'Malgun Gothic', sans-serif; background:#f5f7fa; color:#333; margin:0; padding:20px; }}
  .container {{ max-width:1200px; margin:0 auto; background:white; border-radius:12px; overflow:hidden; box-shadow:0 4px 20px rgba(0,0,0,0.1); }}
  .header {{ background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460); color:white; padding:30px; text-align:center; }}
  .header h1 {{ margin:0; font-size:24px; letter-spacing:2px; }}
  .header p {{ margin:8px 0 0; opacity:0.8; font-size:14px; }}
  .section {{ padding:24px; border-bottom:1px solid #eee; }}
  .section-title {{ font-size:16px; font-weight:bold; color:#1a1a2e; margin-bottom:16px; padding-left:10px; border-left:4px solid #0f3460; }}
  table {{ width:100%; border-collapse:collapse; font-size:12px; }}
  th {{ background:#1a1a2e; color:white; padding:10px 8px; text-align:center; }}
  td {{ padding:9px 8px; text-align:center; border-bottom:1px solid #f0f0f0; vertical-align:middle; }}
  tr:hover {{ background:#f8f9ff; }}
  .summary-box {{ display:flex; gap:16px; margin-bottom:16px; flex-wrap:wrap; }}
  .summary-card {{ flex:1; min-width:140px; background:#f8f9ff; border-radius:10px; padding:16px; text-align:center; border:1px solid #e0e4f0; }}
  .summary-card .label {{ font-size:12px; color:#888; margin-bottom:6px; }}
  .summary-card .value {{ font-size:18px; font-weight:bold; }}
  .turtle-box {{ background:#fff9e6; border:1px solid #f0c040; border-radius:8px; padding:14px; margin-bottom:16px; font-size:13px; line-height:1.8; }}
  .footer {{ background:#f8f9ff; padding:16px; text-align:center; font-size:12px; color:#999; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📊 포트폴리오 일일 보고서</h1>
    <p>{today} 기준</p>
  </div>

  <!-- 거시경제 -->
  <div class="section">
    <div class="section-title">🌍 글로벌 시장 흐름 (전일 마감 기준)</div>
    <table><tr><th>지표</th><th>가격</th><th>등락률</th></tr>{macro_rows}</table>
  </div>

  <!-- 포트폴리오 -->
  <div class="section">
    <div class="section-title">💼 내 포트폴리오 현황</div>
    <div class="summary-box">
      <div class="summary-card"><div class="label">총 투자금</div><div class="value">{total_invest:,.0f}원</div></div>
      <div class="summary-card"><div class="label">현재 평가금</div><div class="value">{total_current:,.0f}원</div></div>
      <div class="summary-card"><div class="label">평가 손익</div><div class="value" style="color:{total_color}">{total_profit:+,.0f}원</div></div>
      <div class="summary-card"><div class="label">수익률</div><div class="value" style="color:{total_color}">{total_profit_rate:+.2f}%</div></div>
      <div class="summary-card"><div class="label">터틀 1회 최대손실(2%)</div><div class="value" style="color:#e74c3c">{max_loss_per_trade:,}원</div></div>
    </div>
    <table>
      <tr>
        <th>종목명</th><th>수량</th><th>평단가</th><th>현재가</th>
        <th>등락률</th><th>평가손익</th>
        <th>추가매수</th><th>방어매도</th><th>익절매도</th>
      </tr>
      {port_rows}
    </table>
  </div>

  <!-- 스윙 추천 + 터틀 신호 -->
  <div class="section">
    <div class="section-title">🎯 스윙 추천 TOP5 + 터틀 트레이딩 신호</div>
    <div class="turtle-box">
      🐢 <b>터틀 트레이딩 핵심 원칙</b><br>
      📈 <b>매수</b>: 20캔들 신고가 돌파 시 진입 (1번 신호 우선)<br>
      📉 <b>매도</b>: 20캔들 신저가 이탈 시 전량 청산<br>
      ✂️ <b>손절</b>: 계좌 전체 -2% ({max_loss_per_trade:,}원) 도달 시 즉시 손절<br>
      💰 <b>투자금</b>: 추천투자금은 2% 룰 기준 종목별 최적 투자금액
    </div>
    <table>
      <tr>
        <th>종목명</th><th>현재가</th><th>추천매수가</th><th>추천주수</th>
        <th>기간</th><th>근거</th>
        <th>터틀신호</th><th>20캔들고점</th><th>20캔들저점(손절)</th><th>추천투자금</th>
      </tr>
      {swing_rows}
    </table>
  </div>

  <div class="footer">
    ⚠️ 본 보고서는 참고용이며 투자 판단의 최종 책임은 본인에게 있습니다.<br>
    터틀 트레이딩 기법 적용 | 자동 생성: portfolio_report.py
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
    print("="*50)
    print("📊 포트폴리오 일일 보고서 생성 시작")
    print("="*50)
    token = get_token()
    html  = build_report(token)
    with open("portfolio_report.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✅ 보고서 저장 완료")
    today_str = dt.datetime.now(KST).strftime("%Y/%m/%d")
    print("📧 이메일 전송 중...")
    send_email(f"📊 [{today_str}] 포트폴리오 일일 보고서", html)
    print("="*50)
    print("✅ 완료!")

if __name__ == "__main__":
    main()

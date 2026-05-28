# premarket_report.py
# 장 시작 전 준비 리포트 (오전 8:30)
# pip install requests pandas yfinance beautifulsoup4 lxml

import requests
import pandas as pd
import yfinance as yf
import os
import smtplib
import datetime as dt
KST = dt.timezone(dt.timedelta(hours=9))
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup
import warnings
warnings.filterwarnings("ignore")

# =====================================================
# ✅ 설정값 (GitHub Secrets에서 자동으로 읽어옴)
# =====================================================
GMAIL_ADDRESS      = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
RECEIVE_ADDRESS    = os.environ.get("RECEIVE_ADDRESS", "")

HEADERS = {"User-Agent": "Mozilla/5.0"}

# =====================================================
# 미국 시장 마감 데이터
# =====================================================
def get_us_market():
    tickers = {
        "S&P500":      "^GSPC",
        "나스닥":       "^IXIC",
        "다우":         "^DJI",
        "VIX(공포지수)":"^VIX",
        "나스닥선물":   "NQ=F",
        "S&P선물":      "ES=F",
        "달러인덱스":   "DX-Y.NYB",
        "원달러환율":   "USDKRW=X",
        "WTI유가":      "CL=F",
        "금":           "GC=F",
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
# 어제 상한가 / 급등 종목
# =====================================================
def get_top_gainers():
    rows = []
    for sosok in [0, 1]:
        url = f"https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page=1"
        try:
            r = requests.get(url, headers=HEADERS, verify=False, timeout=10)
            r.encoding = "euc-kr"
            soup = BeautifulSoup(r.text, "html.parser")
            for tr in soup.select("table.type_2 tr"):
                tds = tr.select("td")
                if len(tds) < 12:
                    continue
                name_tag = tr.select_one("a.tltle")
                if not name_tag:
                    continue
                v      = [td.get_text(strip=True) for td in tds]
                name   = name_tag.get_text(strip=True)
                price  = v[2]
                rate   = v[4]
                volume = v[9]
                tv     = v[10] if len(v) > 10 else "-"
                try:
                    rate_f = float(rate.replace(",","").replace("%","").replace("+",""))
                except:
                    rate_f = 0
                if rate_f >= 5:
                    rows.append({
                        "종목명": name,
                        "현재가": price,
                        "등락률": rate,
                        "거래량": volume,
                        "등락률_수치": rate_f,
                    })
        except Exception as e:
            print(f"오류: {e}")

    rows = sorted(rows, key=lambda x: x["등락률_수치"], reverse=True)
    return rows[:10]

# =====================================================
# 오늘 갭상 예상 종목 (전일 급등 + 미국 선물 긍정적)
# =====================================================
def get_gap_up_candidates(gainers, us_market):
    nq_rate = us_market.get("나스닥선물", {}).get("등락률", 0)
    sp_rate = us_market.get("S&P선물", {}).get("등락률", 0)
    us_positive = nq_rate > 0 and sp_rate > 0

    candidates = []
    for r in gainers[:10]:
        score = 0
        try:
            rate_f = r["등락률_수치"]
            if rate_f >= 10:   score += 30
            elif rate_f >= 5:  score += 20

            if us_positive:    score += 30

        except:
            pass

        if score >= 30:
            candidates.append({
                "종목명":   r["종목명"],
                "전일등락률": r["등락률"],
                "현재가":   r["현재가"],
                "갭상전망": "🔥 갭상 유력" if score >= 50 else "⭐ 갭상 가능",
                "주의사항": "추격금지 / 눌림 확인 후 진입",
            })

    return candidates[:5]

# =====================================================
# 오늘 경제 지표 일정 (고정 안내)
# =====================================================
def get_today_schedule():
    today = dt.datetime.now()
    weekday = today.weekday()
    schedules = [
        "📌 매주 수요일 밤 11:30 — 미국 EIA 원유재고",
        "📌 매주 목요일 밤 9:30 — 미국 신규실업수당청구건수",
        "📌 매월 첫째주 금요일 밤 9:30 — 미국 비농업고용지수(NFP)",
        "📌 매월 셋째주 화요일 밤 9:30 — 미국 CPI(소비자물가지수)",
        "📌 매월 FOMC 회의 결과 — 미국 기준금리 결정",
    ]
    return schedules

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
def build_report():
    today_str = dt.datetime.now().strftime("%Y년 %m월 %d일")
    now_str   = dt.datetime.now().strftime("%H:%M")

    print("🌍 미국 시장 데이터 수집 중...")
    us_market = get_us_market()

    print("📈 급등 종목 수집 중...")
    gainers = get_top_gainers()

    print("🔥 갭상 후보 분석 중...")
    gap_candidates = get_gap_up_candidates(gainers, us_market)

    schedules = get_today_schedule()

    # 미국 시장 HTML
    us_rows = ""
    for name, val in us_market.items():
        color = "#27ae60" if val["등락률"] >= 0 else "#e74c3c"
        emoji = "🟢" if val["등락률"] >= 0 else "🔴"
        us_rows += f"""
        <tr>
            <td>{name}</td>
            <td>{val['가격']:,}</td>
            <td style="color:{color}">{emoji} {val['등락률']:+.2f}%</td>
        </tr>"""

    # 급등 종목 HTML
    gainer_rows = ""
    for r in gainers:
        color = "#e74c3c" if "+" in str(r['등락률']) else "#27ae60"
        gainer_rows += f"""
        <tr>
            <td><b>{r['종목명']}</b></td>
            <td>{r['현재가']}</td>
            <td style="color:{color}">{r['등락률']}</td>
            <td>{r['거래량']}</td>
        </tr>"""

    # 갭상 후보 HTML
    gap_rows = ""
    for r in gap_candidates:
        gap_rows += f"""
        <tr>
            <td><b>{r['종목명']}</b></td>
            <td>{r['전일등락률']}</td>
            <td>{r['현재가']}</td>
            <td>{r['갭상전망']}</td>
            <td style="color:#e67e22;font-size:12px">{r['주의사항']}</td>
        </tr>"""

    if not gap_rows:
        gap_rows = "<tr><td colspan='5' style='color:#999'>미국 선물 흐름 부정적 — 갭상 후보 없음</td></tr>"

    # 일정 HTML
    schedule_html = ""
    for s in schedules:
        schedule_html += f"<li style='margin-bottom:8px'>{s}</li>"

    # 나스닥 등락률로 오늘 시장 전망
    nq_rate = us_market.get("나스닥선물", {}).get("등락률", 0)
    if nq_rate >= 1:
        outlook = "🟢 강세 예상 — 갭상 종목 눌림 후 진입 기회"
        outlook_color = "#27ae60"
    elif nq_rate >= 0:
        outlook = "🟡 보합 예상 — 종목별 대응, 추격 자제"
        outlook_color = "#f39c12"
    else:
        outlook = "🔴 약세 예상 — 신규 진입 자제, 보유 종목 방어"
        outlook_color = "#e74c3c"

    html = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body {{ font-family: 'Malgun Gothic', sans-serif; background:#f5f7fa; color:#333; margin:0; padding:20px; }}
  .container {{ max-width:900px; margin:0 auto; background:white; border-radius:12px; overflow:hidden; box-shadow:0 4px 20px rgba(0,0,0,0.1); }}
  .header {{ background:linear-gradient(135deg,#0a0a1a,#1a2a1a,#0a2a0a); color:white; padding:28px; text-align:center; }}
  .header h1 {{ margin:0; font-size:22px; letter-spacing:2px; }}
  .header p {{ margin:8px 0 0; opacity:0.8; font-size:14px; }}
  .section {{ padding:22px; border-bottom:1px solid #eee; }}
  .section-title {{ font-size:15px; font-weight:bold; color:#1a1a2e; margin-bottom:14px; padding-left:10px; border-left:4px solid #0a2a0a; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ background:#1a2a1a; color:white; padding:9px 7px; text-align:center; }}
  td {{ padding:8px 7px; text-align:center; border-bottom:1px solid #f0f0f0; }}
  tr:hover {{ background:#f0fff0; }}
  .outlook-box {{ background:#f0fff0; border:1px solid #27ae60; border-radius:8px; padding:16px; text-align:center; font-size:16px; font-weight:bold; margin-bottom:12px; }}
  .strategy-box {{ background:#fff9e6; border:1px solid #f0c040; border-radius:8px; padding:16px; font-size:13px; line-height:1.8; }}
  .footer {{ background:#f8f9ff; padding:14px; text-align:center; font-size:11px; color:#999; }}
  ul {{ margin:0; padding-left:20px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🌅 장 시작 전 준비 리포트</h1>
    <p>{today_str} {now_str} 기준</p>
  </div>

  <!-- 오늘 시장 전망 -->
  <div class="section">
    <div class="section-title">📊 오늘 한국 시장 전망</div>
    <div class="outlook-box" style="color:{outlook_color}">{outlook}</div>
  </div>

  <!-- 미국 시장 마감 -->
  <div class="section">
    <div class="section-title">🌍 미국 시장 마감 현황</div>
    <table>
      <tr><th>지표</th><th>가격</th><th>등락률</th></tr>
      {us_rows}
    </table>
  </div>

  <!-- 전일 급등 종목 -->
  <div class="section">
    <div class="section-title">🔥 전일 급등 종목 TOP10 (등락률 5% 이상)</div>
    <table>
      <tr><th>종목명</th><th>현재가</th><th>등락률</th><th>거래량</th></tr>
      {gainer_rows}
    </table>
  </div>

  <!-- 갭상 후보 -->
  <div class="section">
    <div class="section-title">⚡ 오늘 갭상 예상 후보</div>
    <table>
      <tr><th>종목명</th><th>전일등락률</th><th>전일종가</th><th>갭상전망</th><th>주의사항</th></tr>
      {gap_rows}
    </table>
  </div>

  <!-- 오늘 전략 -->
  <div class="section">
    <div class="section-title">📋 오늘 장 시작 전략</div>
    <div class="strategy-box">
      🕘 <b>09:00 ~ 09:05</b>: 시초가 확인 — 갭상/갭하 여부 체크<br>
      🕘 <b>09:05 ~ 09:10</b>: 시가 유지 종목만 진입 검토<br>
      🚫 <b>추격금지</b>: 시초 +4% 이상 갭상 종목 — 눌림 올 때까지 대기<br>
      ✂️ <b>손절원칙</b>: 매수가 대비 -3% 무조건 손절<br>
      💰 <b>익절원칙</b>: 1차 +3% 절반, 2차 +6% 전량<br>
      ⏰ <b>당일청산</b>: 14:30 이전 미익절 포지션 정리
    </div>
  </div>

  <!-- 주요 경제 일정 -->
  <div class="section">
    <div class="section-title">📅 주요 경제 지표 일정</div>
    <ul>{schedule_html}</ul>
  </div>

  <div class="footer">
    ⚠️ 본 보고서는 참고용이며 투자 판단의 최종 책임은 본인에게 있습니다.<br>
    자동 생성: premarket_report.py
  </div>
</div>
</body>
</html>
"""
    return html

# =====================================================
# 메인
# =====================================================
def main():
    print("="*50)
    print("🌅 장 시작 전 준비 리포트 생성 시작")
    print("="*50)

    html = build_report()

    with open("premarket_report.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✅ 보고서 저장 완료: premarket_report.html")

    today_str = dt.datetime.now().strftime("%Y/%m/%d")
    print("📧 이메일 전송 중...")
    send_email(f"🌅 [{today_str}] 장 시작 전 준비 리포트", html)
    print("="*50)
    print("✅ 완료!")

if __name__ == "__main__":
    main()

# premarket_report.py
# 장 시작 전 준비 리포트 (풀버전)
# 포함 기법:
#   - VIX 시장 환경 필터
#   - 공포/탐욕 지수
#   - 장단기 금리차 (경기침체 신호)
#   - 계절성 알림
#   - 섹터 로테이션
#   - 외국인/기관 수급
#   - 전일 급등 종목 분석
#   - 갭상 예상 후보
#   - VWAP/MACD 신호
#   - 오늘 전략 요약
#   - 심리 체크리스트
# pip install requests pandas yfinance beautifulsoup4 lxml

import requests
import pandas as pd
import yfinance as yf
import os
import smtplib
import datetime as dt
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup
import warnings
warnings.filterwarnings("ignore")

KST = dt.timezone(dt.timedelta(hours=9))

# =====================================================
# ✅ 설정값
# =====================================================
GMAIL_ADDRESS      = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
RECEIVE_ADDRESS    = os.environ.get("RECEIVE_ADDRESS", "")

HEADERS = {"User-Agent": "Mozilla/5.0"}

# =====================================================
# 거시경제 데이터
# =====================================================
def get_macro():
    tickers = {
        "S&P500":       "^GSPC",
        "나스닥":        "^IXIC",
        "다우":          "^DJI",
        "VIX(공포지수)": "^VIX",
        "나스닥선물":    "NQ=F",
        "S&P선물":       "ES=F",
        "달러인덱스":    "DX-Y.NYB",
        "원달러환율":    "USDKRW=X",
        "WTI유가":       "CL=F",
        "금":            "GC=F",
        "미국10년금리":  "^TNX",
        "미국2년금리":   "^IRX",
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

# =====================================================
# VIX 시장 환경 필터
# =====================================================
def get_vix_signal(macro):
    vix = macro.get("VIX(공포지수)",{}).get("가격",20)
    if vix >= 40:   return "🟢 극단적 공포 → 역발상 매수 기회!", "#27ae60", vix, "단타 가능 (역발상)"
    elif vix >= 30: return "🔴 공포 구간 → 단타 완전 금지!", "#e74c3c", vix, "단타 금지"
    elif vix >= 25: return "🟠 불안 구간 → 보수적 매매 권장", "#e67e22", vix, "소극적 단타"
    elif vix >= 20: return "🟡 주의 구간 → 리스크 관리 강화", "#f39c12", vix, "신중한 단타"
    else:           return "🟢 안정 구간 → 적극적 매매 가능", "#27ae60", vix, "적극적 단타"

# =====================================================
# 공포/탐욕 지수
# =====================================================
def get_fear_greed(vix_val):
    if vix_val >= 40:   return 10, "극단적 공포", "#e74c3c"
    elif vix_val >= 30: return 25, "공포", "#e67e22"
    elif vix_val >= 20: return 50, "중립", "#f39c12"
    elif vix_val >= 15: return 70, "탐욕", "#27ae60"
    else:               return 85, "극단적 탐욕", "#e74c3c"

# =====================================================
# 장단기 금리차
# =====================================================
def get_yield_curve(macro):
    try:
        y10  = macro.get("미국10년금리",{}).get("가격",0)
        y2   = macro.get("미국2년금리",{}).get("가격",0)
        diff = round(y10-y2, 3)
        if diff < -0.5:   sig,col = "🔴 심각한 역전 (경기침체 위험!)", "#e74c3c"
        elif diff < 0:    sig,col = "🟡 역전 (경기침체 주의)", "#f39c12"
        elif diff < 0.5:  sig,col = "🟢 정상화 중", "#27ae60"
        else:             sig,col = "🟢 정상 (경기 양호)", "#27ae60"
        return diff, sig, col
    except:
        return 0, "-", "#888"

# =====================================================
# 계절성 알림
# =====================================================
def get_seasonality():
    month = dt.datetime.now(KST).month
    season_map = {
        1:  ("🟢 1월 효과", "역사적으로 상승 확률 높음. 신규 자금 유입 시기. 공격적 매매 가능!", "#27ae60"),
        2:  ("🟡 2월 조정", "1월 랠리 후 조정 구간. 선별적 매매 권장.", "#f39c12"),
        3:  ("🟢 3월 반등", "분기말 기관 매수. 기술적 반등 가능성 높음.", "#27ae60"),
        4:  ("🟡 4월 주의", "실적 시즌 변동성 확대. 눌림매수 기회 탐색.", "#f39c12"),
        5:  ("🔴 5월 경고!", "Sell in May! 5~10월 역사적 약세 구간 시작. 비중 축소 고려!", "#e74c3c"),
        6:  ("🟡 6월 보합", "여름 거래 감소. 방어적 포지션 권장.", "#f39c12"),
        7:  ("🟢 7월 반등", "여름 랠리 가능성. 실적 호조 종목 주목.", "#27ae60"),
        8:  ("🟡 8월 변동", "변동성 확대 구간. 리스크 관리 강화.", "#f39c12"),
        9:  ("🔴 9월 경고!", "역사적으로 최악의 달! 비중 최소화 강력 권장.", "#e74c3c"),
        10: ("🟢 10월 기회", "역사적 바닥 구간. 역발상 매수 기회. 저점 분할 매수!", "#27ae60"),
        11: ("🟢 11월 강세", "산타랠리 준비 시작. 공격적 매매 가능.", "#27ae60"),
        12: ("🟢 12월 랠리", "산타랠리! 연말 기관 매수. 상승 확률 높음.", "#27ae60"),
    }
    return season_map.get(month, ("🟡 보통", "특별한 계절성 없음", "#888"))

# =====================================================
# 섹터 로테이션
# =====================================================
def get_sector_rotation():
    sectors = {
        "기술(XLK)":     "XLK",
        "금융(XLF)":     "XLF",
        "헬스케어(XLV)":  "XLV",
        "에너지(XLE)":   "XLE",
        "산업재(XLI)":   "XLI",
        "소재(XLB)":     "XLB",
        "유틸리티(XLU)":  "XLU",
        "필수소비재(XLP)": "XLP",
    }
    result = []
    for name, ticker in sectors.items():
        try:
            hist = yf.Ticker(ticker).history(period="5d").dropna()
            if len(hist) >= 2:
                rate = (hist["Close"].iloc[-1]-hist["Close"].iloc[0])/hist["Close"].iloc[0]*100
                result.append({"섹터": name, "5일수익률": round(rate,2)})
        except:
            pass
    return sorted(result, key=lambda x: x["5일수익률"], reverse=True)

# =====================================================
# 전일 급등 종목 수집
# =====================================================
def get_top_gainers():
    rows = []
    for sosok in [0, 1]:
        market = "KOSPI" if sosok==0 else "KOSDAQ"
        url = f"https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page=1"
        try:
            r = requests.get(url, headers=HEADERS, verify=False, timeout=10)
            r.encoding = "euc-kr"
            soup = BeautifulSoup(r.text, "html.parser")
            for tr in soup.select("table.type_2 tr"):
                tds = tr.select("td")
                if len(tds) < 12: continue
                name_tag = tr.select_one("a.tltle")
                if not name_tag: continue
                v     = [td.get_text(strip=True) for td in tds]
                name  = name_tag.get_text(strip=True)
                price = v[2]
                rate  = v[4]
                vol   = v[9]
                cap   = v[6]
                try:
                    rate_f = float(rate.replace(",","").replace("%","").replace("+",""))
                    price_f = float(price.replace(",",""))
                    vol_f   = float(vol.replace(",",""))
                    cap_f   = float(cap.replace(",",""))
                except:
                    rate_f = price_f = vol_f = cap_f = 0
                if rate_f >= 5:
                    rows.append({
                        "시장": market,
                        "종목명": name,
                        "현재가": price,
                        "등락률": rate,
                        "거래량": vol,
                        "시가총액": cap,
                        "등락률_수치": rate_f,
                        "가격_수치": price_f,
                        "거래량_수치": vol_f,
                        "시총_수치": cap_f,
                    })
        except Exception as e:
            print(f"오류: {e}")
    return sorted(rows, key=lambda x: x["등락률_수치"], reverse=True)[:15]

# =====================================================
# 갭상 예상 후보 분석
# =====================================================
def get_gap_up_candidates(gainers, macro):
    nq_rate = macro.get("나스닥선물",{}).get("등락률",0)
    sp_rate = macro.get("S&P선물",{}).get("등락률",0)
    us_positive = nq_rate > 0 and sp_rate > 0

    candidates = []
    for r in gainers[:10]:
        score = 0
        reason = []

        rate_f = r["등락률_수치"]
        if rate_f >= 15:   score+=30; reason.append("상한가급 급등")
        elif rate_f >= 10: score+=20; reason.append("강한 급등")
        elif rate_f >= 5:  score+=10; reason.append("급등")

        if us_positive:
            score+=30
            reason.append(f"미국선물 강세(나스닥{nq_rate:+.1f}%)")
        elif nq_rate < 0:
            score-=15
            reason.append("미국선물 약세 주의")

        if r["시총_수치"] >= 3000:
            score+=10; reason.append("대형주")
        elif r["시총_수치"] < 500:
            score-=5; reason.append("소형주(변동성 주의)")

        if score >= 50:   gap = "🔥 갭상 유력"
        elif score >= 30: gap = "⭐ 갭상 가능"
        elif score >= 10: gap = "➖ 중립"
        else:             gap = "📉 갭하 주의"

        candidates.append({
            "종목명":   r["종목명"],
            "시장":     r["시장"],
            "전일등락률": r["등락률"],
            "전일종가": r["현재가"],
            "갭상전망": gap,
            "근거":     ", ".join(reason),
            "주의":     "추격금지 / 눌림 확인 후 진입",
        })

    return sorted(candidates, key=lambda x: ("유력" in x["갭상전망"], "가능" in x["갭상전망"]), reverse=True)[:7]

# =====================================================
# 외국인/기관 수급 (상위 종목)
# =====================================================
def get_top_investor_flow():
    try:
        url = "https://finance.naver.com/sise/frgn_rank.naver"
        res = requests.get(url, headers=HEADERS, timeout=8)
        res.encoding = "euc-kr"
        soup = BeautifulSoup(res.text, "html.parser")
        rows = []
        for tr in soup.select("table.type_2 tr"):
            tds = tr.select("td")
            if len(tds) < 8: continue
            name_tag = tr.select_one("a.tltle") or tr.select_one("td a")
            if not name_tag: continue
            v = [td.get_text(strip=True) for td in tds]
            rows.append({
                "종목명": name_tag.get_text(strip=True),
                "현재가": v[1] if len(v)>1 else "-",
                "등락률": v[2] if len(v)>2 else "-",
                "외국인순매수": v[4] if len(v)>4 else "-",
            })
        return rows[:5]
    except:
        return []

# =====================================================
# 오늘 경제 지표 일정
# =====================================================
def get_today_schedule():
    weekday = dt.datetime.now(KST).weekday()
    schedules = []
    if weekday == 1:  # 화요일
        schedules.append("📌 미국 CPI 발표 가능 (매월 둘째주 화요일)")
    if weekday == 2:  # 수요일
        schedules.append("📌 미국 EIA 원유재고 (매주 수요일 밤 11:30)")
    if weekday == 3:  # 목요일
        schedules.append("📌 미국 신규실업수당청구건수 (매주 목요일 밤 9:30)")
    schedules.append("📌 FOMC 회의 결과 — 기준금리 결정 (연 8회)")
    schedules.append("📌 미국 고용지표(NFP) — 매월 첫째주 금요일 밤 9:30")
    return schedules

# =====================================================
# 오늘 시장 전망 종합
# =====================================================
def get_market_outlook(macro, vix_val, fg_val, yield_diff):
    nq_rate = macro.get("나스닥선물",{}).get("등락률",0)
    sp_rate = macro.get("S&P선물",{}).get("등락률",0)

    score = 0
    reasons = []

    # 미국 선물
    if nq_rate > 0.5:   score+=2; reasons.append(f"나스닥선물 강세({nq_rate:+.1f}%)")
    elif nq_rate < -0.5: score-=2; reasons.append(f"나스닥선물 약세({nq_rate:+.1f}%)")
    if sp_rate > 0.5:   score+=1
    elif sp_rate < -0.5: score-=1

    # VIX
    if vix_val < 15:    score+=2; reasons.append("VIX 안정")
    elif vix_val >= 30: score-=3; reasons.append("VIX 공포 구간")
    elif vix_val >= 25: score-=1

    # 공포/탐욕
    if fg_val <= 25:    score+=1; reasons.append("극단적 공포(역발상)")
    elif fg_val >= 75:  score-=1; reasons.append("극단적 탐욕(주의)")

    # 금리차
    if yield_diff < -0.5: score-=1; reasons.append("금리차 역전")

    if score >= 3:
        return "🟢 강세 예상", "#27ae60", ", ".join(reasons), "갭상 종목 눌림 후 진입 기회"
    elif score >= 1:
        return "🟢 약한 강세", "#27ae60", ", ".join(reasons), "선별적 매수 가능"
    elif score <= -3:
        return "🔴 약세 예상", "#e74c3c", ", ".join(reasons), "신규 진입 자제, 보유 종목 방어"
    elif score <= -1:
        return "🟡 약한 약세", "#f39c12", ", ".join(reasons), "보수적 접근, 종목별 대응"
    else:
        return "🟡 보합 예상", "#f39c12", ", ".join(reasons), "종목별 대응, 추격 자제"

# =====================================================
# 심리 체크리스트
# =====================================================
def get_psychology_checklist(vix_val, fg_val, season_title):
    checks = []
    if vix_val >= 30:
        checks.append("🔴 VIX 30 이상 — 오늘 단타 금지! 시장이 너무 불안정해요")
    if fg_val >= 75:
        checks.append("🔴 극단적 탐욕 — FOMO 매수 절대 금지! 고점일 가능성 높아요")
    elif fg_val <= 25:
        checks.append("🟢 극단적 공포 — 역발상 기회! 냉정하게 저점 분할 매수 검토")
    if "경고" in season_title or "5월" in season_title or "9월" in season_title:
        checks.append(f"⚠️ {season_title} — 계절적 약세 구간! 비중 관리 필수")
    checks.append("💭 오늘 매매는 감이 아닌 신호를 따르고 있는가?")
    checks.append("✂️ 손절 신호 나오면 즉시 실행할 준비가 되어있는가?")
    checks.append("⏰ 14:30 강제 청산 원칙을 지킬 것인가?")
    checks.append("📊 포지션 사이징은 2% 룰 안에서 이루어지고 있는가?")
    checks.append("🚫 추격금지 종목에 추격 매수하지 않을 것인가?")
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
            print("✅ 이메일 전송 성공!")
    except Exception as e:
        print(f"❌ 이메일 전송 실패: {e}")

# =====================================================
# HTML 보고서 생성
# =====================================================
def build_report():
    today_str = dt.datetime.now(KST).strftime("%Y년 %m월 %d일")
    now_str   = dt.datetime.now(KST).strftime("%H:%M")

    print("🌍 거시경제 수집 중...")
    macro = get_macro()

    vix_signal, vix_color, vix_val, day_strategy = get_vix_signal(macro)
    fg_val, fg_text, fg_color = get_fear_greed(vix_val)
    yield_diff, yield_signal, yield_color = get_yield_curve(macro)

    print("📅 계절성 분석 중...")
    season_title, season_desc, season_color = get_seasonality()

    print("🔄 섹터 로테이션 수집 중...")
    sectors = get_sector_rotation()

    print("📈 전일 급등 종목 수집 중...")
    gainers = get_top_gainers()

    print("🔥 갭상 후보 분석 중...")
    gap_candidates = get_gap_up_candidates(gainers, macro)

    print("💼 외국인 순매수 수집 중...")
    investor_flows = get_top_investor_flow()

    print("📋 오늘 전략 분석 중...")
    outlook_title, outlook_color, outlook_reason, outlook_action = get_market_outlook(macro, vix_val, fg_val, yield_diff)

    schedules = get_today_schedule()
    psych_checks = get_psychology_checklist(vix_val, fg_val, season_title)

    # ── HTML 조립 ──
    macro_rows = ""
    for name, val in macro.items():
        if name in ("미국10년금리","미국2년금리"): continue
        color = "#e74c3c" if val["등락률"]<0 else "#27ae60"
        emoji = "🔴" if val["등락률"]<0 else "🟢"
        macro_rows += f"<tr><td>{name}</td><td>{val['가격']:,}</td><td style='color:{color}'>{emoji} {val['등락률']:+.2f}%</td></tr>"

    sector_rows = ""
    for i, s in enumerate(sectors):
        color = "#e74c3c" if s["5일수익률"]<0 else "#27ae60"
        rank  = "🥇" if i==0 else "🥈" if i==1 else "🥉" if i==2 else ""
        sector_rows += f"<tr><td>{rank} <b>{s['섹터']}</b></td><td style='color:{color}'>{s['5일수익률']:+.2f}%</td></tr>"

    gainer_rows = ""
    for r in gainers[:10]:
        color = "#e74c3c" if "+" in str(r['등락률']) else "#27ae60"
        gainer_rows += f"""
        <tr>
            <td><b>{r['종목명']}</b></td>
            <td><small>{r['시장']}</small></td>
            <td>{r['현재가']}</td>
            <td style='color:{color}'><b>{r['등락률']}</b></td>
            <td>{r['거래량']}</td>
            <td>{r['시가총액']}</td>
        </tr>"""

    gap_rows = ""
    for r in gap_candidates:
        gap_color = "#e74c3c" if "유력" in r["갭상전망"] else "#f39c12" if "가능" in r["갭상전망"] else "#888"
        gap_rows += f"""
        <tr>
            <td><b>{r['종목명']}</b></td>
            <td><small>{r['시장']}</small></td>
            <td>{r['전일등락률']}</td>
            <td>{r['전일종가']}</td>
            <td style='color:{gap_color};font-weight:bold'>{r['갭상전망']}</td>
            <td style='font-size:11px'>{r['근거']}</td>
            <td style='color:#e67e22;font-size:11px'>{r['주의']}</td>
        </tr>"""

    if not gap_rows:
        gap_rows = "<tr><td colspan='7' style='color:#999'>미국 선물 흐름 부정적 — 갭상 후보 없음</td></tr>"

    investor_rows = ""
    for r in investor_flows:
        investor_rows += f"<tr><td><b>{r['종목명']}</b></td><td>{r['현재가']}</td><td>{r['등락률']}</td><td style='color:#27ae60'>{r['외국인순매수']}</td></tr>"
    if not investor_rows:
        investor_rows = "<tr><td colspan='4' style='color:#999'>데이터 없음</td></tr>"

    schedule_html = "".join([f"<li style='margin-bottom:6px'>{s}</li>" for s in schedules])
    psych_html    = "".join([f"<li style='margin-bottom:6px'>{c}</li>" for c in psych_checks])

    html = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
  body{{font-family:'Malgun Gothic',sans-serif;background:#f5f7fa;color:#333;margin:0;padding:20px}}
  .container{{max-width:1200px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.1)}}
  .header{{background:linear-gradient(135deg,#0a0a1a,#1a2a1a,#0a2a0a);color:white;padding:28px;text-align:center}}
  .header h1{{margin:0;font-size:22px;letter-spacing:2px}}
  .header p{{margin:8px 0 0;opacity:0.8;font-size:14px}}
  .section{{padding:20px;border-bottom:1px solid #eee}}
  .section-title{{font-size:15px;font-weight:bold;color:#1a1a2e;margin-bottom:14px;padding-left:10px;border-left:4px solid #0a2a0a}}
  table{{width:100%;border-collapse:collapse;font-size:12px}}
  th{{background:#1a2a1a;color:white;padding:9px 7px;text-align:center}}
  td{{padding:8px 7px;text-align:center;border-bottom:1px solid #f0f0f0;vertical-align:middle}}
  tr:hover{{background:#f0fff0}}
  .grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
  .grid-3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:16px}}
  .grid-4{{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:12px;margin-bottom:16px}}
  .card{{background:#f8f9ff;border-radius:10px;padding:16px;border:1px solid #e0e4f0}}
  .card .label{{font-size:11px;color:#888;margin-bottom:6px}}
  .card .value{{font-size:15px;font-weight:bold}}
  .outlook-box{{border-radius:10px;padding:20px;text-align:center;margin-bottom:16px}}
  .strategy-box{{background:#fff9e6;border:1px solid #f0c040;border-radius:8px;padding:16px;font-size:13px;line-height:2}}
  .psych-box{{background:#f0f8ff;border:1px solid #3498db;border-radius:8px;padding:16px}}
  .footer{{background:#f8f9ff;padding:14px;text-align:center;font-size:11px;color:#999}}
  ul{{margin:0;padding-left:20px}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🌅 장 시작 전 준비 리포트 (풀버전)</h1>
    <p>{today_str} {now_str} 기준 | 오늘 전략 종합</p>
  </div>

  <!-- 오늘 시장 전망 -->
  <div class="section">
    <div class="section-title">📊 오늘 한국 시장 종합 전망</div>
    <div class="outlook-box" style="background:{outlook_color}22;border:2px solid {outlook_color}">
      <div style="font-size:22px;font-weight:bold;color:{outlook_color}">{outlook_title}</div>
      <div style="font-size:13px;color:#555;margin-top:8px">{outlook_reason}</div>
      <div style="font-size:14px;font-weight:bold;color:{outlook_color};margin-top:8px">→ {outlook_action}</div>
    </div>

    <div class="grid-4">
      <div class="card">
        <div class="label">🌡️ VIX 시장 필터</div>
        <div class="value" style="color:{vix_color};font-size:13px">{vix_signal}</div>
        <div style="font-size:20px;font-weight:bold;color:{vix_color}">{vix_val}</div>
        <div style="font-size:11px;margin-top:4px;color:#666">{day_strategy}</div>
      </div>
      <div class="card">
        <div class="label">😱 공포/탐욕 지수</div>
        <div class="value" style="color:{fg_color}">{fg_val}</div>
        <div style="font-size:13px;color:{fg_color};font-weight:bold">{fg_text}</div>
        <div style="font-size:11px;color:#666;margin-top:4px">
          {'역발상 매수 기회' if fg_val<=25 else '탐욕 과열 주의!' if fg_val>=75 else '중립 구간'}
        </div>
      </div>
      <div class="card">
        <div class="label">📅 계절성</div>
        <div class="value" style="color:{season_color};font-size:13px">{season_title}</div>
        <div style="font-size:11px;color:#666;margin-top:4px">{season_desc}</div>
      </div>
      <div class="card">
        <div class="label">📉 장단기 금리차</div>
        <div class="value" style="color:{yield_color}">{yield_diff:+.3f}%</div>
        <div style="font-size:12px;color:{yield_color};margin-top:4px">{yield_signal}</div>
      </div>
    </div>
  </div>

  <!-- 거시경제 + 섹터 -->
  <div class="section">
    <div class="section-title">🌍 미국 시장 마감 + 섹터 로테이션</div>
    <div class="grid-2">
      <div>
        <div style="font-weight:bold;margin-bottom:8px;font-size:13px">🌍 글로벌 시장</div>
        <table><tr><th>지표</th><th>가격</th><th>등락률</th></tr>{macro_rows}</table>
      </div>
      <div>
        <div style="font-weight:bold;margin-bottom:8px;font-size:13px">🔄 섹터 로테이션 (5일 수익률)</div>
        <table><tr><th>섹터</th><th>5일수익률</th></tr>{sector_rows}</table>
        <div style="font-size:11px;color:#888;margin-top:8px">
          💡 상위 섹터 = 지금 돈이 몰리는 곳 → 해당 섹터 종목 우선 주목!
        </div>
      </div>
    </div>
  </div>

  <!-- 전일 급등 종목 -->
  <div class="section">
    <div class="section-title">🔥 전일 급등 종목 TOP10 (등락률 5% 이상)</div>
    <table>
      <tr><th>종목명</th><th>시장</th><th>현재가</th><th>등락률</th><th>거래량</th><th>시가총액(억)</th></tr>
      {gainer_rows}
    </table>
  </div>

  <!-- 갭상 예상 후보 -->
  <div class="section">
    <div class="section-title">⚡ 오늘 갭상 예상 후보 (미국 선물 + 전일 급등 분석)</div>
    <table>
      <tr><th>종목명</th><th>시장</th><th>전일등락률</th><th>전일종가</th><th>갭상전망</th><th>근거</th><th>주의사항</th></tr>
      {gap_rows}
    </table>
  </div>

  <!-- 외국인 순매수 -->
  <div class="section">
    <div class="section-title">💼 외국인 순매수 상위 종목 (어제 기준)</div>
    <table>
      <tr><th>종목명</th><th>현재가</th><th>등락률</th><th>외국인순매수</th></tr>
      {investor_rows}
    </table>
    <div style="font-size:11px;color:#888;margin-top:8px">
      💡 외국인 순매수 종목 = 기관도 함께 사면 강한 매수 신호!
    </div>
  </div>

  <!-- 오늘 전략 -->
  <div class="section">
    <div class="section-title">📋 오늘 장 시작 전략</div>
    <div class="strategy-box">
      🕘 <b>09:00~09:05</b>: 시초가 확인 — 갭상/갭하 여부 체크<br>
      🕘 <b>09:05~09:10</b>: 시가 유지 종목만 진입 검토 (시가이탈 즉시 제외)<br>
      📊 <b>09:10 이후</b>: VWAP 확인 → VWAP 위 종목만 매수, 아래는 대기<br>
      📈 <b>거래량 체크</b>: 평균의 3배 이상 터지는 종목 우선 주목<br>
      🚫 <b>추격금지</b>: 시초 +4% 이상 갭상 → 눌림 올 때까지 절대 추격 금지<br>
      ✂️ <b>손절원칙</b>: 매수가 대비 -3% 무조건 즉시 손절<br>
      📉 <b>트레일링스탑</b>: 고점 대비 -2% 이탈 시 청산<br>
      💰 <b>익절원칙</b>: 1차 +3% 절반 익절, 2차 +6% 전량 익절<br>
      ⏰ <b>강제청산</b>: 14:30 이전 미익절 포지션 무조건 정리<br>
      🔍 <b>MACD 확인</b>: 데드크로스 발생 시 즉시 청산<br>
      {'⚠️ <b>오늘 단타 주의!</b>: VIX 25 이상 — 보수적 매매 권장' if vix_val>=25 else '✅ <b>오늘 단타 가능!</b>: VIX 안정 구간'}
    </div>
  </div>

  <!-- 경제 지표 일정 -->
  <div class="section">
    <div class="section-title">📅 주요 경제 지표 일정</div>
    <ul style="line-height:2;font-size:13px">{schedule_html}</ul>
  </div>

  <!-- 심리 체크리스트 -->
  <div class="section">
    <div class="section-title">🧠 오늘 매매 전 심리 체크리스트</div>
    <div class="psych-box">
      <ul style="line-height:2;font-size:13px">{psych_html}</ul>
    </div>
  </div>

  <div class="footer">
    ⚠️ 본 보고서는 참고용이며 투자 판단의 최종 책임은 본인에게 있습니다.<br>
    적용 기법: VIX필터 | 공포탐욕지수 | 장단기금리차 | 계절성 | 섹터로테이션 | 갭상분석 | 외국인수급 | 심리체크
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
    print("🌅 장 시작 전 준비 리포트 (풀버전) 생성 시작")
    print("="*50)

    html = build_report()

    with open("premarket_report.html","w",encoding="utf-8") as f:
        f.write(html)
    print("✅ 보고서 저장 완료")

    today_str = dt.datetime.now(KST).strftime("%Y/%m/%d")
    send_email(f"🌅 [{today_str}] 장 시작 전 준비 리포트 (풀버전)", html)
    print("="*50)
    print("✅ 완료!")

if __name__ == "__main__":
    main()

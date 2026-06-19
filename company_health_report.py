# company_health_report.py
# 보유 종목 재무 건전성 주간 진단 보고서
# DART 연동 + Google Sheets 연동 + 이메일 발송
# 매주 1회 실행 권장 (재무제표는 분기 단위로만 갱신되므로)
# pip install opendartreader pandas requests

import pandas as pd
import os
import json
import requests
import datetime as dt
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import warnings
warnings.filterwarnings("ignore")

from company_health import diagnose_portfolio_health

KST = dt.timezone(dt.timedelta(hours=9))

GMAIL_ADDRESS      = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
RECEIVE_ADDRESS    = os.environ.get("RECEIVE_ADDRESS", "")
APP_KEY             = os.environ.get("APP_KEY", "")
APP_SECRET          = os.environ.get("APP_SECRET", "")
SHEET_ID           = "1-7TeKv9OucJYMvXN55yQ5w0Rg0Fwi8QQH44jmUfzElg"
TOKEN_FILE          = "token.json"

# =====================================================
# 한국투자증권 토큰 + 실시간가 조회 (PER/PBR 정확도 향상용)
# =====================================================
def get_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
        if data.get("issued_at") == dt.datetime.now(KST).strftime("%Y-%m-%d"):
            return data["access_token"]
    url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    res = requests.post(url, headers={"content-type": "application/json"},
        data=json.dumps({"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}),
        timeout=10)
    token_data = res.json()
    token_data["issued_at"] = dt.datetime.now(KST).strftime("%Y-%m-%d")
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f)
    return token_data["access_token"]

def get_current_prices(holdings):
    """보유 종목의 실시간 현재가 일괄 조회 (PER/PBR 계산용)"""
    prices = {}
    try:
        token = get_token()
    except Exception as e:
        print(f"⚠️ 토큰 발급 실패, 평단가로 대체 계산: {e}")
        return prices

    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {"content-type": "application/json", "authorization": f"Bearer {token}",
               "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHKST01010100"}

    for code, name, qty, avg, market in holdings:
        if market not in ("KR",):
            continue
        try:
            res = requests.get(url, headers=headers,
                params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code}, timeout=10)
            output = res.json().get("output", {})
            price = int(output.get("stck_prpr", 0))
            if price > 0:
                prices[code] = price
        except Exception:
            continue
    return prices

# =====================================================
# Google Sheets에서 보유종목 로드 (portfolio_report.py와 동일 로직)
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
            except:
                continue
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
    ]

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
def build_health_report(results):
    today = dt.datetime.now(KST).strftime("%Y년 %m월 %d일")

    # 등급별 카운트
    safe_count    = sum(1 for r in results if r["점수"] is not None and r["점수"] >= 80)
    ok_count      = sum(1 for r in results if r["점수"] is not None and 60 <= r["점수"] < 80)
    warn_count    = sum(1 for r in results if r["점수"] is not None and 40 <= r["점수"] < 60)
    danger_count  = sum(1 for r in results if r["점수"] is not None and r["점수"] < 40)
    unknown_count = sum(1 for r in results if r["점수"] is None)

    rows = ""
    for r in results:
        score_display = f"{r['점수']}점" if r['점수'] is not None else "-"
        매출 = f"{r['매출액']:,.0f}" if r.get('매출액') else "-"
        영업이익 = f"{r['영업이익']:,.0f}" if r.get('영업이익') else "-"
        순이익 = f"{r['당기순이익']:,.0f}" if r.get('당기순이익') else "-"
        부채비율 = f"{r['부채비율']}%" if r.get('부채비율') is not None else "-"
        유보율 = f"{r['유보율']:,.0f}%" if r.get('유보율') is not None else "-"

        detail_html = "<br>".join([f"<span style='font-size:11px'>{d}</span>" for d in r.get("세부", [])])

        rows += f"""<tr>
          <td><b>{r['종목명']}</b><br><small style="color:#888">{r['종목코드']}</small></td>
          <td style="color:{r['색상']};font-weight:bold">{r['등급']}</td>
          <td style="color:{r['색상']};font-weight:bold;font-size:16px">{score_display}</td>
          <td style="font-size:11px">매출 {매출}원<br>영업이익 {영업이익}원<br>순이익 {순이익}원</td>
          <td style="font-size:11px">부채비율 {부채비율}<br>유보율 {유보율}</td>
          <td style="font-size:11px;text-align:left">{detail_html}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
  body{{font-family:'Malgun Gothic',sans-serif;background:#f5f7fa;color:#333;margin:0;padding:10px}}
  .container{{max-width:1300px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.1)}}
  .header{{background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);color:white;padding:20px;text-align:center}}
  .header h1{{margin:0;font-size:20px;letter-spacing:2px}}
  .section{{padding:16px;border-bottom:1px solid #eee}}
  .section-title{{font-size:13px;font-weight:bold;color:#1a1a2e;margin-bottom:10px;padding-left:8px;border-left:4px solid #0f3460}}
  table{{width:100%;border-collapse:collapse;font-size:12px}}
  th{{background:#1a1a2e;color:white;padding:8px 6px;text-align:center}}
  td{{padding:8px 6px;text-align:center;border-bottom:1px solid #f0f0f0;vertical-align:top}}
  tr:hover{{background:#f8f9ff}}
  .summary-box{{display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap}}
  .summary-card{{flex:1;min-width:100px;background:#f8f9ff;border-radius:8px;padding:12px;text-align:center;border:1px solid #e0e4f0}}
  .summary-card .label{{font-size:10px;color:#888;margin-bottom:4px}}
  .summary-card .value{{font-size:20px;font-weight:bold}}
  .footer{{background:#f8f9ff;padding:10px;text-align:center;font-size:10px;color:#999}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🏥 보유 종목 재무 건전성 주간 진단</h1>
    <p style="margin:4px 0 0;opacity:0.8;font-size:12px">{today} | DART 공시 데이터 기반</p>
  </div>

  <div class="section">
    <div class="section-title">📋 종합 현황</div>
    <div class="summary-box">
      <div class="summary-card"><div class="label">🟢 우량</div><div class="value" style="color:#27ae60">{safe_count}개</div></div>
      <div class="summary-card"><div class="label">🟡 양호</div><div class="value" style="color:#f39c12">{ok_count}개</div></div>
      <div class="summary-card"><div class="label">🟠 주의</div><div class="value" style="color:#e67e22">{warn_count}개</div></div>
      <div class="summary-card"><div class="label">🔴 위험</div><div class="value" style="color:#e74c3c">{danger_count}개</div></div>
      <div class="summary-card"><div class="label">❓ 데이터없음</div><div class="value" style="color:#888">{unknown_count}개</div></div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">🏥 종목별 재무 건전성 상세</div>
    <div style="overflow-x:auto">
    <table>
      <tr><th>종목</th><th>등급</th><th>점수</th><th>실적</th><th>재무비율</th><th>세부 진단</th></tr>
      {rows if rows else "<tr><td colspan='6' style='color:#999'>진단 결과 없음</td></tr>"}
    </table>
    </div>
  </div>

  <div class="section">
    <div class="section-title">📖 점수 산정 기준</div>
    <table style="font-size:11px">
      <tr><th>항목</th><th>배점</th><th>기준</th></tr>
      <tr><td>부채비율</td><td>20점</td><td>100%이하 만점, 200%초과 0점</td></tr>
      <tr><td>유보율</td><td>15점</td><td>1000%이상 만점, 300%미만 0점</td></tr>
      <tr><td>영업이익→순이익 전환</td><td>15점</td><td>괴리율 적을수록 고득점</td></tr>
      <tr><td>현금흐름 패턴</td><td>25점</td><td>영업+/투자-/재무- 우량형 만점</td></tr>
      <tr><td>유동비율</td><td>10점</td><td>150%이상 만점</td></tr>
      <tr><td>PER/PBR</td><td>15점</td><td>저평가일수록 고득점</td></tr>
    </table>
  </div>

  <div class="footer">
    ⚠️ 본 진단은 DART 공시 재무제표 기반 참고용이며 투자 판단의 최종 책임은 본인에게 있습니다.<br>
    재무제표는 분기 단위로만 갱신되므로 매주 동일한 결과가 나올 수 있습니다.
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
    print("🏥 보유 종목 재무 건전성 주간 진단 시작")
    print("="*50)
    holdings = load_holdings_from_sheets()

    print("💹 실시간 현재가 조회 중 (PER/PBR 정확도 향상용)...")
    try:
        current_prices = get_current_prices(holdings)
        print(f"✅ {len(current_prices)}개 종목 실시간가 확보")
    except Exception as e:
        print(f"⚠️ 실시간가 조회 실패, 평단가로 대체: {e}")
        current_prices = {}

    results = diagnose_portfolio_health(holdings, current_prices=current_prices)

    html = build_health_report(results)
    with open("company_health_report.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✅ 보고서 저장 완료")

    today_str = dt.datetime.now(KST).strftime("%Y/%m/%d")
    send_email(f"🏥 [{today_str}] 보유종목 재무건전성 주간진단", html)
    print("✅ 완료!")

if __name__ == "__main__":
    main()

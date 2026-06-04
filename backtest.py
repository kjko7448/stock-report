# backtest.py
# 주식 프로그램 백테스트
# 2026년 1월 ~ 현재 과거 데이터로 소급 적용
# 검증 기법: 터틀 매수신호 / 주도주 스코어 / 섹터 선택
# pip install yfinance pandas matplotlib

import yfinance as yf
import pandas as pd
import datetime as dt
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

KST = dt.timezone(dt.timedelta(hours=9))

GMAIL_ADDRESS      = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
RECEIVE_ADDRESS    = os.environ.get("RECEIVE_ADDRESS", "")

# =====================================================
# 백테스트 대상 종목 (23개 섹터 대표주)
# =====================================================
BACKTEST_STOCKS = {
    # 조류
    "AI/반도체":        [("000660.KS","SK하이닉스"),("042700.KS","한미반도체"),("005930.KS","삼성전자")],
    "전력/전기인프라":  [("010120.KS","LS ELECTRIC"),("103590.KS","일진전기"),("267270.KS","HD현대일렉트릭")],
    "로봇/자동화":      [("454910.KS","두산로보틱스"),("277810.KS","레인보우로보틱스")],
    "방산/우주":        [("012450.KS","한화에어로스페이스"),("079550.KS","LIG넥스원")],
    "바이오/헬스케어":  [("207940.KS","삼성바이오로직스"),("068270.KS","셀트리온")],
    "AI소프트웨어":     [("035420.KS","NAVER"),("304100.KS","솔트룩스")],
    "조선/해운":        [("329180.KS","HD현대중공업"),("042660.KS","한화오션")],
    "2차전지소재":      [("247540.KS","에코프로비엠"),("003670.KS","포스코퓨처엠")],
    "금융/보험/증권":   [("105560.KS","KB금융"),("055550.KS","신한지주")],
    "자동차/부품":      [("005380.KS","현대차"),("000270.KS","기아")],
}

# 비교 벤치마크
BENCHMARK = "^KS11"  # KOSPI

# 백테스트 기간
START_DATE = "2023-01-02"
END_DATE   = dt.datetime.now(KST).strftime("%Y-%m-%d")

# =====================================================
# 데이터 수집
# =====================================================
def fetch_data(ticker, start, end):
    try:
        hist = yf.Ticker(ticker).history(start=start, end=end).dropna()
        if hist.empty:
            return None
        hist.index = hist.index.tz_localize(None)
        return hist
    except:
        return None

# =====================================================
# 기법 1: 터틀 트레이딩 백테스트
# =====================================================
def backtest_turtle(ticker, name, hist, period=20):
    """
    20캔들 신고가 돌파 시 매수
    20캔들 신저가 이탈 시 매도
    """
    if hist is None or len(hist) < period+1:
        return None

    trades = []
    position = False
    buy_price = 0
    buy_date = None

    for i in range(period, len(hist)):
        curr_price = hist["Close"].iloc[i]
        curr_date  = hist.index[i]

        high20 = hist["High"].iloc[i-period:i].max()
        low20  = hist["Low"].iloc[i-period:i].min()

        if not position:
            # 신고가 돌파 → 매수
            if curr_price >= high20:
                position  = True
                buy_price = curr_price
                buy_date  = curr_date
        else:
            # 신저가 이탈 → 매도
            if curr_price <= low20:
                profit_rate = (curr_price - buy_price) / buy_price * 100
                hold_days   = (curr_date - buy_date).days
                trades.append({
                    "매수일":    buy_date.strftime("%Y-%m-%d"),
                    "매도일":    curr_date.strftime("%Y-%m-%d"),
                    "매수가":    round(buy_price),
                    "매도가":    round(curr_price),
                    "수익률":    round(profit_rate,2),
                    "보유일수":  hold_days,
                    "결과":      "✅ 수익" if profit_rate > 0 else "❌ 손실",
                })
                position  = False
                buy_price = 0
                buy_date  = None

    # 아직 보유 중이면 현재가로 미실현
    unrealized = None
    if position:
        curr_price  = hist["Close"].iloc[-1]
        profit_rate = (curr_price - buy_price) / buy_price * 100
        unrealized  = {
            "매수일":   buy_date.strftime("%Y-%m-%d"),
            "매도일":   "보유중",
            "매수가":   round(buy_price),
            "매도가":   round(curr_price),
            "수익률":   round(profit_rate,2),
            "보유일수": (hist.index[-1] - buy_date).days,
            "결과":     "📊 보유중",
        }

    if not trades and not unrealized:
        return None

    all_trades = trades + ([unrealized] if unrealized else [])
    completed  = [t for t in trades]

    win_count  = sum(1 for t in completed if t["수익률"] > 0)
    loss_count = len(completed) - win_count
    win_rate   = round(win_count / len(completed) * 100, 1) if completed else 0
    avg_win    = round(pd.Series([t["수익률"] for t in completed if t["수익률"]>0]).mean(),2) if win_count>0 else 0
    avg_loss   = round(pd.Series([t["수익률"] for t in completed if t["수익률"]<=0]).mean(),2) if loss_count>0 else 0
    pl_ratio   = round(abs(avg_win/avg_loss),2) if avg_loss!=0 else 0
    total_ret  = round(sum(t["수익률"] for t in completed),2)

    return {
        "종목명":    name,
        "거래횟수":  len(completed),
        "승":        win_count,
        "패":        loss_count,
        "적중률":    win_rate,
        "평균수익":  avg_win,
        "평균손실":  avg_loss,
        "손익비":    pl_ratio,
        "누적수익률": total_ret,
        "거래내역":  all_trades,
        "미실현":    unrealized,
    }

# =====================================================
# 기법 2: 주도주 스코어 백테스트
# =====================================================
def backtest_leader_score(ticker, name, hist, kospi_hist, threshold=60):
    """
    주도주 점수 threshold 이상일 때만 매수
    터틀 매도 기준 적용
    """
    if hist is None or len(hist) < 40:
        return None

    trades   = []
    position = False
    buy_price= 0
    buy_date = None

    for i in range(40, len(hist)):
        curr_price = hist["Close"].iloc[i]
        curr_date  = hist.index[i]

        # 주도주 점수 계산 (간소화)
        score = 0

        # ① 신고가 근접도
        high52 = hist["High"].iloc[max(0,i-252):i].max()
        low52  = hist["Low"].iloc[max(0,i-252):i].min()
        if high52 > low52:
            cycle = (curr_price - low52) / (high52 - low52) * 100
            if cycle >= 80:  score += 20
            elif cycle >= 60: score += 15
            elif cycle >= 30: score += 8
            else:             score += 5

        # ② 코스피 대비 아웃퍼폼 (20일)
        if len(kospi_hist) > i and i >= 20:
            try:
                stock_20d = (hist["Close"].iloc[i] - hist["Close"].iloc[i-20]) / hist["Close"].iloc[i-20] * 100
                kospi_20d = (kospi_hist["Close"].iloc[i] - kospi_hist["Close"].iloc[i-20]) / kospi_hist["Close"].iloc[i-20] * 100
                out = stock_20d - kospi_20d
                if out >= 10:  score += 15
                elif out >= 5: score += 10
                elif out >= 0: score += 5
                else:          score -= 5
            except: pass

        # ③ 모멘텀 가속도
        if i >= 20:
            ret_1w = (hist["Close"].iloc[i] - hist["Close"].iloc[i-5]) / hist["Close"].iloc[i-5] * 100
            ret_1m = (hist["Close"].iloc[i] - hist["Close"].iloc[i-20]) / hist["Close"].iloc[i-20] * 100
            if ret_1w > ret_1m / 4: score += 10
            elif ret_1w > 0:        score += 5

        # ④ 거래량
        avg_vol = hist["Volume"].iloc[max(0,i-20):i].mean()
        now_vol = hist["Volume"].iloc[i]
        vol_ratio = now_vol / avg_vol if avg_vol > 0 else 1
        if vol_ratio >= 2:   score += 15
        elif vol_ratio >= 1.5: score += 10

        low20  = hist["Low"].iloc[max(0,i-20):i].min()

        if not position:
            if score >= threshold:
                position  = True
                buy_price = curr_price
                buy_date  = curr_date
        else:
            if curr_price <= low20:
                profit_rate = (curr_price - buy_price) / buy_price * 100
                trades.append({
                    "매수일":   buy_date.strftime("%Y-%m-%d"),
                    "매도일":   curr_date.strftime("%Y-%m-%d"),
                    "매수가":   round(buy_price),
                    "매도가":   round(curr_price),
                    "수익률":   round(profit_rate,2),
                    "점수":     score,
                    "결과":     "✅ 수익" if profit_rate > 0 else "❌ 손실",
                })
                position  = False
                buy_price = 0

    unrealized = None
    if position:
        curr_price  = hist["Close"].iloc[-1]
        profit_rate = (curr_price - buy_price) / buy_price * 100
        unrealized  = {
            "매수일": buy_date.strftime("%Y-%m-%d"),
            "매도일": "보유중",
            "매수가": round(buy_price),
            "매도가": round(curr_price),
            "수익률": round(profit_rate,2),
            "결과":   "📊 보유중",
        }

    if not trades and not unrealized:
        return None

    completed  = trades
    win_count  = sum(1 for t in completed if t["수익률"] > 0)
    loss_count = len(completed) - win_count
    win_rate   = round(win_count / len(completed) * 100, 1) if completed else 0
    avg_win    = round(pd.Series([t["수익률"] for t in completed if t["수익률"]>0]).mean(),2) if win_count>0 else 0
    avg_loss   = round(pd.Series([t["수익률"] for t in completed if t["수익률"]<=0]).mean(),2) if loss_count>0 else 0
    total_ret  = round(sum(t["수익률"] for t in completed),2)

    return {
        "종목명":    name,
        "거래횟수":  len(completed),
        "승":        win_count,
        "패":        loss_count,
        "적중률":    win_rate,
        "평균수익":  avg_win,
        "평균손실":  avg_loss,
        "누적수익률": total_ret,
        "거래내역":  trades + ([unrealized] if unrealized else []),
        "미실현":    unrealized,
    }

# =====================================================
# 기법 3: 섹터 선택 백테스트
# =====================================================
def backtest_sector(sector_name, stocks_data, kospi_ret):
    """
    섹터별 평균 수익률 vs KOSPI 비교
    """
    rets = []
    for ticker, name, hist in stocks_data:
        if hist is None or len(hist) < 2: continue
        total_ret = (hist["Close"].iloc[-1] - hist["Close"].iloc[0]) / hist["Close"].iloc[0] * 100
        rets.append({"종목":name, "수익률":round(total_ret,2)})

    if not rets: return None

    avg_ret = round(sum(r["수익률"] for r in rets) / len(rets), 2)
    vs_kospi = round(avg_ret - kospi_ret, 2)

    return {
        "섹터":      sector_name,
        "평균수익률": avg_ret,
        "KOSPI대비":  vs_kospi,
        "아웃퍼폼":  vs_kospi > 0,
        "종목들":    rets,
    }

# =====================================================
# 벤치마크 수익률
# =====================================================
def get_benchmark_return(start, end):
    hist = fetch_data(BENCHMARK, start, end)
    if hist is None or len(hist) < 2:
        return 0
    return round((hist["Close"].iloc[-1] - hist["Close"].iloc[0]) / hist["Close"].iloc[0] * 100, 2)

# =====================================================
# HTML 보고서 생성
# =====================================================
def build_backtest_report(turtle_results, leader_results, sector_results, kospi_ret):
    today = dt.datetime.now(KST).strftime("%Y년 %m월 %d일 %H:%M")

    # 터틀 요약
    turtle_summary = []
    for r in turtle_results:
        if r:
            turtle_summary.append(r)

    turtle_rows = ""
    for r in sorted(turtle_summary, key=lambda x: x["누적수익률"], reverse=True):
        color = "#27ae60" if r["누적수익률"] > 0 else "#e74c3c"
        pl_color = "#27ae60" if r["손익비"] >= 2 else "#f39c12" if r["손익비"] >= 1 else "#e74c3c"
        turtle_rows += f"""<tr>
          <td><b>{r['종목명']}</b></td>
          <td>{r['거래횟수']}회</td>
          <td>{r['승']}승 {r['패']}패</td>
          <td style="color:{'#27ae60' if r['적중률']>=60 else '#e74c3c'}">{r['적중률']}%</td>
          <td style="color:#27ae60">+{r['평균수익']}%</td>
          <td style="color:#e74c3c">{r['평균손실']}%</td>
          <td style="color:{pl_color}">{r['손익비']}:1</td>
          <td style="color:{color};font-weight:bold">{r['누적수익률']:+.2f}%</td>
          <td>{"✅ 보유중" if r['미실현'] else "-"}</td>
        </tr>"""

    # 주도주 스코어 요약
    leader_rows = ""
    for r in sorted(leader_results, key=lambda x: x["누적수익률"], reverse=True):
        if r:
            color = "#27ae60" if r["누적수익률"] > 0 else "#e74c3c"
            leader_rows += f"""<tr>
              <td><b>{r['종목명']}</b></td>
              <td>{r['거래횟수']}회</td>
              <td>{r['승']}승 {r['패']}패</td>
              <td style="color:{'#27ae60' if r['적중률']>=60 else '#e74c3c'}">{r['적중률']}%</td>
              <td style="color:{color};font-weight:bold">{r['누적수익률']:+.2f}%</td>
              <td>{"✅ 보유중" if r['미실현'] else "-"}</td>
            </tr>"""

    # 섹터 요약
    sector_rows = ""
    for s in sorted(sector_results, key=lambda x: x["평균수익률"], reverse=True):
        color = "#27ae60" if s["아웃퍼폼"] else "#e74c3c"
        sector_rows += f"""<tr>
          <td><b>{s['섹터']}</b></td>
          <td style="color:{'#27ae60' if s['평균수익률']>=0 else '#e74c3c'};font-weight:bold">{s['평균수익률']:+.2f}%</td>
          <td>{kospi_ret:+.2f}%</td>
          <td style="color:{color};font-weight:bold">{s['KOSPI대비']:+.2f}%</td>
          <td>{"✅ 아웃퍼폼" if s['아웃퍼폼'] else "❌ 언더퍼폼"}</td>
        </tr>"""

    # 전체 성과 요약
    all_turtle = [r for r in turtle_results if r]
    avg_win_rate = round(sum(r["적중률"] for r in all_turtle) / len(all_turtle), 1) if all_turtle else 0
    avg_pl_ratio = round(sum(r["손익비"] for r in all_turtle) / len(all_turtle), 2) if all_turtle else 0
    avg_ret_turtle = round(sum(r["누적수익률"] for r in all_turtle) / len(all_turtle), 2) if all_turtle else 0

    outperform_sectors = sum(1 for s in sector_results if s["아웃퍼폼"])
    total_sectors = len(sector_results)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
  body{{font-family:'Malgun Gothic',sans-serif;background:#f5f7fa;color:#333;margin:0;padding:10px}}
  .container{{max-width:1200px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.1)}}
  .header{{background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);color:white;padding:24px;text-align:center}}
  .header h1{{margin:0;font-size:22px;letter-spacing:2px}}
  .section{{padding:18px;border-bottom:1px solid #eee}}
  .section-title{{font-size:14px;font-weight:bold;color:#1a1a2e;margin-bottom:12px;padding-left:8px;border-left:4px solid #0f3460}}
  table{{width:100%;border-collapse:collapse;font-size:12px}}
  th{{background:#1a1a2e;color:white;padding:8px 6px;text-align:center}}
  td{{padding:7px 6px;text-align:center;border-bottom:1px solid #f0f0f0;vertical-align:middle}}
  tr:hover{{background:#f8f9ff}}
  .summary-box{{display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap}}
  .summary-card{{flex:1;min-width:130px;background:#f8f9ff;border-radius:8px;padding:12px;text-align:center;border:1px solid #e0e4f0}}
  .summary-card .label{{font-size:10px;color:#888;margin-bottom:4px}}
  .summary-card .value{{font-size:18px;font-weight:bold}}
  .verdict-box{{border-radius:10px;padding:16px;margin-bottom:16px;font-size:13px;line-height:1.8}}
  .footer{{background:#f8f9ff;padding:12px;text-align:center;font-size:10px;color:#999}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📊 주식 프로그램 백테스트 결과</h1>
    <p style="margin:6px 0 0;opacity:0.8;font-size:13px">{START_DATE} ~ {END_DATE} | {today} 생성</p>
  </div>

  <!-- 종합 성과 -->
  <div class="section">
    <div class="section-title">🏆 종합 성과 요약</div>
    <div class="summary-box">
      <div class="summary-card">
        <div class="label">KOSPI 수익률</div>
        <div class="value" style="color:{'#27ae60' if kospi_ret>=0 else '#e74c3c'}">{kospi_ret:+.2f}%</div>
      </div>
      <div class="summary-card">
        <div class="label">터틀 평균 수익률</div>
        <div class="value" style="color:{'#27ae60' if avg_ret_turtle>=0 else '#e74c3c'}">{avg_ret_turtle:+.2f}%</div>
      </div>
      <div class="summary-card">
        <div class="label">평균 적중률</div>
        <div class="value" style="color:{'#27ae60' if avg_win_rate>=60 else '#e74c3c'}">{avg_win_rate}%</div>
      </div>
      <div class="summary-card">
        <div class="label">평균 손익비</div>
        <div class="value" style="color:{'#27ae60' if avg_pl_ratio>=2 else '#f39c12'}">{avg_pl_ratio}:1</div>
      </div>
      <div class="summary-card">
        <div class="label">섹터 아웃퍼폼</div>
        <div class="value" style="color:{'#27ae60' if outperform_sectors/total_sectors>=0.5 else '#e74c3c'}">{outperform_sectors}/{total_sectors}</div>
      </div>
    </div>

    <!-- 종합 평가 -->
    <div class="verdict-box" style="background:{'#d5f5e3' if avg_ret_turtle>kospi_ret else '#fadbd8'};border:1px solid {'#27ae60' if avg_ret_turtle>kospi_ret else '#e74c3c'}">
      <b>📋 종합 평가:</b><br>
      {'✅ 우리 프로그램이 KOSPI보다 우수한 성과를 보였어요!' if avg_ret_turtle>kospi_ret else '⚠️ 이 기간 동안 KOSPI를 하회했어요. 기법 개선이 필요해요.'}<br>
      터틀 트레이딩 평균 수익률 {avg_ret_turtle:+.2f}% vs KOSPI {kospi_ret:+.2f}% (차이: {avg_ret_turtle-kospi_ret:+.2f}%)<br>
      섹터 선택 아웃퍼폼: {outperform_sectors}/{total_sectors}개 섹터 ({round(outperform_sectors/total_sectors*100)}%)
    </div>
  </div>

  <!-- 터틀 트레이딩 결과 -->
  <div class="section">
    <div class="section-title">🐢 터틀 트레이딩 백테스트 (20캔들 신고가 매수 / 신저가 매도)</div>
    <div style="overflow-x:auto">
    <table>
      <tr><th>종목명</th><th>거래횟수</th><th>승/패</th><th>적중률</th><th>평균수익</th><th>평균손실</th><th>손익비</th><th>누적수익률</th><th>현재</th></tr>
      {turtle_rows if turtle_rows else "<tr><td colspan='9' style='color:#999'>데이터 없음</td></tr>"}
    </table>
    </div>
    <div style="font-size:11px;color:#888;margin-top:8px">
      💡 손익비 2:1 이상 = 양호 / 적중률 50% 이상 = 정상 (터틀은 손익비가 핵심!)
    </div>
  </div>

  <!-- 주도주 스코어 결과 -->
  <div class="section">
    <div class="section-title">🔥 주도주 스코어 백테스트 (60점 이상 매수)</div>
    <div style="overflow-x:auto">
    <table>
      <tr><th>종목명</th><th>거래횟수</th><th>승/패</th><th>적중률</th><th>누적수익률</th><th>현재</th></tr>
      {leader_rows if leader_rows else "<tr><td colspan='6' style='color:#999'>데이터 없음</td></tr>"}
    </table>
    </div>
  </div>

  <!-- 섹터 선택 결과 -->
  <div class="section">
    <div class="section-title">📊 섹터 선택 백테스트 (KOSPI {kospi_ret:+.2f}% 대비)</div>
    <div style="overflow-x:auto">
    <table>
      <tr><th>섹터명</th><th>섹터 평균수익률</th><th>KOSPI</th><th>초과수익</th><th>판정</th></tr>
      {sector_rows if sector_rows else "<tr><td colspan='5' style='color:#999'>데이터 없음</td></tr>"}
    </table>
    </div>
    <div style="font-size:11px;color:#888;margin-top:8px">
      💡 조류 섹터(AI/반도체, 전력, 로봇 등)가 KOSPI를 아웃퍼폼하면 탑다운 전략이 유효한 것!
    </div>
  </div>

  <div class="footer">
    ⚠️ 백테스트는 과거 데이터 기반이며 미래 수익을 보장하지 않습니다.<br>
    백테스트 기간: {START_DATE} ~ {END_DATE} | 수수료/세금 미반영
  </div>
</div>
</body>
</html>"""
    return html

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
            smtp.login(GMAIL_ADDRESS,GMAIL_APP_PASSWORD)
            smtp.send_message(msg)
            print("✅ 이메일 전송 성공!")
    except Exception as e:
        print(f"❌ 이메일 전송 실패: {e}")

# =====================================================
# 메인 실행
# =====================================================
def main():
    print("="*60)
    print("📊 백테스트 시작")
    print(f"기간: {START_DATE} ~ {END_DATE}")
    print("="*60)

    # KOSPI 벤치마크
    print("\n📈 KOSPI 벤치마크 수집 중...")
    kospi_ret = get_benchmark_return(START_DATE, END_DATE)
    kospi_hist = fetch_data(BENCHMARK, START_DATE, END_DATE)
    print(f"✅ KOSPI 수익률: {kospi_ret:+.2f}%")

    # 데이터 수집
    print("\n📊 종목 데이터 수집 중...")
    all_hists = {}
    for sector, stocks in BACKTEST_STOCKS.items():
        for ticker, name in stocks:
            print(f"  → {name} ({ticker}) 수집 중...")
            all_hists[ticker] = fetch_data(ticker, START_DATE, END_DATE)

    # 터틀 백테스트
    print("\n🐢 터틀 트레이딩 백테스트 실행 중...")
    turtle_results = []
    for sector, stocks in BACKTEST_STOCKS.items():
        for ticker, name in stocks:
            hist = all_hists.get(ticker)
            result = backtest_turtle(ticker, name, hist)
            if result:
                turtle_results.append(result)
                print(f"  ✅ {name}: {result['거래횟수']}회 거래, 적중률 {result['적중률']}%, 누적 {result['누적수익률']:+.2f}%")

    # 주도주 스코어 백테스트
    print("\n🔥 주도주 스코어 백테스트 실행 중...")
    leader_results = []
    for sector, stocks in BACKTEST_STOCKS.items():
        for ticker, name in stocks:
            hist = all_hists.get(ticker)
            result = backtest_leader_score(ticker, name, hist, kospi_hist)
            if result:
                leader_results.append(result)
                print(f"  ✅ {name}: {result['거래횟수']}회, 누적 {result['누적수익률']:+.2f}%")

    # 섹터 백테스트
    print("\n📊 섹터 선택 백테스트 실행 중...")
    sector_results = []
    for sector, stocks in BACKTEST_STOCKS.items():
        stocks_data = [(t, n, all_hists.get(t)) for t,n in stocks]
        result = backtest_sector(sector, stocks_data, kospi_ret)
        if result:
            sector_results.append(result)
            print(f"  ✅ {sector}: 평균 {result['평균수익률']:+.2f}% ({'✅ 아웃퍼폼' if result['아웃퍼폼'] else '❌ 언더퍼폼'})")

    # 보고서 생성
    print("\n📧 백테스트 보고서 생성 중...")
    html = build_backtest_report(turtle_results, leader_results, sector_results, kospi_ret)

    with open("backtest_report.html","w",encoding="utf-8") as f:
        f.write(html)
    print("✅ 보고서 저장 완료")

    today_str = dt.datetime.now(KST).strftime("%Y/%m/%d")
    send_email(f"📊 [{today_str}] 주식 프로그램 백테스트 결과", html)
    print("="*60)
    print("✅ 백테스트 완료!")

if __name__ == "__main__":
    main()

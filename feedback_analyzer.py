# feedback_analyzer.py
# 주간/월간 피드백 보고서 생성 (Claude API 연동)
# 실행: python feedback_analyzer.py weekly  (주간)
#       python feedback_analyzer.py monthly (월간)

import requests
import pandas as pd
import os
import sys
import datetime as dt
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

KST = dt.timezone(dt.timedelta(hours=9))

ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
GMAIL_ADDRESS      = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
RECEIVE_ADDRESS    = os.environ.get("RECEIVE_ADDRESS", "")

PRED_FILE = "predictions.csv"

# =====================================================
# 데이터 분석
# =====================================================
def analyze_data(mode="weekly"):
    if not os.path.exists(PRED_FILE):
        return None, "predictions.csv 파일 없음"

    df   = pd.read_csv(PRED_FILE, encoding="utf-8-sig")
    today = dt.datetime.now(KST).date()

    # 기간 필터
    if mode == "weekly":
        since = today - dt.timedelta(days=7)
        label = "주간"
    else:
        since = today - dt.timedelta(days=30)
        label = "월간"

    df["날짜_dt"] = pd.to_datetime(df["날짜"]).dt.date
    period_df = df[df["날짜_dt"] >= since].copy()

    if period_df.empty:
        return None, f"최근 {label} 데이터 없음"

    # ── 기본 통계 ──
    total       = len(period_df)
    has_1d      = period_df["1일후수익률"].notna() & (period_df["1일후수익률"] != "")
    has_1w      = period_df["1주후수익률"].notna() & (period_df["1주후수익률"] != "")

    # 진입 가능성
    entry_ok    = period_df["1일후진입여부"].str.contains("진입가능", na=False)
    entry_cnt   = entry_ok.sum()
    entry_rate  = round(entry_cnt / total * 100, 1) if total > 0 else 0

    # 수익/손실 분석 (1주 기준)
    if has_1w.sum() > 0:
        rates_1w    = pd.to_numeric(period_df.loc[has_1w, "1주후수익률"], errors="coerce").dropna()
        win_cnt     = (rates_1w > 0).sum()
        loss_cnt    = (rates_1w <= 0).sum()
        win_rate    = round(win_cnt / len(rates_1w) * 100, 1) if len(rates_1w) > 0 else 0
        avg_win     = round(rates_1w[rates_1w > 0].mean(), 2) if win_cnt > 0 else 0
        avg_loss    = round(rates_1w[rates_1w <= 0].mean(), 2) if loss_cnt > 0 else 0
        pl_ratio    = round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0
        best        = period_df.loc[rates_1w.idxmax(), "종목명"] if len(rates_1w) > 0 else "-"
        best_rate   = rates_1w.max() if len(rates_1w) > 0 else 0
        worst       = period_df.loc[rates_1w.idxmin(), "종목명"] if len(rates_1w) > 0 else "-"
        worst_rate  = rates_1w.min() if len(rates_1w) > 0 else 0
    else:
        win_rate = avg_win = avg_loss = pl_ratio = best_rate = worst_rate = 0
        win_cnt = loss_cnt = 0
        best = worst = "데이터 없음"
        rates_1w = pd.Series(dtype=float)

    # 놓친 수익 (진입 못했는데 수익난 종목)
    missed = period_df[
        (period_df["1일후진입여부"].str.contains("미도달", na=False)) &
        (pd.to_numeric(period_df["1주후수익률"], errors="coerce") > 5)
    ][["종목명","1주후수익률","1일후진입여부"]].head(5)

    # 기법별 성과
    method_stats = []
    for method, col, threshold in [
        ("터틀매수신호", "터틀신호", "매수신호"),
        ("RSI과매도", "신호목록", "RSI과매도"),
        ("골든크로스", "MA신호", "골든크로스"),
        ("VIX안정", "신호목록", "VIX안정"),
    ]:
        mask = period_df[col].str.contains(threshold, na=False) if col in period_df.columns else pd.Series([False]*len(period_df))
        sub  = period_df[mask]
        if len(sub) > 0 and has_1w.sum() > 0:
            sub_rates = pd.to_numeric(sub.loc[has_1w & mask, "1주후수익률"], errors="coerce").dropna()
            if len(sub_rates) > 0:
                m_win  = round((sub_rates > 0).sum() / len(sub_rates) * 100, 1)
                m_avg  = round(sub_rates.mean(), 2)
                method_stats.append({"기법": method, "사용횟수": len(sub), "적중률": f"{m_win}%", "평균수익": f"{m_avg:+.2f}%"})

    # 종목 타입 분포
    type_dist = period_df["종목타입"].value_counts().to_dict() if "종목타입" in period_df.columns else {}

    stats = {
        "label":       label,
        "total":       total,
        "entry_cnt":   entry_cnt,
        "entry_rate":  entry_rate,
        "win_cnt":     int(win_cnt),
        "loss_cnt":    int(loss_cnt),
        "win_rate":    win_rate,
        "avg_win":     avg_win,
        "avg_loss":    avg_loss,
        "pl_ratio":    pl_ratio,
        "best":        best,
        "best_rate":   float(best_rate),
        "worst":       worst,
        "worst_rate":  float(worst_rate),
        "missed":      missed.to_dict("records"),
        "method_stats": method_stats,
        "type_dist":   type_dist,
        "period_df":   period_df,
    }
    return stats, None

# =====================================================
# Claude API 분석
# =====================================================
def get_claude_analysis(stats):
    if not ANTHROPIC_API_KEY:
        return "⚠️ ANTHROPIC_API_KEY 없음"

    missed_text = ""
    for r in stats["missed"]:
        missed_text += f"  - {r['종목명']}: {r['1주후수익률']}% 상승했으나 추천가 미도달\n"

    method_text = ""
    for m in stats["method_stats"]:
        method_text += f"  - {m['기법']}: 사용 {m['사용횟수']}회, 적중률 {m['적중률']}, 평균수익 {m['평균수익']}\n"

    type_text = ""
    for t, cnt in stats["type_dist"].items():
        if t: type_text += f"  - {t}: {cnt}건\n"

    prompt = f"""
당신은 주식 투자 시스템을 분석하는 전문가입니다.
아래는 최근 {stats['label']} 주식 추천 시스템의 성과 데이터입니다.

=== {stats['label']} 성과 데이터 ===

전체 추천: {stats['total']}건
추천매수가 진입 가능: {stats['entry_cnt']}건 ({stats['entry_rate']}%)
수익 종목: {stats['win_cnt']}건 / 손실 종목: {stats['loss_cnt']}건
적중률: {stats['win_rate']}%
평균 수익: +{stats['avg_win']}%
평균 손실: {stats['avg_loss']}%
손익비: {stats['pl_ratio']} : 1
최고 수익: {stats['best']} (+{stats['best_rate']:.1f}%)
최대 손실: {stats['worst']} ({stats['worst_rate']:.1f}%)

=== 추천가 미도달로 놓친 수익 ===
{missed_text if missed_text else "없음"}

=== 기법별 성과 ===
{method_text if method_text else "데이터 없음"}

=== 종목 타입 분포 ===
{type_text if type_text else "아직 분류 없음"}

위 데이터를 분석하여 다음을 한국어로 답변해주세요:

1. **전체 성과 평가** (잘된 점과 아쉬운 점)

2. **추천매수가 문제 분석**
   - 진입 가능률이 {stats['entry_rate']}%인 이유
   - 놓친 수익 종목들의 공통점
   - 매수가 설정 개선 방안 (구체적 수치 포함)

3. **기법별 분석**
   - 가장 효과적인 기법
   - 개선이 필요한 기법
   - 기법 조합 추천

4. **코드 수정 제안**
   아래 Python 함수의 수정안을 제시해주세요.
   현재 코드:
   ```python
   def get_recommend_buy_price(price, market):
       return int(price * 0.98)  # 무조건 -2%
   ```
   종목 타입과 변동성을 고려한 개선된 코드를 제시해주세요.

5. **다음 {stats['label']} 전략**
   - 집중할 것
   - 피할 것

간결하고 실용적으로 답변해주세요.
"""

    try:
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        )
        data = res.json()
        return data["content"][0]["text"]
    except Exception as e:
        return f"Claude API 오류: {e}"

# =====================================================
# HTML 보고서 생성
# =====================================================
def build_html(stats, ai_analysis):
    today_str = dt.datetime.now(KST).strftime("%Y년 %m월 %d일")
    label     = stats["label"]

    # 진입 가능성
    entry_color = "#27ae60" if stats["entry_rate"] >= 70 else "#f39c12" if stats["entry_rate"] >= 50 else "#e74c3c"

    # 적중률
    win_color = "#27ae60" if stats["win_rate"] >= 70 else "#f39c12" if stats["win_rate"] >= 50 else "#e74c3c"

    # 손익비
    pl_color = "#27ae60" if stats["pl_ratio"] >= 2 else "#f39c12" if stats["pl_ratio"] >= 1 else "#e74c3c"

    # 놓친 수익
    missed_rows = ""
    for r in stats["missed"]:
        missed_rows += f"<tr><td><b>{r['종목명']}</b></td><td style='color:#27ae60'>+{r['1주후수익률']}%</td><td style='color:#e74c3c'>{r['1일후진입여부']}</td></tr>"
    if not missed_rows:
        missed_rows = "<tr><td colspan='3' style='color:#999'>놓친 수익 없음 👍</td></tr>"

    # 기법별 성과
    method_rows = ""
    for m in stats["method_stats"]:
        rate_num = float(m["적중률"].replace("%",""))
        color    = "#27ae60" if rate_num >= 70 else "#f39c12" if rate_num >= 50 else "#e74c3c"
        method_rows += f"<tr><td><b>{m['기법']}</b></td><td>{m['사용횟수']}회</td><td style='color:{color}'>{m['적중률']}</td><td>{m['평균수익']}</td></tr>"
    if not method_rows:
        method_rows = "<tr><td colspan='4' style='color:#999'>데이터 없음</td></tr>"

    # AI 분석 (마크다운 간단 변환)
    ai_html = ai_analysis.replace("\n", "<br>").replace("**", "<b>").replace("```python", "<pre style='background:#f5f5f5;padding:10px;border-radius:6px;font-size:12px'>").replace("```", "</pre>")

    html = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
  body{{font-family:'Malgun Gothic',sans-serif;background:#f5f7fa;color:#333;margin:0;padding:20px}}
  .container{{max-width:1000px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.1)}}
  .header{{background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);color:white;padding:28px;text-align:center}}
  .header h1{{margin:0;font-size:22px;letter-spacing:2px}}
  .section{{padding:20px;border-bottom:1px solid #eee}}
  .section-title{{font-size:15px;font-weight:bold;color:#1a1a2e;margin-bottom:14px;padding-left:10px;border-left:4px solid #0f3460}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{background:#1a1a2e;color:white;padding:9px 7px;text-align:center}}
  td{{padding:8px 7px;text-align:center;border-bottom:1px solid #f0f0f0}}
  tr:hover{{background:#f8f9ff}}
  .grid-4{{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:14px;margin-bottom:16px}}
  .grid-3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin-bottom:16px}}
  .card{{background:#f8f9ff;border-radius:10px;padding:16px;text-align:center;border:1px solid #e0e4f0}}
  .card .label{{font-size:11px;color:#888;margin-bottom:6px}}
  .card .value{{font-size:20px;font-weight:bold}}
  .ai-box{{background:#f0f8ff;border:1px solid #3498db;border-radius:8px;padding:20px;font-size:13px;line-height:1.8}}
  .footer{{background:#f8f9ff;padding:14px;text-align:center;font-size:11px;color:#999}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🔄 {label} 피드백 보고서</h1>
    <p>{today_str} 기준 | Claude AI 분석 포함</p>
  </div>

  <!-- 성과 요약 -->
  <div class="section">
    <div class="section-title">📊 {label} 성과 요약</div>
    <div class="grid-4">
      <div class="card">
        <div class="label">전체 추천</div>
        <div class="value">{stats['total']}건</div>
      </div>
      <div class="card">
        <div class="label">진입 가능률</div>
        <div class="value" style="color:{entry_color}">{stats['entry_rate']}%</div>
        <div style="font-size:11px;color:#888">{stats['entry_cnt']}건 도달</div>
      </div>
      <div class="card">
        <div class="label">적중률 (1주 기준)</div>
        <div class="value" style="color:{win_color}">{stats['win_rate']}%</div>
        <div style="font-size:11px;color:#888">{stats['win_cnt']}승 {stats['loss_cnt']}패</div>
      </div>
      <div class="card">
        <div class="label">손익비</div>
        <div class="value" style="color:{pl_color}">{stats['pl_ratio']} : 1</div>
        <div style="font-size:11px;color:#888">+{stats['avg_win']}% / {stats['avg_loss']}%</div>
      </div>
    </div>
    <div class="grid-3">
      <div class="card">
        <div class="label">🏆 최고 수익</div>
        <div class="value" style="color:#27ae60">{stats['best']}</div>
        <div style="font-size:13px;color:#27ae60">+{stats['best_rate']:.1f}%</div>
      </div>
      <div class="card">
        <div class="label">📉 최대 손실</div>
        <div class="value" style="color:#e74c3c">{stats['worst']}</div>
        <div style="font-size:13px;color:#e74c3c">{stats['worst_rate']:.1f}%</div>
      </div>
      <div class="card">
        <div class="label">💰 놓친 수익</div>
        <div class="value" style="color:#f39c12">{len(stats['missed'])}건</div>
        <div style="font-size:11px;color:#888">추천가 미도달</div>
      </div>
    </div>
  </div>

  <!-- 진입 가능성 분석 -->
  <div class="section">
    <div class="section-title">📈 추천매수가 진입 가능성 분석</div>
    <table>
      <tr><th>종목명</th><th>놓친 수익 (1주)</th><th>미도달 이유</th></tr>
      {missed_rows}
    </table>
    <div style="font-size:12px;color:#888;margin-top:8px">
      💡 이 종목들은 B타입(돌파형) 가능성 → 추천매수가를 현재가 -0.5%로 조정 검토
    </div>
  </div>

  <!-- 기법별 성과 -->
  <div class="section">
    <div class="section-title">🔍 기법별 성과 분석</div>
    <table>
      <tr><th>기법</th><th>사용횟수</th><th>적중률</th><th>평균수익</th></tr>
      {method_rows}
    </table>
  </div>

  <!-- Claude AI 분석 -->
  <div class="section">
    <div class="section-title">🧠 Claude AI 심층 분석 및 코드 수정 제안</div>
    <div class="ai-box">
      {ai_html}
    </div>
  </div>

  <div class="footer">
    ⚠️ 본 보고서는 참고용이며 투자 판단의 최종 책임은 본인에게 있습니다.<br>
    자동 생성: feedback_analyzer.py | Claude AI 분석 포함
  </div>
</div>
</body>
</html>
"""
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
            smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            smtp.send_message(msg)
            print("✅ 이메일 전송 성공!")
    except Exception as e:
        print(f"❌ 이메일 전송 실패: {e}")

# =====================================================
# 메인
# =====================================================
def main():
    mode = sys.argv[1].lower() if len(sys.argv) >= 2 else "weekly"
    print("="*50)
    print(f"🔄 {'주간' if mode=='weekly' else '월간'} 피드백 보고서 생성 시작")
    print("="*50)

    print("📊 데이터 분석 중...")
    stats, error = analyze_data(mode)
    if error:
        print(f"⚠️ {error}")
        return

    print("🧠 Claude AI 분석 중...")
    ai_analysis = get_claude_analysis(stats)

    print("📧 보고서 생성 중...")
    html = build_html(stats, ai_analysis)

    filename = f"feedback_{'weekly' if mode=='weekly' else 'monthly'}.html"
    with open(filename,"w",encoding="utf-8") as f:
        f.write(html)
    print(f"✅ 보고서 저장: {filename}")

    today_str = dt.datetime.now(KST).strftime("%Y/%m/%d")
    label     = "주간" if mode=="weekly" else "월간"
    send_email(f"🔄 [{today_str}] {label} 피드백 보고서 (Claude AI 분석)", html)
    print("="*50)
    print("✅ 완료!")

if __name__ == "__main__":
    main()

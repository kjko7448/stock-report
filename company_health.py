# company_health.py
# 보유 종목 재무 건전성 진단 모듈
# DART API 연동 — 정량 스크리닝 + 재무건전성 체크리스트
# pip install opendartreader pandas

import OpenDartReader
import pandas as pd
import os
import datetime as dt
import warnings
warnings.filterwarnings("ignore")

DART_API_KEY = os.environ.get("DART_API_KEY", "")

# =====================================================
# 종목코드 -> DART 고유번호 매핑은 OpenDartReader가 내부 처리
# 6자리 종목코드 그대로 사용 가능 (예: "005930")
# =====================================================

def get_dart_reader():
    if not DART_API_KEY:
        raise ValueError("DART_API_KEY 환경변수가 설정되지 않았습니다")
    return OpenDartReader(DART_API_KEY)

# =====================================================
# 최근 사업연도/분기 자동 판별
# =====================================================
def get_latest_report_params():
    """
    현재 날짜 기준으로 조회 가능한 최신 연도/보고서코드 추정
    분기보고서 코드: 11013(1분기) 11012(반기) 11014(3분기) 11011(사업보고서/4분기)
    """
    today = dt.datetime.now()
    year = today.year
    month = today.month

    # 분기별 공시 마감 기준 (실제 공시는 마감 후 45~90일 소요되므로 보수적으로 직전 분기 사용)
    if month in (1,2,3):
        return year-1, "11014"   # 전년 3분기보고서
    elif month in (4,5):
        return year-1, "11011"   # 전년 사업보고서
    elif month in (6,7,8):
        return year, "11013"     # 올해 1분기보고서
    elif month in (9,10):
        return year, "11012"     # 올해 반기보고서
    else:
        return year, "11014"     # 올해 3분기보고서

# =====================================================
# 재무제표 수집 (단일 종목)
# =====================================================
def get_financial_data(dart, stock_code, name):
    """
    종목코드로 최신 재무제표 수집
    실패 시 직전 분기로 1회 재시도
    """
    year, reprt_code = get_latest_report_params()

    fallback_sequence = [
        (year, reprt_code),
        (year-1, "11011"),  # 안전망: 작년 사업보고서
    ]

    for y, code in fallback_sequence:
        try:
            df = dart.finstate(stock_code, y, reprt_code=code)
            if df is not None and len(df) > 0:
                return df, y, code
        except Exception as e:
            continue

    return None, None, None

# =====================================================
# 재무 지표 추출
# =====================================================
def extract_metrics(df):
    """
    DART 재무제표 DataFrame에서 핵심 지표 추출
    fs_div: CFS(연결) 우선, 없으면 OFS(별도)
    """
    if df is None or len(df) == 0:
        return None

    metrics = {}

    # 연결재무제표 우선 사용
    fs_pref = df[df["fs_div"] == "CFS"]
    if len(fs_pref) == 0:
        fs_pref = df[df["fs_div"] == "OFS"]
    if len(fs_pref) == 0:
        fs_pref = df

    def normalize(text):
        """공백, 로마숫자, 특수문자 제거해서 매칭 정확도 향상"""
        import re
        text = str(text)
        text = re.sub(r"[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]", "", text)
        text = re.sub(r"[\.\,\(\)\s0-9]", "", text)
        return text

    def find_amount(account_names, df_target, sj_div=None):
        """
        계정명 후보군 중 매칭되는 첫 값 반환
        sj_div 지정 시 해당 재무제표 구분(BS/IS/CF)에서만 검색 (정확도 향상)
        """
        search_df = df_target
        if sj_div and "sj_div" in df_target.columns:
            filtered = df_target[df_target["sj_div"] == sj_div]
            if len(filtered) > 0:
                search_df = filtered

        # 1차: 원본 텍스트 포함 검색
        for acc_name in account_names:
            row = search_df[search_df["account_nm"].str.contains(acc_name, na=False, regex=False)]
            if len(row) > 0:
                try:
                    val = row.iloc[0]["thstrm_amount"]
                    val = str(val).replace(",", "")
                    return float(val) if val and val != "-" else None
                except:
                    continue

        # 2차: 정규화 후 검색 (로마숫자/공백 제거)
        search_df_norm = search_df.copy()
        search_df_norm["__norm"] = search_df_norm["account_nm"].apply(normalize)
        for acc_name in account_names:
            norm_target = normalize(acc_name)
            row = search_df_norm[search_df_norm["__norm"].str.contains(norm_target, na=False, regex=False)]
            if len(row) > 0:
                try:
                    val = row.iloc[0]["thstrm_amount"]
                    val = str(val).replace(",", "")
                    return float(val) if val and val != "-" else None
                except:
                    continue
        return None

    # 손익계산서 항목
    metrics["매출액"]     = find_amount(["매출액", "영업수익"], fs_pref)
    metrics["영업이익"]   = find_amount(["영업이익", "영업손익"], fs_pref)
    metrics["당기순이익"] = find_amount(["당기순이익", "당기순손익", "분기순이익"], fs_pref)

    # 재무상태표 항목
    metrics["자산총계"]   = find_amount(["자산총계"], fs_pref)
    metrics["부채총계"]   = find_amount(["부채총계"], fs_pref)
    metrics["자본총계"]   = find_amount(["자본총계"], fs_pref)
    metrics["유동자산"]   = find_amount(["유동자산"], fs_pref)
    metrics["유동부채"]   = find_amount(["유동부채"], fs_pref)
    metrics["이익잉여금"] = find_amount(["이익잉여금"], fs_pref)
    metrics["자본금"]     = find_amount(["자본금"], fs_pref)

    # 현금흐름표 항목 (sj_div="CF"로 한정해서 정확도 향상)
    metrics["영업활동현금흐름"] = find_amount(
        ["영업활동으로인한현금흐름", "영업활동현금흐름", "영업활동으로부터의현금흐름", "영업활동"],
        fs_pref, sj_div="CF")
    metrics["투자활동현금흐름"] = find_amount(
        ["투자활동으로인한현금흐름", "투자활동현금흐름", "투자활동으로부터의현금흐름", "투자활동"],
        fs_pref, sj_div="CF")
    metrics["재무활동현금흐름"] = find_amount(
        ["재무활동으로인한현금흐름", "재무활동현금흐름", "재무활동으로부터의현금흐름", "재무활동"],
        fs_pref, sj_div="CF")

    # sj_div 컬럼이 없거나 CF 매칭 실패 시 전체 범위에서 재검색 (안전망)
    if metrics["영업활동현금흐름"] is None:
        metrics["영업활동현금흐름"] = find_amount(["영업활동으로인한현금흐름", "영업활동현금흐름", "영업활동"], fs_pref)
    if metrics["투자활동현금흐름"] is None:
        metrics["투자활동현금흐름"] = find_amount(["투자활동으로인한현금흐름", "투자활동현금흐름", "투자활동"], fs_pref)
    if metrics["재무활동현금흐름"] is None:
        metrics["재무활동현금흐름"] = find_amount(["재무활동으로인한현금흐름", "재무활동현금흐름", "재무활동"], fs_pref)

    return metrics

# =====================================================
# 재무 건전성 판정 로직
# =====================================================
def evaluate_health(metrics, current_price, shares_outstanding=None):
    """
    수집된 재무지표로 건전성 점수 + 신호등 산출
    100점 만점
    """
    if metrics is None:
        return {
            "점수": None, "등급": "❓ 데이터없음", "색상": "#888",
            "세부": [], "부채비율": None, "유보율": None,
            "현금흐름패턴": "확인불가", "PER": None, "PBR": None,
        }

    score = 0
    max_score = 100
    details = []

    부채총계 = metrics.get("부채총계")
    자본총계 = metrics.get("자본총계")
    자본금   = metrics.get("자본금")
    이익잉여금 = metrics.get("이익잉여금")
    영업이익 = metrics.get("영업이익")
    당기순이익 = metrics.get("당기순이익")
    영업CF = metrics.get("영업활동현금흐름")
    투자CF = metrics.get("투자활동현금흐름")
    재무CF = metrics.get("재무활동현금흐름")

    # ① 부채비율 (20점)
    부채비율 = None
    if 부채총계 is not None and 자본총계 not in (None, 0):
        부채비율 = round(부채총계/자본총계*100, 1)
        if 부채비율 <= 100:
            score += 20; details.append(f"✅ 부채비율 {부채비율}% (100%이하 우량)")
        elif 부채비율 <= 200:
            score += 10; details.append(f"🟡 부채비율 {부채비율}% (200%미만, 주의)")
        else:
            score += 0; details.append(f"🔴 부채비율 {부채비율}% (200%초과, 위험!)")
    else:
        details.append("❓ 부채비율 계산불가")

    # ② 유보율 (15점)
    유보율 = None
    if 이익잉여금 is not None and 자본금 not in (None, 0):
        유보율 = round(이익잉여금/자본금*100, 1)
        if 유보율 >= 1000:
            score += 15; details.append(f"✅ 유보율 {유보율:,.0f}% (곳간 두둑함)")
        elif 유보율 >= 300:
            score += 8; details.append(f"🟡 유보율 {유보율:,.0f}% (보통)")
        else:
            score += 0; details.append(f"🔴 유보율 {유보율:,.0f}% (증자/CB 리스크 주의)")
    else:
        details.append("❓ 유보율 계산불가")

    # ③ 영업이익 vs 순이익 괴리 (15점)
    if 영업이익 is not None and 당기순이익 is not None and 영업이익 != 0:
        괴리율 = round((영업이익 - 당기순이익) / abs(영업이익) * 100, 1)
        if 영업이익 > 0 and 당기순이익 > 0 and 괴리율 < 30:
            score += 15; details.append(f"✅ 영업이익→순이익 전환 양호 (괴리 {괴리율}%)")
        elif 영업이익 > 0 and 당기순이익 > 0:
            score += 8; details.append(f"🟡 이자비용 등으로 괴리 큼 ({괴리율}%)")
        elif 영업이익 > 0 and 당기순이익 <= 0:
            score += 0; details.append("🔴 영업이익 흑자인데 순이익 적자 (이자/일회성비용 의심)")
        else:
            score += 0; details.append("🔴 영업적자 상태")
    else:
        details.append("❓ 이익 괴리 계산불가")

    # ④ 현금흐름 패턴 (25점) — 가장 중요한 지표
    cf_pattern = "확인불가"
    if 영업CF is not None and 투자CF is not None and 재무CF is not None:
        if 영업CF > 0 and 투자CF < 0 and 재무CF < 0:
            cf_pattern = "🟢 우량형 (벌어서 투자, 빚 갚음)"
            score += 25; details.append(cf_pattern)
        elif 영업CF > 0 and 투자CF < 0:
            cf_pattern = "🟡 성장형 (벌어서 투자 확대, 자금조달 동반)"
            score += 18; details.append(cf_pattern)
        elif 영업CF < 0 and (투자CF > 0 or 재무CF > 0):
            cf_pattern = "🔴 좀비형 (장사 부진, 자산매각/차입 의존)"
            score += 0; details.append(cf_pattern)
        else:
            cf_pattern = "🟡 혼재형 (추가 확인 필요)"
            score += 10; details.append(cf_pattern)
    else:
        details.append("❓ 현금흐름 데이터 일부 누락")

    # ⑤ 유동비율 (10점)
    유동자산 = metrics.get("유동자산")
    유동부채 = metrics.get("유동부채")
    if 유동자산 is not None and 유동부채 not in (None, 0):
        유동비율 = round(유동자산/유동부채*100, 1)
        if 유동비율 >= 150:
            score += 10; details.append(f"✅ 유동비율 {유동비율}% (단기지급능력 양호)")
        elif 유동비율 >= 100:
            score += 5; details.append(f"🟡 유동비율 {유동비율}% (보통)")
        else:
            score += 0; details.append(f"🔴 유동비율 {유동비율}% (단기 유동성 위험)")

    # ⑥ 밸류에이션 PER/PBR (15점) — 현재가 필요
    PER = PBR = None
    if current_price and shares_outstanding and 당기순이익 and 자본총계:
        eps = 당기순이익 / shares_outstanding if shares_outstanding else None
        bps = 자본총계 / shares_outstanding if shares_outstanding else None
        if eps and eps > 0:
            PER = round(current_price / eps, 1)
        if bps and bps > 0:
            PBR = round(current_price / bps, 2)

        if PER is not None:
            if PER <= 10:
                score += 8; details.append(f"✅ PER {PER}배 (저평가)")
            elif PER <= 20:
                score += 4; details.append(f"🟡 PER {PER}배 (적정)")
            else:
                score += 0; details.append(f"🔴 PER {PER}배 (고평가)")
        if PBR is not None:
            if PBR <= 1:
                score += 7; details.append(f"✅ PBR {PBR}배 (청산가치 이하)")
            elif PBR <= 3:
                score += 3; details.append(f"🟡 PBR {PBR}배 (적정)")
            else:
                score += 0; details.append(f"🔴 PBR {PBR}배 (고평가)")
    else:
        details.append("❓ PER/PBR 계산 불가 (발행주식수 데이터 필요)")

    # 등급 산정
    if score >= 80:
        grade, color = "🟢 우량 (보유 안심)", "#27ae60"
    elif score >= 60:
        grade, color = "🟡 양호 (보유 유지)", "#f39c12"
    elif score >= 40:
        grade, color = "🟠 주의 (모니터링 필요)", "#e67e22"
    else:
        grade, color = "🔴 위험 (재검토 필요)", "#e74c3c"

    return {
        "점수": score, "등급": grade, "색상": color, "세부": details,
        "부채비율": 부채비율, "유보율": 유보율,
        "현금흐름패턴": cf_pattern, "PER": PER, "PBR": PBR,
    }

# =====================================================
# 발행주식수 조회 (PER/PBR 계산용)
# =====================================================
def get_shares_outstanding(dart, stock_code):
    """
    발행주식수 조회 (PER/PBR 계산용)
    DART의 report() API로 정기보고서 내 '주식의 총수 현황' 조회
    """
    year, reprt_code = get_latest_report_params()

    try:
        # 주식의 총수 현황 보고서 조회
        df = dart.report(stock_code, '주식의총수', year)
        if df is not None and len(df) > 0:
            # '발행주식총수' 또는 '유통주식수' 컬럼에서 보통주 기준 찾기
            for col in ["istc_totqy", "now_to_isu_stock_totqy"]:
                if col in df.columns:
                    row = df[df["se"].astype(str).str.contains("합계|보통주", na=False, regex=True)]
                    if len(row) > 0:
                        val = str(row.iloc[0][col]).replace(",", "")
                        if val and val != "-":
                            return float(val)
        return None
    except Exception:
        return None

# =====================================================
# 메인: 보유 종목 전체 건전성 진단
# =====================================================
def diagnose_portfolio_health(holdings, current_prices=None):
    """
    holdings: [(code, name, qty, avg, market), ...]
    current_prices: {code: 실시간현재가} 딕셔너리 (옵션)
                     없으면 평단가로 PER/PBR 계산 (참고용 근사치)
    한국 종목(KR, ETF_KR)만 DART 분석 대상 (ETF/해외주는 제외)
    """
    print("🏥 보유 종목 재무 건전성 진단 시작...")
    current_prices = current_prices or {}

    try:
        dart = get_dart_reader()
    except Exception as e:
        print(f"⚠️ DART 연동 실패: {e}")
        return []

    results = []
    for code, name, qty, avg, market in holdings:
        # ETF는 재무제표가 없으므로 건너뜀
        if market == "ETF_KR" or market == "US":
            continue

        print(f"  → {name} 재무 분석 중...")
        try:
            df, year, reprt_code = get_financial_data(dart, code, name)
            metrics = extract_metrics(df)
            shares = get_shares_outstanding(dart, code)
            price_for_valuation = current_prices.get(code) or avg
            health = evaluate_health(metrics, current_price=price_for_valuation, shares_outstanding=shares)

            results.append({
                "종목코드": code, "종목명": name,
                "보고서연도": year, "보고서종류": reprt_code,
                "매출액": metrics.get("매출액") if metrics else None,
                "영업이익": metrics.get("영업이익") if metrics else None,
                "당기순이익": metrics.get("당기순이익") if metrics else None,
                **health,
            })
        except Exception as e:
            print(f"    ⚠️ {name} 분석 실패: {e}")
            results.append({
                "종목코드": code, "종목명": name,
                "점수": None, "등급": "❓ 분석실패", "색상": "#888",
                "세부": [f"오류: {e}"], "부채비율": None, "유보율": None,
                "현금흐름패턴": "확인불가", "PER": None, "PBR": None,
                "매출액": None, "영업이익": None, "당기순이익": None,
            })

    results.sort(key=lambda x: (x["점수"] is None, -(x["점수"] or 0)))
    return results

if __name__ == "__main__":
    # 단독 실행 테스트
    test_holdings = [
        ("005930","삼성전자",4,60100,"KR"),
        ("000660","SK하이닉스",1,2245000,"KR"),
        ("005490","POSCO홀딩스",10,424550,"KR"),
        ("247540","에코프로비엠",8,235750,"KR"),
    ]
    results = diagnose_portfolio_health(test_holdings)
    for r in results:
        print(f"\n{r['종목명']}: {r['등급']} ({r['점수']}점)")
        for d in r['세부']:
            print(f"  {d}")

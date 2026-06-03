# sector_screener.py
# 탑다운 섹터 스크리너
# 유동성 점수 → 섹터 선택 → 종목 발굴
# pip install requests yfinance pandas

import requests
import yfinance as yf
import pandas as pd
import os
import datetime as dt

KST = dt.timezone(dt.timedelta(hours=9))
APP_KEY    = os.environ.get("APP_KEY", "")
APP_SECRET = os.environ.get("APP_SECRET", "")

# =====================================================
# 전체 섹터 & 종목 정의 (23개 섹터)
# =====================================================
SECTORS = {
    # ── 조류 (구조적 성장) ──────────────────────────
    "AI/반도체": {
        "type": "조류",
        "stocks": [
            ("005930", "삼성전자"),
            ("000660", "SK하이닉스"),
            ("042700", "한미반도체"),
            ("007660", "이수페타시스"),
            ("058470", "리노공업"),
            ("403870", "HPSP"),
            ("036830", "솔브레인"),
            ("240810", "원익IPS"),
            ("131290", "피에스케이"),
        ]
    },
    "전력/전기인프라": {
        "type": "조류",
        "stocks": [
            ("010120", "LS ELECTRIC"),
            ("103590", "일진전기"),
            ("267270", "HD현대일렉트릭"),
            ("094830", "현대일렉트릭"),
            ("033100", "제룡전기"),
            ("094870", "효성중공업"),
        ]
    },
    "로봇/자동화": {
        "type": "조류",
        "stocks": [
            ("454910", "두산로보틱스"),
            ("277810", "레인보우로보틱스"),
            ("064350", "현대로템"),
            ("031860", "에스피지"),
            ("377340", "티로보틱스"),
        ]
    },
    "방산/우주": {
        "type": "조류",
        "stocks": [
            ("012450", "한화에어로스페이스"),
            ("079550", "LIG넥스원"),
            ("064350", "현대로템"),
            ("047810", "한국항공우주"),
            ("065650", "빅텍"),
        ]
    },
    "바이오/헬스케어/제약/의료기기": {
        "type": "조류",
        "stocks": [
            ("207940", "삼성바이오로직스"),
            ("068270", "셀트리온"),
            ("000100", "유한양행"),
            ("128940", "한미약품"),
            ("003850", "보령"),
            ("185750", "종근당"),
            ("009290", "광동제약"),
            ("041830", "인바디"),
            ("100120", "뷰웍스"),
        ]
    },
    "AI소프트웨어": {
        "type": "조류",
        "stocks": [
            ("035420", "NAVER"),
            ("035720", "카카오"),
            ("304100", "솔트룩스"),
            ("208370", "셀바스AI"),
            ("357550", "마인즈랩"),
        ]
    },
    "원전/신재생에너지": {
        "type": "조류",
        "stocks": [
            ("034020", "두산에너빌리티"),
            ("130660", "한전기술"),
            ("099220", "비에이치아이"),
            ("112610", "씨에스윈드"),
            ("100130", "동국S&C"),
        ]
    },
    "사이버보안": {
        "type": "조류",
        "stocks": [
            ("053800", "안랩"),
            ("067920", "이글루시큐리티"),
            ("263800", "드림시큐리티"),
            ("147970", "파이오링크"),
        ]
    },
    "2차전지소재": {
        "type": "조류",
        "stocks": [
            ("247540", "에코프로비엠"),
            ("003670", "포스코퓨처엠"),
            ("066970", "엘앤에프"),
            ("336370", "솔루스첨단소재"),
            ("278280", "천보"),
        ]
    },
    "게임/콘텐츠": {
        "type": "조류",
        "stocks": [
            ("259960", "크래프톤"),
            ("251270", "넷마블"),
            ("036570", "엔씨소프트"),
            ("352820", "하이브"),
            ("041510", "SM엔터"),
        ]
    },

    # ── 파도 (경기 사이클) ──────────────────────────
    "조선/해운": {
        "type": "파도",
        "stocks": [
            ("329180", "HD현대중공업"),
            ("042660", "한화오션"),
            ("010140", "삼성중공업"),
            ("011200", "HMM"),
            ("028670", "팬오션"),
        ]
    },
    "소재/화학": {
        "type": "파도",
        "stocks": [
            ("005490", "POSCO홀딩스"),
            ("051910", "LG화학"),
            ("011170", "롯데케미칼"),
            ("011780", "금호석유"),
            ("004800", "효성"),
        ]
    },
    "금융/보험/증권": {
        "type": "파도",
        "stocks": [
            ("105560", "KB금융"),
            ("055550", "신한지주"),
            ("086790", "하나금융"),
            ("000810", "삼성화재"),
            ("138040", "메리츠금융"),
            ("006800", "미래에셋증권"),
            ("016360", "삼성증권"),
        ]
    },
    "자동차/부품": {
        "type": "파도",
        "stocks": [
            ("005380", "현대차"),
            ("000270", "기아"),
            ("012330", "현대모비스"),
            ("018880", "한온시스템"),
            ("204320", "만도"),
        ]
    },
    "철강/금속": {
        "type": "파도",
        "stocks": [
            ("004020", "현대제철"),
            ("010130", "고려아연"),
            ("103140", "풍산"),
            ("001430", "세아베스틸"),
        ]
    },
    "에너지/정유": {
        "type": "파도",
        "stocks": [
            ("096770", "SK이노베이션"),
            ("010950", "S-Oil"),
            ("078930", "GS"),
            ("036460", "한국가스공사"),
        ]
    },
    "건설/부동산": {
        "type": "파도",
        "stocks": [
            ("000720", "현대건설"),
            ("006360", "GS건설"),
            ("001880", "DL이앤씨"),
            ("047040", "대우건설"),
            ("294870", "HDC현대산업개발"),
        ]
    },
    "디스플레이/가전": {
        "type": "파도",
        "stocks": [
            ("066570", "LG전자"),
            ("034220", "LG디스플레이"),
            ("009150", "삼성전기"),
            ("006400", "삼성SDI"),
        ]
    },
    "물류/운송/항공": {
        "type": "파도",
        "stocks": [
            ("000120", "CJ대한통운"),
            ("002320", "한진"),
            ("086280", "현대글로비스"),
            ("003490", "대한항공"),
            ("020560", "아시아나항공"),
        ]
    },

    # ── 방어 (경기 무관) ──────────────────────────
    "필수소비재/식품": {
        "type": "방어",
        "stocks": [
            ("097950", "CJ제일제당"),
            ("271560", "오리온"),
            ("004370", "농심"),
            ("000080", "하이트진로"),
            ("280360", "롯데웰푸드"),
        ]
    },
    "통신": {
        "type": "방어",
        "stocks": [
            ("017670", "SK텔레콤"),
            ("030200", "KT"),
            ("032640", "LG유플러스"),
        ]
    },
    "유틸리티/인프라": {
        "type": "방어",
        "stocks": [
            ("015760", "한국전력"),
            ("036460", "한국가스공사"),
            ("071320", "지역난방공사"),
        ]
    },
    "유통/리테일": {
        "type": "방어",
        "stocks": [
            ("139480", "이마트"),
            ("027410", "BGF리테일"),
            ("007070", "GS리테일"),
            ("004170", "신세계"),
            ("023530", "롯데쇼핑"),
        ]
    },
}

# =====================================================
# 유동성 점수에 따른 추천 섹터 결정
# =====================================================
def get_recommended_sectors(liquidity_score):
    """
    유동성 점수 → 추천 섹터 목록 반환
    70점 이상: 조류 전체 + 파도 일부
    50~70점: 조류 우선 + 방어 일부
    50점 미만: 방어 전체 + 조류 일부
    """
    if liquidity_score >= 70:
        # 성장주 우위 → 조류 전체 + 파도 경기민감
        recommended = []
        priority = []
        for name, info in SECTORS.items():
            if info["type"] == "조류":
                priority.append(name)
            elif info["type"] == "파도" and name in ["조선/해운","자동차/부품","금융/보험/증권"]:
                recommended.append(name)
        return priority + recommended, "🟢 성장주 우위 — 조류 섹터 집중"

    elif liquidity_score >= 50:
        # 중립 → 조류 우선, 방어 일부
        recommended = []
        priority = []
        for name, info in SECTORS.items():
            if info["type"] == "조류" and name in [
                "AI/반도체","전력/전기인프라","바이오/헬스케어/제약/의료기기","방산/우주"
            ]:
                priority.append(name)
            elif info["type"] == "방어":
                recommended.append(name)
        return priority + recommended, "🟡 중립 — 핵심 조류 + 방어 혼합"

    else:
        # 방어주 우위 → 방어 전체 + 조류 일부만
        recommended = []
        priority = []
        for name, info in SECTORS.items():
            if info["type"] == "방어":
                priority.append(name)
            elif info["type"] == "조류" and name in [
                "바이오/헬스케어/제약/의료기기","AI/반도체"
            ]:
                recommended.append(name)
        return priority + recommended, "🔴 방어주 우위 — 방어 섹터 집중"

# =====================================================
# 국내주식 현재가 조회
# =====================================================
def get_kr_price(token, code):
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY, "appsecret": APP_SECRET,
        "tr_id": "FHKST01010100",
    }
    try:
        res    = requests.get(url, headers=headers,
            params={"FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":code}, timeout=10)
        output = res.json().get("output",{})
        return (
            int(output.get("stck_prpr",0)),
            float(output.get("prdy_ctrt",0)),
            int(output.get("acml_vol",0)),
            int(output.get("w52_hgpr",0)),
            int(output.get("w52_lwpr",0)),
        )
    except:
        return 0,0,0,0,0

# =====================================================
# RSI 계산
# =====================================================
def get_rsi(code, period=14):
    try:
        hist = yf.Ticker(code+".KS").history(period="2mo").dropna()
        if len(hist) < period+1: return 50
        delta = hist["Close"].diff()
        gain  = delta.where(delta>0,0).rolling(period).mean()
        loss  = (-delta.where(delta<0,0)).rolling(period).mean()
        rs    = gain/loss
        return round((100-(100/(1+rs))).iloc[-1],1)
    except:
        return 50

# =====================================================
# 골든크로스 확인
# =====================================================
def get_ma_signal(code):
    try:
        hist = yf.Ticker(code+".KS").history(period="4mo").dropna()
        if len(hist) < 60: return "-"
        ma20 = hist["Close"].rolling(20).mean().iloc[-1]
        ma60 = hist["Close"].rolling(60).mean().iloc[-1]
        curr = hist["Close"].iloc[-1]
        if ma20>ma60 and curr>ma20:   return "골든크로스"
        elif ma20<ma60 and curr<ma20: return "데드크로스"
        elif curr>ma20>ma60:          return "상승추세"
        elif curr<ma20:               return "20일선하회"
        return "횡보"
    except:
        return "-"

# =====================================================
# 터틀 신호
# =====================================================
def get_turtle_signal(code, price):
    try:
        hist  = yf.Ticker(code+".KS").history(period="2mo").dropna()
        if len(hist) < 20: return "-", 0
        high20 = int(hist["High"].tail(20).max())
        low20  = int(hist["Low"].tail(20).min())
        curr   = price or int(hist["Close"].iloc[-1])
        if curr >= high20:   return "매수신호", high20
        elif curr <= low20:  return "매도신호", low20
        else:
            gap = round((high20-curr)/curr*100,1)
            return f"대기({gap}%)", high20
    except:
        return "-", 0

# =====================================================
# 섹터별 종목 스크리닝
# =====================================================
def screen_sector(token, sector_name, sector_info, total_assets=24_000_000):
    """섹터 내 종목 스크리닝"""
    results = []
    max_loss = total_assets * 0.02

    for code, name in sector_info["stocks"]:
        price,rate,volume,high52,low52 = get_kr_price(token, code)
        if price == 0: continue

        score  = 0
        reason = []

        rsi = get_rsi(code)
        ma  = get_ma_signal(code)
        turtle_sig, turtle_price = get_turtle_signal(code, price)

        # RSI 점수
        if rsi <= 30:   score+=30; reason.append(f"RSI극과매도({rsi})")
        elif rsi <= 40: score+=20; reason.append(f"RSI과매도({rsi})")
        elif rsi >= 70: score-=20; reason.append(f"RSI과매수({rsi})")

        # MA 점수
        if ma == "골든크로스":   score+=25; reason.append("골든크로스")
        elif ma == "상승추세":   score+=15; reason.append("상승추세")
        elif ma == "데드크로스": score-=20; reason.append("데드크로스")

        # 터틀 점수
        if "매수신호" in turtle_sig: score+=25; reason.append("터틀매수")
        elif "매도신호" in turtle_sig: score-=20

        # 거래량 점수
        if volume >= 1_000_000: score+=15; reason.append("거래량풍부")
        elif volume >= 500_000: score+=8

        # 52주 저가 근접
        if low52 > 0 and (price-low52)/low52*100 <= 20:
            score+=15; reason.append("52주저가근접")

        # 눌림목
        if high52 > 0 and -20 <= (price-high52)/high52*100 <= -5:
            score+=10; reason.append("눌림목")

        # 추천 투자금 (2% 룰)
        try:
            hist  = yf.Ticker(code+".KS").history(period="2mo").dropna()
            low20 = int(hist["Low"].tail(20).min()) if len(hist)>=20 else int(price*0.95)
            loss_pct = (price-low20)/price*100 if price>low20 else 2
            rec_buy = int(max_loss/(loss_pct/100)) if loss_pct>0 else 0
        except:
            rec_buy = 0

        results.append({
            "섹터":     sector_name,
            "섹터타입": sector_info["type"],
            "종목명":   name,
            "종목코드": code,
            "현재가":   price,
            "등락률":   rate,
            "RSI":      rsi,
            "MA신호":   ma,
            "터틀신호": turtle_sig,
            "점수":     score,
            "근거":     ", ".join(reason) if reason else "신호없음",
            "추천투자금": rec_buy,
        })

    return sorted(results, key=lambda x: x["점수"], reverse=True)

# =====================================================
# 탑다운 전체 스크리닝
# =====================================================
def run_topdown_screener(token, liquidity_score):
    """
    탑다운 방식 전체 스크리닝
    유동성 점수 → 섹터 선택 → 종목 발굴
    """
    print(f"\n🔍 탑다운 스크리너 실행 (유동성 점수: {liquidity_score}점)")

    recommended_sectors, phase_msg = get_recommended_sectors(liquidity_score)
    print(f"📊 시장 국면: {phase_msg}")
    print(f"✅ 추천 섹터: {', '.join(recommended_sectors[:5])} 외 {max(0,len(recommended_sectors)-5)}개")

    all_results = []
    for sector_name in recommended_sectors[:8]:  # 상위 8개 섹터만
        if sector_name not in SECTORS: continue
        print(f"  → {sector_name} 스크리닝 중...")
        results = screen_sector(token, sector_name, SECTORS[sector_name])
        all_results.extend(results[:2])  # 섹터당 상위 2개

    # 전체 점수순 정렬
    all_results = sorted(all_results, key=lambda x: x["점수"], reverse=True)
    return all_results[:10], recommended_sectors, phase_msg

# =====================================================
# 섹터별 ETF 매핑 (참고용)
# =====================================================
SECTOR_ETF = {
    "AI/반도체":        ("SOL AI반도체TOP2플러스", "0167A0"),
    "전력/전기인프라":  ("KODEX AI전력핵심설비", "487240"),
    "로봇/자동화":      ("KODEX 로봇액티브", "445290"),
    "방산/우주":        ("TIGER 방산&우주ETF", "-"),
    "바이오/헬스케어/제약/의료기기": ("TIGER 바이오TOP10", "364970"),
    "AI소프트웨어":     ("TIGER 글로벌AI&로보틱스INDXX", "464310"),
    "2차전지소재":      ("TIGER 2차전지테마", "-"),
    "게임/콘텐츠":      ("TIGER 미디어컨텐츠", "-"),
}

if __name__ == "__main__":
    print("섹터 스크리너 모듈 로드 완료")
    print(f"총 섹터 수: {len(SECTORS)}개")
    for stype in ["조류","파도","방어"]:
        cnt = sum(1 for s in SECTORS.values() if s["type"]==stype)
        print(f"  {stype}: {cnt}개")

"""
Mini ERP 가상 데이터 생성기
=========================================================
가상의 청주 소재 전자부품 제조사의 2년치(2024-01-01 ~ 2025-12-31)
영업·구매·생산·재고 데이터를 만든다. 등장하는 회사명·인명은 모두 가상이다.

동작 방식
  1단계(수요): 고객 주문(수주)을 먼저 전부 만든다. 수요는 공급과 무관한 외생 변수.
  2단계(공급): 영업일 단위로 하루씩 진행하며 입고 → 생산 완료 → 생산 착수
              → 출하 → 취소 → 재발주/생산계획 → 재고실사 순서로 처리한다.

지키는 업무 규칙
  - 재고는 어느 시점에도 음수가 되지 않는다 (창고·품목별)
  - 출하 수량 합계 ≤ 수주 수량, 입고 수량 합계 ≤ 발주 수량
  - 생산 착수 시 원자재 출고량 = 생산지시 수량 × BOM 소요량 (정확히 일치)
  - 주말·공휴일에는 거래가 발생하지 않는다
  - seed 고정: 언제 실행해도 같은 데이터

분석용으로 의도적으로 심어둔 패턴 (README에 정리)
  1. 납기 지연 공급업체: Shenzhen Hongda Electronics — 계약 리드타임 21일, 실제 30~42일
  2. 그 여파로 OIS 액추에이터(FG-1007) 등 해당 IC를 쓰는 완제품의 결품·납기 지연
  3. 2025년 3월 신규 해외 고객(Saigon Precision Assembly)의 급성장
  4. 목표 대비 실적이 꾸준히 미달하는 영업담당 1명
  5. 2025년 하반기 단종 수순 품목(FG-1019)의 재고 정체 (갱신 안 된 수요예측)
  6. 2025년 동선(銅線) 매입단가 18% 인상 → 원가 상승
  7. 연말·하반기 성수기, 설·추석 비수기 계절성

사용법:  python generate_data.py        → ./data/*.csv 생성
"""

import csv
import math
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

SEED = 20260828
START = date(2024, 1, 1)
END = date(2025, 12, 31)
OUT = Path(__file__).resolve().parent.parent / "data"

rng = random.Random(SEED)

# ---------------------------------------------------------------------------
# 달력: 주말 + 주요 공휴일(대체·임시공휴일 포함) 제외
# ---------------------------------------------------------------------------
HOLIDAYS = {
    # 2024
    date(2024, 1, 1), date(2024, 2, 9), date(2024, 2, 12), date(2024, 3, 1),
    date(2024, 4, 10), date(2024, 5, 6), date(2024, 5, 15), date(2024, 6, 6),
    date(2024, 8, 15), date(2024, 9, 16), date(2024, 9, 17), date(2024, 9, 18),
    date(2024, 10, 1), date(2024, 10, 3), date(2024, 10, 9), date(2024, 12, 25),
    # 2025
    date(2025, 1, 1), date(2025, 1, 27), date(2025, 1, 28), date(2025, 1, 29),
    date(2025, 1, 30), date(2025, 3, 3), date(2025, 5, 5), date(2025, 5, 6),
    date(2025, 6, 3), date(2025, 6, 6), date(2025, 8, 15), date(2025, 10, 3),
    date(2025, 10, 6), date(2025, 10, 7), date(2025, 10, 8), date(2025, 10, 9),
    date(2025, 12, 25),
}


def is_bday(d):
    return d.weekday() < 5 and d not in HOLIDAYS


def next_bday(d):
    while not is_bday(d):
        d += timedelta(days=1)
    return d


def add_bdays(d, n):
    while n > 0:
        d += timedelta(days=1)
        if is_bday(d):
            n -= 1
    return d


BDAYS = [START + timedelta(days=i) for i in range((END - START).days + 1)]
BDAYS = [d for d in BDAYS if is_bday(d)]

# 월별 계절 지수 (모바일 신제품 출시 전 하반기 성수기, 연초 비수기)
SEASON = [0.85, 0.80, 0.95, 1.00, 1.00, 1.05, 1.10, 1.15, 1.10, 1.05, 1.00, 0.95]
GROWTH = {2024: 1.00, 2025: 1.08}

# ---------------------------------------------------------------------------
# 수량 단위: 재고 계산은 1/1000 단위 정수(milli)로 해서 부동소수 오차를 없앤다
# ---------------------------------------------------------------------------
M = 1000


def fmt_milli(m):
    sign = "-" if m < 0 else ""
    m = abs(m)
    return f"{sign}{m // M}.{m % M:03d}"


# ---------------------------------------------------------------------------
# 1. 기준정보
# ---------------------------------------------------------------------------
SALES_REPS = [
    # rep_id, name, team, hire_date
    (1, "박지훈", "국내영업1팀", date(2014, 3, 3)),
    (2, "이서연", "국내영업1팀", date(2019, 7, 1)),
    (3, "최민석", "국내영업2팀", date(2012, 1, 2)),
    (4, "정다은", "국내영업2팀", date(2022, 2, 7)),   # 목표 미달 패턴
    (5, "한도윤", "해외영업팀", date(2016, 9, 1)),
    (6, "오세린", "해외영업팀", date(2020, 4, 1)),
]
UNDERPERFORMER_REP = 4

WAREHOUSES = [
    (1, "오창 원자재창고", "충북 청주시 청원구 오창읍"),
    (2, "오창 완제품창고", "충북 청주시 청원구 오창읍"),
    (3, "진천 수입자재창고", "충북 진천군 이월면"),
]
WH_RM, WH_FG, WH_IMPORT = 1, 2, 3

SUPPLIERS = [
    # supplier_id, name, country, 계약 리드타임(일), 실제 리드타임 배수(하한, 상한)
    (1, "오창동선(주)", "KR", 5, (0.6, 1.1)),
    (2, "한결마그네틱", "KR", 7, (0.6, 1.1)),
    (3, "세진정밀", "KR", 5, (0.6, 1.1)),
    (4, "미래하우징", "KR", 6, (0.6, 1.1)),
    (5, "청원PCB", "KR", 7, (0.7, 1.15)),
    (6, "동일커넥트", "KR", 4, (0.6, 1.1)),
    (7, "성원화학", "KR", 5, (0.6, 1.1)),
    (8, "우진테크", "KR", 6, (0.6, 1.1)),
    (9, "금강부품", "KR", 3, (0.6, 1.2)),
    (10, "한성패키징", "KR", 3, (0.6, 1.1)),
    (11, "Shenzhen Hongda Electronics", "CN", 21, (1.4, 2.0)),   # 납기 지연 패턴
    (12, "Ningbo Magtech", "CN", 18, (0.75, 1.1)),
    (13, "Taipei Semicon Supply", "TW", 14, (0.9, 1.2)),
    (14, "Osaka Precision Parts", "JP", 10, (0.9, 1.1)),
    (15, "Hanoi Component", "VN", 16, (0.75, 1.15)),
]
LATE_SUPPLIER = 11
SUP = {s[0]: s for s in SUPPLIERS}

# 원자재: code, name, unit, standard_cost, supplier_id, 발주 단위(MOQ, 단위 그대로)
RAW_MATERIALS = [
    ("RM-2001", "에나멜 동선 0.05mm", "KG", 15800, 1, 5),
    ("RM-2002", "에나멜 동선 0.10mm", "KG", 14200, 1, 5),
    ("RM-2003", "네오디뮴 자석 Φ4", "EA", 38, 12, 5000),
    ("RM-2004", "네오디뮴 자석 Φ6", "EA", 55, 12, 5000),
    ("RM-2005", "네오디뮴 자석 Φ10", "EA", 120, 2, 1000),
    ("RM-2006", "페라이트 코어", "EA", 22, 2, 5000),
    ("RM-2007", "편심 분동(텅스텐)", "EA", 64, 3, 5000),
    ("RM-2008", "카본 브러시", "EA", 18, 3, 5000),
    ("RM-2009", "정류자", "EA", 26, 3, 5000),
    ("RM-2010", "샤프트 Φ1.0", "EA", 15, 3, 5000),
    ("RM-2011", "샤프트 Φ2.0", "EA", 24, 3, 2000),
    ("RM-2012", "미니 볼베어링", "EA", 140, 14, 1000),
    ("RM-2013", "SUS 하우징(소)", "EA", 45, 4, 5000),
    ("RM-2014", "SUS 하우징(중)", "EA", 78, 4, 2000),
    ("RM-2015", "알루미늄 하우징", "EA", 210, 4, 1000),
    ("RM-2016", "PCB 기판(소)", "EA", 95, 5, 2000),
    ("RM-2017", "PCB 기판(중)", "EA", 180, 5, 1000),
    ("RM-2018", "FPCB 케이블", "EA", 130, 15, 2000),
    ("RM-2019", "SUS 판스프링", "EA", 12, 9, 10000),
    ("RM-2020", "볼 가이드", "EA", 85, 14, 1000),
    ("RM-2021", "홀 센서 IC", "EA", 260, 13, 1000),
    ("RM-2022", "모터 드라이버 IC", "EA", 420, 11, 1000),
    ("RM-2023", "자이로 센서 IC", "EA", 950, 11, 500),
    ("RM-2024", "MCU", "EA", 1100, 13, 500),
    ("RM-2025", "이미지센서 마운트", "EA", 160, 8, 1000),
    ("RM-2026", "렌즈 캐리어", "EA", 140, 8, 1000),
    ("RM-2027", "커넥터(4핀)", "EA", 35, 6, 5000),
    ("RM-2028", "커넥터(8핀)", "EA", 60, 6, 2000),
    ("RM-2029", "칩 저항 세트", "EA", 8, 15, 10000),
    ("RM-2030", "칩 커패시터 세트", "EA", 10, 15, 10000),
    ("RM-2031", "PBT 수지", "KG", 4200, 7, 25),
    ("RM-2032", "LCP 수지", "KG", 18500, 7, 25),
    ("RM-2033", "에폭시 접착제", "KG", 32000, 7, 5),
    ("RM-2034", "솔더 페이스트", "KG", 85000, 7, 1),
    ("RM-2035", "절연 테이프", "M", 120, 9, 500),
    ("RM-2036", "방진 고무", "EA", 9, 9, 10000),
    ("RM-2037", "실리콘 댐퍼", "EA", 14, 9, 10000),
    ("RM-2038", "리드선", "M", 90, 6, 1000),
    ("RM-2039", "포장 트레이", "EA", 320, 10, 200),
    ("RM-2040", "방습 포장재", "EA", 150, 10, 200),
]
COPPER = {"RM-2001", "RM-2002"}          # 2025년 매입단가 인상 품목

# 완제품: code, name, list_price, 월 기준수요(EA), 생산 리드타임(영업일), 고객 산업군
FINISHED_GOODS = [
    ("FG-1001", "코인형 진동모터 Φ8", 520, 90000, 3, "MOBILE"),
    ("FG-1002", "코인형 진동모터 Φ10", 610, 70000, 3, "MOBILE"),
    ("FG-1003", "리니어 진동모터(LRA)", 1450, 40000, 4, "MOBILE"),
    ("FG-1004", "바형 진동모터", 480, 50000, 3, "APPLIANCE"),
    ("FG-1005", "스테퍼 모터 15mm", 3200, 12000, 5, "AUTO"),
    ("FG-1006", "스테퍼 모터 20mm", 4100, 8000, 5, "AUTO"),
    ("FG-1007", "OIS 액추에이터", 14500, 4000, 6, "MOBILE"),
    ("FG-1008", "AF 액추에이터", 6800, 9000, 5, "MOBILE"),
    ("FG-1009", "카메라 모듈 베이스", 2300, 15000, 4, "MOBILE"),
    ("FG-1010", "홀 센서 모듈", 2900, 12000, 4, "AUTO"),
    ("FG-1011", "BLDC 팬 모터 25mm", 5200, 6000, 5, "APPLIANCE"),
    ("FG-1012", "BLDC 팬 모터 40mm", 7400, 5000, 5, "APPLIANCE"),
    ("FG-1013", "햅틱 드라이버 모듈", 8800, 4000, 5, "MOBILE"),
    ("FG-1014", "차량용 진동모터", 3600, 9000, 4, "AUTO"),
    ("FG-1015", "차량용 스테퍼(HUD)", 12500, 2500, 6, "AUTO"),
    ("FG-1016", "정밀 기어드 모터", 9600, 3000, 6, "APPLIANCE"),
    ("FG-1017", "웨어러블 진동모터", 1900, 15000, 3, "MOBILE"),
    ("FG-1018", "페라이트 코일 모듈", 1100, 25000, 3, "APPLIANCE"),
    ("FG-1019", "DC 브러시 모터 소형", 2100, 10000, 4, "APPLIANCE"),  # 단종 수순
    ("FG-1020", "스마트워치 햅틱 모듈", 6200, 5000, 5, "MOBILE"),
]
DECLINING_ITEM = "FG-1019"

# BOM: 완제품 1개당 원자재 소요량 (소수점 3자리 이내)
BOM = {
    "FG-1001": {"RM-2001": 0.002, "RM-2003": 1, "RM-2007": 1, "RM-2013": 1, "RM-2038": 0.03, "RM-2039": 0.005},
    "FG-1002": {"RM-2001": 0.003, "RM-2004": 1, "RM-2007": 1, "RM-2013": 1, "RM-2038": 0.03, "RM-2039": 0.005},
    "FG-1003": {"RM-2001": 0.003, "RM-2004": 2, "RM-2019": 2, "RM-2013": 1, "RM-2018": 1, "RM-2037": 2, "RM-2039": 0.005},
    "FG-1004": {"RM-2002": 0.004, "RM-2003": 1, "RM-2007": 1, "RM-2008": 2, "RM-2009": 1, "RM-2010": 1, "RM-2039": 0.005},
    "FG-1005": {"RM-2002": 0.012, "RM-2005": 1, "RM-2011": 1, "RM-2012": 2, "RM-2014": 1, "RM-2028": 1, "RM-2040": 0.01},
    "FG-1006": {"RM-2002": 0.018, "RM-2005": 2, "RM-2011": 1, "RM-2012": 2, "RM-2014": 1, "RM-2028": 1, "RM-2040": 0.01},
    "FG-1007": {"RM-2001": 0.004, "RM-2004": 4, "RM-2020": 2, "RM-2023": 1, "RM-2022": 1, "RM-2026": 1, "RM-2018": 1, "RM-2032": 0.002, "RM-2040": 0.01},
    "FG-1008": {"RM-2001": 0.003, "RM-2004": 2, "RM-2019": 2, "RM-2021": 1, "RM-2026": 1, "RM-2018": 1, "RM-2032": 0.002, "RM-2040": 0.01},
    "FG-1009": {"RM-2025": 1, "RM-2032": 0.004, "RM-2033": 0.001, "RM-2016": 1, "RM-2039": 0.005},
    "FG-1010": {"RM-2021": 1, "RM-2016": 1, "RM-2027": 1, "RM-2029": 1, "RM-2030": 1, "RM-2031": 0.005, "RM-2034": 0.001, "RM-2040": 0.01},
    "FG-1011": {"RM-2002": 0.015, "RM-2005": 1, "RM-2021": 1, "RM-2022": 1, "RM-2012": 2, "RM-2017": 1, "RM-2031": 0.02, "RM-2027": 1, "RM-2040": 0.01},
    "FG-1012": {"RM-2002": 0.025, "RM-2005": 2, "RM-2021": 1, "RM-2022": 1, "RM-2012": 2, "RM-2017": 1, "RM-2031": 0.035, "RM-2028": 1, "RM-2040": 0.01},
    "FG-1013": {"RM-2022": 1, "RM-2024": 1, "RM-2017": 1, "RM-2029": 2, "RM-2030": 2, "RM-2028": 1, "RM-2034": 0.002, "RM-2040": 0.01},
    "FG-1014": {"RM-2002": 0.006, "RM-2005": 1, "RM-2007": 1, "RM-2014": 1, "RM-2036": 2, "RM-2027": 1, "RM-2035": 0.1, "RM-2039": 0.005},
    "FG-1015": {"RM-2002": 0.02, "RM-2005": 2, "RM-2011": 1, "RM-2012": 2, "RM-2015": 1, "RM-2021": 1, "RM-2028": 1, "RM-2040": 0.01},
    "FG-1016": {"RM-2002": 0.015, "RM-2005": 1, "RM-2011": 2, "RM-2012": 4, "RM-2015": 1, "RM-2031": 0.03, "RM-2027": 1, "RM-2040": 0.01},
    "FG-1017": {"RM-2001": 0.002, "RM-2003": 1, "RM-2019": 1, "RM-2013": 1, "RM-2018": 1, "RM-2037": 1, "RM-2039": 0.005},
    "FG-1018": {"RM-2002": 0.008, "RM-2006": 2, "RM-2016": 1, "RM-2035": 0.2, "RM-2038": 0.1, "RM-2039": 0.005},
    "FG-1019": {"RM-2002": 0.01, "RM-2005": 1, "RM-2008": 2, "RM-2009": 1, "RM-2011": 1, "RM-2014": 1, "RM-2038": 0.2, "RM-2039": 0.005},
    "FG-1020": {"RM-2001": 0.003, "RM-2004": 2, "RM-2019": 2, "RM-2022": 1, "RM-2016": 1, "RM-2018": 1, "RM-2037": 2, "RM-2040": 0.01},
}

# 고객: name, country, segment, 산업군, rep_id, 규모 가중치, 거래 시작일, 할인율
CUSTOMERS = [
    # 국내 모바일 (국내영업1팀)
    ("한빛모바일", "KR", "DOMESTIC", "MOBILE", 1, 10.0, date(2016, 4, 1), 0.08),
    ("누리디바이스", "KR", "DOMESTIC", "MOBILE", 1, 6.5, date(2018, 2, 1), 0.06),
    ("서진텔레콤부품", "KR", "DOMESTIC", "MOBILE", 2, 5.0, date(2017, 9, 1), 0.05),
    ("가온스마트", "KR", "DOMESTIC", "MOBILE", 2, 4.2, date(2019, 5, 1), 0.05),
    ("대명옵틱스", "KR", "DOMESTIC", "MOBILE", 1, 3.6, date(2015, 3, 1), 0.04),
    ("하늘카메라모듈", "KR", "DOMESTIC", "MOBILE", 2, 3.0, date(2020, 1, 1), 0.04),
    ("새롬웨어러블", "KR", "DOMESTIC", "MOBILE", 1, 2.4, date(2021, 6, 1), 0.03),
    ("에이스터치", "KR", "DOMESTIC", "MOBILE", 2, 2.0, date(2019, 11, 1), 0.03),
    ("솔빛전자", "KR", "DOMESTIC", "MOBILE", 1, 1.6, date(2022, 3, 1), 0.02),
    ("민트디스플레이", "KR", "DOMESTIC", "MOBILE", 2, 1.2, date(2023, 2, 1), 0.02),
    # 국내 자동차 (국내영업2팀)
    ("대성오토텍", "KR", "DOMESTIC", "AUTO", 3, 7.0, date(2013, 5, 1), 0.07),
    ("한라모빌리티부품", "KR", "DOMESTIC", "AUTO", 3, 5.5, date(2014, 8, 1), 0.06),
    ("미래전장", "KR", "DOMESTIC", "AUTO", 4, 3.8, date(2018, 10, 1), 0.04),
    ("청주카일렉트릭", "KR", "DOMESTIC", "AUTO", 3, 3.2, date(2016, 1, 1), 0.04),
    ("동해오토파츠", "KR", "DOMESTIC", "AUTO", 4, 2.5, date(2020, 7, 1), 0.03),
    ("세종모터스부품", "KR", "DOMESTIC", "AUTO", 4, 2.0, date(2021, 4, 1), 0.02),
    ("유성차량전자", "KR", "DOMESTIC", "AUTO", 3, 1.5, date(2022, 9, 1), 0.02),
    ("광명HUD", "KR", "DOMESTIC", "AUTO", 4, 1.2, date(2023, 5, 1), 0.02),
    # 국내 가전 (국내영업2팀)
    ("한결가전", "KR", "DOMESTIC", "APPLIANCE", 3, 6.0, date(2012, 6, 1), 0.06),
    ("푸른공조", "KR", "DOMESTIC", "APPLIANCE", 4, 4.0, date(2017, 3, 1), 0.05),
    ("다온홈테크", "KR", "DOMESTIC", "APPLIANCE", 4, 3.0, date(2019, 8, 1), 0.04),
    ("에코쿨링", "KR", "DOMESTIC", "APPLIANCE", 3, 2.4, date(2018, 12, 1), 0.03),
    ("신우전기", "KR", "DOMESTIC", "APPLIANCE", 4, 2.0, date(2016, 10, 1), 0.03),
    ("오창정밀기기", "KR", "DOMESTIC", "APPLIANCE", 3, 1.6, date(2020, 2, 1), 0.02),
    ("바른로봇", "KR", "DOMESTIC", "APPLIANCE", 4, 1.4, date(2022, 1, 1), 0.02),
    ("늘봄헬스케어", "KR", "DOMESTIC", "APPLIANCE", 4, 1.0, date(2023, 8, 1), 0.01),
    ("태광소형모터", "KR", "DOMESTIC", "APPLIANCE", 3, 1.0, date(2021, 11, 1), 0.01),
    ("하나공기청정", "KR", "DOMESTIC", "APPLIANCE", 4, 0.8, date(2023, 10, 1), 0.01),
    # 해외 (해외영업팀)
    ("Hanoi Mobile Assembly", "VN", "OVERSEAS", "MOBILE", 5, 8.0, date(2017, 5, 1), 0.07),
    ("Bac Ninh Electronics", "VN", "OVERSEAS", "MOBILE", 5, 5.0, date(2019, 3, 1), 0.05),
    ("Saigon Precision Assembly", "VN", "OVERSEAS", "MOBILE", 6, 0.0, date(2025, 3, 3), 0.04),  # 신규·급성장
    ("Noida Device Works", "IN", "OVERSEAS", "MOBILE", 6, 3.5, date(2020, 6, 1), 0.04),
    ("Chennai Handset Parts", "IN", "OVERSEAS", "MOBILE", 6, 2.0, date(2022, 4, 1), 0.03),
    ("Suzhou Optical Module", "CN", "OVERSEAS", "MOBILE", 5, 3.0, date(2018, 7, 1), 0.04),
    ("Tianjin Auto Electronics", "CN", "OVERSEAS", "AUTO", 5, 2.8, date(2019, 9, 1), 0.04),
    ("Monterrey Auto Systems", "MX", "OVERSEAS", "AUTO", 6, 2.5, date(2021, 1, 1), 0.03),
    ("Detroit Mobility Parts", "US", "OVERSEAS", "AUTO", 6, 2.0, date(2020, 10, 1), 0.03),
    ("Stuttgart Fahrzeugtechnik", "DE", "OVERSEAS", "AUTO", 5, 1.8, date(2021, 8, 1), 0.02),
    ("Penang Home Appliance", "MY", "OVERSEAS", "APPLIANCE", 6, 1.5, date(2022, 6, 1), 0.02),
    ("Bangkok Cooling Tech", "TH", "OVERSEAS", "APPLIANCE", 5, 1.2, date(2023, 3, 1), 0.02),
]
NEW_CUSTOMER = "Saigon Precision Assembly"


def r3(x):
    """소요량을 소수점 3자리 milli 정수로"""
    return int(round(x * M))


# ---------------------------------------------------------------------------
# 품목 마스터 만들기
# ---------------------------------------------------------------------------
items = []          # (item_id, code, name, type, unit, standard_cost, list_price)
item_id_of = {}
rm_info = {}        # code -> dict
fg_info = {}

iid = 1
for code, name, price, demand, lead, industry in FINISHED_GOODS:
    item_id_of[code] = iid
    fg_info[code] = dict(id=iid, name=name, price=price, demand=demand,
                         lead=lead, industry=industry)
    iid += 1
for code, name, unit, cost, sup, moq in RAW_MATERIALS:
    item_id_of[code] = iid
    wh = WH_IMPORT if SUP[sup][2] != "KR" else WH_RM
    rm_info[code] = dict(id=iid, name=name, unit=unit, cost=cost, sup=sup,
                         moq=moq, wh=wh)
    iid += 1

BOM_MILLI = {fg: {rm: r3(q) for rm, q in kids.items()} for fg, kids in BOM.items()}

for code, f in fg_info.items():
    material = sum(rm_info[rm]["cost"] * q for rm, q in BOM[code].items())
    f["cost"] = round(material * 1.10 + f["price"] * 0.14)   # 재료비 + 가공비
    items.append((f["id"], code, f["name"], "FG", "EA", f["cost"], f["price"]))
for code, r in rm_info.items():
    items.append((r["id"], code, r["name"], "RM", r["unit"], r["cost"], None))
items.sort()

UNIT_STEP = {code: (100 if f["price"] < 5000 else 10) for code, f in fg_info.items()}

# ---------------------------------------------------------------------------
# 2. 수요 생성 (수주)
# ---------------------------------------------------------------------------
customers = []
cust_rows = []
for i, (name, ctry, seg, ind, rep, w, since, disc) in enumerate(CUSTOMERS, start=1):
    customers.append(dict(id=i, name=name, industry=ind, weight=w, since=since,
                          disc=disc, rep=rep))
    cust_rows.append((i, name, ctry, seg, rep, since))


def customer_weight(c, d):
    if d < c["since"]:
        return 0.0
    if c["name"] == NEW_CUSTOMER:
        months = (d.year - 2025) * 12 + d.month - 3          # 0부터 증가
        return min(1.0 + 0.9 * months, 9.0)
    return c["weight"]


def item_weight(code, d):
    w = fg_info[code]["demand"] * fg_info[code]["price"] ** 0.5
    if code == DECLINING_ITEM and d >= date(2025, 6, 1):
        months = (d.year - 2025) * 12 + d.month - 6
        w *= max(0.05, 1.0 - 0.3 * (months + 1))
    return w


ind_items = defaultdict(list)
for code, f in fg_info.items():
    ind_items[f["industry"]].append(code)
# 모바일 고객도 홀 센서 모듈을 가끔 산다 (교차 구매)
ind_items["MOBILE"].append("FG-1010")


def poisson(lam):
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


orders = []         # dict(id, cust, date, req, cancel_on)
lines = []          # dict(order, line, item, qty, price, shipped)
oid = 1
for d in BDAYS:
    lam = 5.0 * SEASON[d.month - 1] * GROWTH[d.year]
    for _ in range(poisson(lam)):
        pool = [(c, customer_weight(c, d)) for c in customers]
        pool = [(c, w) for c, w in pool if w > 0]
        c = rng.choices([p[0] for p in pool], weights=[p[1] for p in pool])[0]
        n_lines = rng.choices([1, 2, 3, 4], weights=[45, 30, 17, 8])[0]
        cand = ind_items[c["industry"]]
        chosen = []
        for _ in range(n_lines):
            left = [x for x in cand if x not in chosen]
            if not left:
                break
            chosen.append(rng.choices(left, weights=[item_weight(x, d) for x in left])[0])
        lead_days = rng.randint(2, 5) if rng.random() < 0.15 else rng.randint(7, 28)  # 15%는 긴급 주문
        req = next_bday(d + timedelta(days=lead_days))
        cancel_on = None
        if rng.random() < 0.02:
            cancel_on = next_bday(d + timedelta(days=rng.randint(1, 6)))
        orders.append(dict(id=oid, cust=c, date=d, req=req, cancel_on=cancel_on))
        for ln, code in enumerate(chosen, start=1):
            lines.append(dict(order=oid, line=ln, item=code, qty=0, price=0,
                              shipped=0, date=d, req=req, cust=c))
        oid += 1

# 수량 보정: 품목별 2년 총 수요가 (월 기준수요 × 계절 × 성장)에 맞도록
target_volume = defaultdict(float)
for d in BDAYS:
    for code, f in fg_info.items():
        bd_in_month = sum(1 for x in BDAYS if x.year == d.year and x.month == d.month)
        target_volume[code] += f["demand"] * SEASON[d.month - 1] * GROWTH[d.year] / bd_in_month
line_count = defaultdict(int)
for ln in lines:
    line_count[ln["item"]] += 1
for ln in lines:
    code = ln["item"]
    mean_qty = target_volume[code] / line_count[code]
    step = UNIT_STEP[code]
    q = mean_qty * rng.lognormvariate(-0.08, 0.4) * (0.7 + 0.08 * ln["cust"]["weight"] ** 0.5)
    ln["qty"] = max(step, int(round(q / step)) * step)
    price = fg_info[code]["price"] * (1.03 if ln["date"].year == 2025 else 1.0)
    price *= (1 - ln["cust"]["disc"]) * rng.uniform(0.98, 1.02)
    ln["price"] = round(price)

# ---------------------------------------------------------------------------
# 3. 공급 시뮬레이션
# ---------------------------------------------------------------------------
stock = defaultdict(int)              # (item_code, wh) -> milli
txns = []                             # (item_code, wh, type, milli, date, ref_type, ref_id)


def post(code, wh, ttype, milli, d, ref_type, ref_id):
    stock[(code, wh)] += milli
    assert stock[(code, wh)] >= 0, f"음수 재고 {code} {wh} {d}"
    txns.append((code, wh, ttype, milli, d, ref_type, ref_id))


def rm_wh(code):
    return rm_info[code]["wh"]


# 기초재고 (2024-01-02, 첫 영업일): 완제품 약 3주, 원자재 약 4주분
first_day = BDAYS[0]
for code, f in fg_info.items():
    q = int(f["demand"] * 0.75 / UNIT_STEP[code]) * UNIT_STEP[code]
    post(code, WH_FG, "ADJUST", q * M, first_day, "ADJUST", None)
rm_monthly = defaultdict(float)
for fg, kids in BOM.items():
    for rm, q in kids.items():
        rm_monthly[rm] += fg_info[fg]["demand"] * q
for code, r in rm_info.items():
    weeks = 4 if r["wh"] == WH_IMPORT else 3
    q = math.ceil(rm_monthly[code] * weeks / 4.3 / r["moq"]) * r["moq"]
    post(code, r["wh"], "ADJUST", q * M, first_day, "ADJUST", None)

prod_orders = []      # dict(id, item, planned, completed, start, due, status, finish)
pos = []              # dict(id, sup, date, expected, status, cancel)
po_lines = []         # dict(po, line, item, milli, price, received, plan=[(date, milli)])
receipts = []         # (gr_id, po, line, date, milli)
shipments = []        # (shipment_id, order, line, date, qty)

order_by_id = {o["id"]: o for o in orders}
lines_by_order = defaultdict(list)
for ln in lines:
    lines_by_order[ln["order"]].append(ln)
cancelled = set()

ordered_by_day = defaultdict(lambda: defaultdict(int))   # date -> code -> qty
for ln in lines:
    ordered_by_day[ln["date"]][ln["item"]] += ln["qty"]


def fg_forecast(code, d):
    """하루 평균 수요 예측: 최근 60일 수주량 기준. 단종 품목은 예측을 갱신하지 않음"""
    f = fg_info[code]
    base = f["demand"] / 21.0
    if code == DECLINING_ITEM:
        return base                                    # 수요가 줄어도 예측을 갱신하지 않음
    if d < START + timedelta(days=60):
        return base * SEASON[d.month - 1]
    window = [d - timedelta(days=k) for k in range(1, 61)]
    total = sum(ordered_by_day[x].get(code, 0) for x in window)
    bdays = sum(1 for x in window if is_bday(x))
    return total / max(bdays, 1)


next_ids = dict(prod=1, po=1, gr=1, ship=1)

for d in BDAYS:
    # (1) 구매 입고
    for pl in po_lines:
        for (rd, milli) in [p for p in pl["plan"] if p[0] == d]:
            po = pos[pl["po"] - 1]
            if po["status"] == "CANCELLED":
                continue
            gr = next_ids["gr"]; next_ids["gr"] += 1
            receipts.append((gr, pl["po"], pl["line"], d, milli))
            pl["received"] += milli
            post(pl["item"], rm_wh(pl["item"]), "PURCHASE_IN", milli, d, "GOODS_RECEIPT", gr)

    # (2) 생산 완료
    for p in prod_orders:
        if p["status"] == "IN_PROGRESS" and p["finish"] == d:
            yield_rate = rng.uniform(0.97, 1.0)
            step = UNIT_STEP[p["item"]]
            done = max(step, int(p["planned"] * yield_rate / step) * step)
            p["completed"], p["status"] = done, "DONE"
            post(p["item"], WH_FG, "PROD_RECEIPT", done * M, d, "PROD_ORDER", p["id"])

    # (3) 생산 착수: 품목별 전용 라인 1개(동시에 1건), 원자재가 전량 있을 때만, 먼저 지시된 것부터
    busy = {p["item"] for p in prod_orders if p["status"] == "IN_PROGRESS"}
    for p in prod_orders:
        if p["status"] != "PLANNED" or p["created"] >= d or p["item"] in busy:
            continue
        need = {rm: q * p["planned"] for rm, q in BOM_MILLI[p["item"]].items()}
        if all(stock[(rm, rm_wh(rm))] >= m for rm, m in need.items()):
            for rm, m in need.items():
                post(rm, rm_wh(rm), "PROD_ISSUE", -m, d, "PROD_ORDER", p["id"])
            p["status"], p["start"] = "IN_PROGRESS", d
            busy.add(p["item"])
            delay = rng.randint(2, 7) if rng.random() < 0.12 else 0   # 설비 고장·품질 이슈
            p["finish"] = add_bdays(d, fg_info[p["item"]]["lead"] + delay)

    # (4) 출하: 요청 납기 5일 전부터, 납기 빠른 순
    open_lines = [ln for ln in lines
                  if ln["order"] not in cancelled and ln["shipped"] < ln["qty"]
                  and ln["date"] < d and d >= ln["req"] - timedelta(days=5)]
    open_lines.sort(key=lambda x: (x["req"], x["order"], x["line"]))
    for ln in open_lines:
        o = order_by_id[ln["order"]]
        if o["cancel_on"] and d >= o["cancel_on"] and not any(l["shipped"] for l in lines_by_order[o["id"]]):
            continue
        avail = stock[(ln["item"], WH_FG)] // M
        remain = ln["qty"] - ln["shipped"]
        step = UNIT_STEP[ln["item"]]
        if avail >= remain:
            q = remain
        elif avail >= max(step, remain * 0.3):
            q = (avail // step) * step
        else:
            continue
        if q <= 0:
            continue
        sid = next_ids["ship"]; next_ids["ship"] += 1
        shipments.append((sid, ln["order"], ln["line"], d, q))
        ln["shipped"] += q
        post(ln["item"], WH_FG, "SALES_OUT", -q * M, d, "SHIPMENT", sid)

    # (5) 주문 취소: 아직 하나도 출하되지 않은 주문만
    for o in orders:
        if o["cancel_on"] == d and o["id"] not in cancelled:
            if not any(l["shipped"] for l in lines_by_order[o["id"]]):
                cancelled.add(o["id"])

    # (6) 생산계획: 예상재고 = 현재고 + 생산중 - 미출하 수주
    backlog = defaultdict(int)
    for ln in lines:
        if ln["order"] not in cancelled and ln["date"] <= d:
            backlog[ln["item"]] += ln["qty"] - ln["shipped"]
    wip = defaultdict(int)
    for p in prod_orders:
        if p["status"] in ("PLANNED", "IN_PROGRESS"):
            wip[p["item"]] += p["planned"]
    for code, f in fg_info.items():
        fc = fg_forecast(code, d)
        rop = fc * (f["lead"] + 4)
        lot = fc * 16
        projected = stock[(code, WH_FG)] // M + wip[code] - backlog[code]
        if projected < rop and fc > 0:
            step = 1000 if f["price"] < 5000 else 100
            qty = math.ceil(max(lot, rop + lot - projected) / step) * step
            pid = next_ids["prod"]; next_ids["prod"] += 1
            prod_orders.append(dict(id=pid, item=code, planned=qty, completed=0,
                                    start=None, finish=None, created=d,
                                    due=add_bdays(d, f["lead"] + 1), status="PLANNED"))

    # (7) 구매계획: 예상재고 = 현재고 + 미입고 발주 - 착수 대기 생산지시 소요량
    planned_need = defaultdict(int)
    for p in prod_orders:
        if p["status"] == "PLANNED":
            for rm, q in BOM_MILLI[p["item"]].items():
                planned_need[rm] += q * p["planned"]
    on_order = defaultdict(int)
    for pl in po_lines:
        if pos[pl["po"] - 1]["status"] != "CANCELLED":
            on_order[pl["item"]] += pl["milli"] - pl["received"]
    fg_fc = {code: fg_forecast(code, d) for code in fg_info}
    need_by_sup = defaultdict(list)
    for code, r in rm_info.items():
        daily = sum(fg_fc[fg] * BOM[fg][code] for fg in BOM if code in BOM[fg])
        lead_bd = SUP[r["sup"]][3] * 5 / 7
        cover = 20 if r["wh"] == WH_IMPORT else 9
        rop = daily * (lead_bd + 5) * M
        projected = stock[(code, r["wh"])] + on_order[code] - planned_need[code]
        if projected < rop and daily > 0:
            want = max(daily * cover * M, rop + daily * cover * M - projected)
            units = math.ceil(want / M / r["moq"]) * r["moq"]
            need_by_sup[r["sup"]].append((code, units))
    for sup_id, needs in need_by_sup.items():
        s = SUP[sup_id]
        po_id = next_ids["po"]; next_ids["po"] += 1
        expected = d + timedelta(days=s[3])
        pos.append(dict(id=po_id, sup=sup_id, date=d, expected=expected,
                        status="OPEN"))
        for ln_no, (code, units) in enumerate(needs, start=1):
            r = rm_info[code]
            price = r["cost"] * rng.uniform(0.97, 1.03)
            if code in COPPER and d.year == 2025:
                price *= 1.18
            actual = max(1, round(s[3] * rng.uniform(*s[4])))
            first = next_bday(d + timedelta(days=actual))
            milli = units * M
            if rng.random() < (0.35 if sup_id == LATE_SUPPLIER else 0.12):
                part = (int(units * rng.uniform(0.5, 0.7)) // r["moq"]) * r["moq"]
                part = max(part, r["moq"]) if units > r["moq"] else units
                plan = [(first, part * M)]
                if part < units:
                    plan.append((next_bday(first + timedelta(days=rng.randint(3, 10))),
                                 (units - part) * M))
            else:
                plan = [(first, milli)]
            po_lines.append(dict(po=po_id, line=ln_no, item=code, milli=milli,
                                 price=round(price, 2), received=0, plan=plan))

    # (8) 분기말 재고실사: 원자재 일부에 소폭 차이 조정
    nxt = add_bdays(d, 1)
    if d.month in (3, 6, 9, 12) and nxt.month != d.month:
        for code in rng.sample(list(rm_info), 6):
            wh = rm_info[code]["wh"]
            cur = stock[(code, wh)]
            if cur <= 0:
                continue
            delta = int(cur * rng.uniform(0.003, 0.015)) * rng.choice([-1, 1])
            if rm_info[code]["unit"] == "EA":
                delta = (delta // M) * M
            if delta != 0 and cur + delta >= 0:
                post(code, wh, "ADJUST", delta, d, "ADJUST", None)

# ---------------------------------------------------------------------------
# 4. 상태값 정리
# ---------------------------------------------------------------------------
for o in orders:
    ls = lines_by_order[o["id"]]
    if o["id"] in cancelled:
        o["status"] = "CANCELLED"
    elif all(l["shipped"] >= l["qty"] for l in ls):
        o["status"] = "SHIPPED"
    elif any(l["shipped"] > 0 for l in ls):
        o["status"] = "PARTIAL"
    else:
        o["status"] = "OPEN"

for po in pos:
    pls = [pl for pl in po_lines if pl["po"] == po["id"]]
    if all(pl["received"] >= pl["milli"] for pl in pls):
        po["status"] = "RECEIVED"
    elif any(pl["received"] > 0 for pl in pls):
        po["status"] = "PARTIAL"

# 영업 목표: 담당자별 연간 출하실적 기반 계획(대부분 0~8% 상향, 미달 담당자는 25% 상향)
ship_amount = defaultdict(float)     # (rep, year, month)
line_key = {(ln["order"], ln["line"]): ln for ln in lines}
for sid, o_id, ln_no, sd, q in shipments:
    ln = line_key[(o_id, ln_no)]
    ship_amount[(ln["cust"]["rep"], sd.year, sd.month)] += q * ln["price"]
targets = []
for rep in SALES_REPS:
    rep_id = rep[0]
    for year in (2024, 2025):
        annual = sum(ship_amount[(rep_id, year, m)] for m in range(1, 13))
        factor = 1.25 if rep_id == UNDERPERFORMER_REP else rng.uniform(0.93, 1.06)
        for m in range(1, 13):
            t = annual * factor * SEASON[m - 1] / sum(SEASON)
            t *= rng.uniform(0.95, 1.05)
            targets.append((rep_id, date(year, m, 1), int(round(t / 1_000_000)) * 1_000_000))

# ---------------------------------------------------------------------------
# 5. CSV 저장
# ---------------------------------------------------------------------------
OUT.mkdir(parents=True, exist_ok=True)


def write(name, header, rows):
    with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        w.writerow(header)
        for row in rows:
            w.writerow(["" if v is None else v for v in row])
    print(f"{name:<22}{len(rows):>8,} rows")


write("sales_reps", ["rep_id", "name", "team", "hire_date"], SALES_REPS)
write("customers", ["customer_id", "name", "country", "segment", "rep_id", "created_at"], cust_rows)
write("items", ["item_id", "item_code", "name", "item_type", "unit", "standard_cost", "list_price"], items)
write("warehouses", ["warehouse_id", "name", "location"], WAREHOUSES)
write("bom", ["parent_item_id", "child_item_id", "qty_per"],
      [(item_id_of[fg], item_id_of[rm], fmt_milli(m))
       for fg, kids in BOM_MILLI.items() for rm, m in kids.items()])
write("suppliers", ["supplier_id", "name", "country", "lead_time_days", "created_at"],
      [(s[0], s[1], s[2], s[3], date(2015 + s[0] % 8, 1 + s[0] % 12, 1)) for s in SUPPLIERS])
write("sales_orders", ["order_id", "customer_id", "order_date", "requested_date", "status"],
      [(o["id"], o["cust"]["id"], o["date"], o["req"], o["status"]) for o in orders])
write("sales_order_lines", ["order_id", "line_no", "item_id", "qty", "unit_price"],
      [(l["order"], l["line"], item_id_of[l["item"]], l["qty"], l["price"]) for l in lines])
write("shipments", ["shipment_id", "order_id", "line_no", "ship_date", "qty"], shipments)
write("sales_targets", ["rep_id", "year_month", "target_amount"], targets)
write("purchase_orders", ["po_id", "supplier_id", "po_date", "expected_date", "status"],
      [(p["id"], p["sup"], p["date"], p["expected"], p["status"]) for p in pos])
write("purchase_order_lines", ["po_id", "line_no", "item_id", "qty", "unit_price"],
      [(pl["po"], pl["line"], item_id_of[pl["item"]], fmt_milli(pl["milli"]), f'{pl["price"]:.2f}')
       for pl in po_lines])
write("goods_receipts", ["gr_id", "po_id", "line_no", "receipt_date", "qty"],
      [(g, p, l, d, fmt_milli(m)) for g, p, l, d, m in receipts])
write("production_orders", ["prod_order_id", "item_id", "planned_qty", "completed_qty",
                            "start_date", "due_date", "status"],
      [(p["id"], item_id_of[p["item"]], p["planned"], p["completed"], p["start"],
        p["due"], p["status"]) for p in prod_orders])
write("inventory_txns", ["txn_id", "item_id", "warehouse_id", "txn_type", "qty",
                         "txn_date", "ref_type", "ref_id"],
      [(i, item_id_of[c], wh, t, fmt_milli(m), d, rt, rid)
       for i, (c, wh, t, m, d, rt, rid) in enumerate(txns, start=1)])

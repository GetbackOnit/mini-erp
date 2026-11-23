-- =========================================================
-- 05. 완제품 ABC 분석 (2025년 출하 매출 기준)
-- 질문: 매출의 대부분을 만드는 핵심 품목은 무엇인가?
-- 기준: 매출 = 출하 수량 × 수주 단가, 기간 2025-01-01 ~ 2025-12-31
--       A = 누적 비중 70% 이내, B = 70~90%, C = 나머지
-- 사용: CTE, SUM() OVER (전체 합계 / 누적 합계), CASE WHEN
--
-- 결과: 완제품 20종 중 A 12종(누적 69.9%), B 4종, C 4종
--       1위 AF 액추에이터 8.7%, 최하위 DC 브러시 모터 소형(FG-1019) 2.1%
--
-- 해석: 1위 품목도 비중이 8.7%에 그쳐 매출이 품목 전반에 고르게 분산되어 있다.
--       '상위 20% 품목이 매출 80%'라는 파레토 구조가 아니어서,
--       70/90 기준을 그대로 적용하면 품목의 60%가 A가 되어 차등 관리의 의미가 약해진다.
--       → 기준을 기계적으로 적용하기 전에 매출 분포부터 확인해야 하며,
--         이 경우 품목 수 기준(상위 20% = A)이나 이익 기준 등급을 함께 검토할 필요가 있다.
--       FG-1019는 C등급 최하위로, 06(재고회전율)에서 정체 재고 여부를 확인한다.
-- =========================================================

WITH item_sales AS (
  -- 1) 품목별 2025년 출하 매출
  SELECT i.item_code,
         i.name,
         SUM(s.qty * l.unit_price) AS revenue
  FROM shipments s
  JOIN sales_order_lines l ON s.order_id = l.order_id
                          AND s.line_no  = l.line_no
  JOIN items i             ON l.item_id  = i.item_id
  WHERE s.ship_date >= DATE '2025-01-01'
    AND s.ship_date <  DATE '2026-01-01'
  GROUP BY i.item_id, i.item_code, i.name
),
ranked AS (
  -- 2) 매출 비중과 누적 비중
  SELECT item_code,
         name,
         revenue,
         ROUND(100.0 * revenue / SUM(revenue) OVER (), 1) AS share_pct,
         ROUND(100.0 * SUM(revenue) OVER (ORDER BY revenue DESC)
                     / SUM(revenue) OVER (), 1)             AS cum_share_pct
  FROM item_sales
)
-- 3) 누적 비중으로 등급 부여
SELECT item_code,
       name,
       revenue,
       share_pct,
       cum_share_pct,
       CASE WHEN cum_share_pct <= 70 THEN 'A'
            WHEN cum_share_pct <= 90 THEN 'B'
            ELSE 'C'
       END AS abc_class
FROM ranked
ORDER BY revenue DESC;
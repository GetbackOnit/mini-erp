-- =========================================================
-- 03. 월별 매출과 전년 동월 대비 성장률
-- 질문: 월 매출은 어떻게 변했고, 작년 같은 달보다 몇 % 늘었나?
-- 기준: 출하 기준 매출 = 출하 수량 × 수주 단가
-- 사용: 복합키 JOIN, date_trunc, CTE, LAG
--
-- 결과: 연 매출 2024년 약 69.1억 → 2025년 약 79.3억 (+14.7%)
--       2025-09 +49.6%, 2025-10 -13.4%
--
-- 해석: 2025-10 감소는 추석 연휴(10/3~10/9)로 영업일이 줄어든 영향으로 보인다.
--
-- 전제: LAG(revenue, 12)는 24개월이 빠짐없이 있을 때만 '전년 동월'을 가리킨다.
--       출하가 없는 달이 생기면 월 달력을 먼저 만들어 LEFT JOIN해야 한다.
-- =========================================================

WITH monthly AS (
  SELECT date_trunc('month', s.ship_date)::date AS ym,
         SUM(s.qty * l.unit_price)               AS revenue
  FROM shipments s
  JOIN sales_order_lines l
    ON s.order_id = l.order_id
   AND s.line_no  = l.line_no
  GROUP BY ym
)
SELECT ym,
       revenue,
       LAG(revenue, 12) OVER (ORDER BY ym) AS prev_year_revenue,
       ROUND(100.0 * (revenue / LAG(revenue, 12) OVER (ORDER BY ym) - 1), 1) AS yoy_pct
FROM monthly
ORDER BY ym;
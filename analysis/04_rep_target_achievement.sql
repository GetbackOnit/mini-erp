-- =========================================================
-- 04. 영업담당별 목표 대비 실적과 연 누적 달성률
-- 질문: 영업담당자마다 매월 목표를 몇 % 달성했고,
--       그해 1월부터 누적으로는 몇 %인가?
-- 기준: 실적 = 출하 기준 매출(출하 수량 × 수주 단가),
--       담당자 = 출하된 수주의 고객 담당자(customers.rep_id)
-- 사용: 4개 테이블 JOIN, CTE, LEFT JOIN + COALESCE,
--       윈도우 함수(PARTITION BY), WINDOW 절
--
-- 결과: 연 누적 달성률(12월 기준)
--       정다은 2024년 79.3% / 2025년 79.9% — 6명 중 유일하게 2년 연속 80% 미만
--       나머지 5명은 2024년 97.9~107.8%, 2025년 98.9~106.3%
--
-- 해석: 정다은의 미달은 2년 내내 일관되게 나타난다.
--       다만 목표 설정 방식(전년 실적 대비 상향 폭)과 담당 고객의
--       업종·규모가 다르면 달성률만으로 개인 성과를 단정하기 어렵다.
--       → 담당 고객별 매출 추이를 함께 봐야 원인을 구분할 수 있다.
-- =========================================================

WITH actual AS (
  -- 담당자·월별 출하 실적
  SELECT c.rep_id,
         date_trunc('month', s.ship_date)::date AS ym,
         SUM(s.qty * l.unit_price)               AS actual_amount
  FROM shipments s
  JOIN sales_order_lines l ON s.order_id = l.order_id
                          AND s.line_no  = l.line_no
  JOIN sales_orders o      ON s.order_id    = o.order_id
  JOIN customers c         ON o.customer_id = c.customer_id
  GROUP BY c.rep_id, ym
)
SELECT r.name,
       t.year_month,
       t.target_amount,
       COALESCE(a.actual_amount, 0) AS actual_amount,
       ROUND(100.0 * COALESCE(a.actual_amount, 0) / t.target_amount, 1) AS achievement_pct,
       ROUND(100.0 * SUM(COALESCE(a.actual_amount, 0)) OVER w
                   / SUM(t.target_amount) OVER w, 1)                  AS cum_achievement_pct
FROM sales_targets t
JOIN sales_reps r     ON t.rep_id = r.rep_id
LEFT JOIN actual a    ON a.rep_id = t.rep_id
                     AND a.ym     = t.year_month   -- 실적이 없는 달도 목표는 남김
WINDOW w AS (
  PARTITION BY t.rep_id, EXTRACT(YEAR FROM t.year_month)  -- 담당자별·연도별로 누적
  ORDER BY t.year_month
)
ORDER BY t.rep_id, t.year_month;
-- =========================================================
-- 01. 일자별 재고 잔액
-- 질문: OIS 액추에이터(item_id=7)의 완제품창고(warehouse_id=2) 재고는
--       날짜별로 얼마였나?
-- 사용: CTE, 집계 함수(SUM + GROUP BY), 윈도우 함수(SUM() OVER)
--
-- 설계 포인트:
--   재고를 '현재고' 컬럼이 아닌 수불 원장(inventory_txns)으로 관리하므로
--   잔액은 입출고 수량(+/-)의 누적합으로 계산한다.
--   같은 날 거래가 여러 건이라 먼저 일자별로 합친 뒤 누적한다.
--
-- 결과: 거래일 123일, 최종 잔액 3,700 (2025-12-31)
-- =========================================================

WITH daily AS (
  SELECT txn_date, SUM(qty) AS daily_change
  FROM inventory_txns
  WHERE item_id = 7 AND warehouse_id = 2
  GROUP BY txn_date
)
SELECT txn_date,
       daily_change,
       SUM(daily_change) OVER (ORDER BY txn_date) AS balance
FROM daily
ORDER BY txn_date;
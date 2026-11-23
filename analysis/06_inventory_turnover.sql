-- =========================================================
-- 06. 완제품 재고회전율과 정체 재고 (2025년, 완제품창고 기준)
-- 질문: 어떤 품목의 재고가 팔리는 속도에 비해 과하게 쌓여 있나?
-- 기준(수량 기준):
--   재고회전율     = 2025년 출고 수량 ÷ 월말 재고 평균(12개월)
--   재고보유일수   = 365 ÷ 재고회전율
--   기말 재고 개월수 = 2025-12-31 재고 ÷ 하반기 월평균 출고 수량
--   기말 재고 개월수가 3개월 이상이면 '정체 의심'
-- 사용: generate_series(월 달력), CROSS JOIN, LEFT JOIN, CTE 여러 개, FILTER
--
-- 결과: 정체 의심 1종 — FG-1019(DC 브러시 모터 소형)
--       기말 재고 13,400개 = 하반기 월평균 출고의 14.1개월분 (나머지 19종은 0.5~1.5개월)
--       2025년 8~12월 출고 0개인데 10월에 8,700개가 생산 입고됨
--
-- 해석: FG-1019의 연간 회전율은 8.0회로 최하위지만 다른 품목(9.8~21.2회)과
--       극단적으로 차이 나지는 않는다. 상반기 판매가 연평균을 끌어올려
--       하반기의 수요 급감이 가려졌기 때문이다.
--       → 연 단위 회전율만 보면 놓치고, 최근 출고 대비 기말 재고로 봐야 드러난다.
--       수요가 끊긴 뒤에도 생산이 이어진 것은 수요예측이 갱신되지 않았다는 신호다.
--       (05 ABC 분석에서도 C등급 최하위)
-- =========================================================

WITH month_ends AS (
  -- 1) 2025년 12개월의 월말 날짜 달력
  SELECT ((m + INTERVAL '1 month')::date - 1) AS month_end
  FROM generate_series(DATE '2025-01-01', DATE '2025-12-01', INTERVAL '1 month') AS m
),
month_end_stock AS (
  -- 2) 품목 × 월말마다, 그날까지의 입출고 누적 = 월말 재고
  SELECT i.item_id,
         me.month_end,
         COALESCE(SUM(t.qty), 0) AS stock
  FROM items i
  CROSS JOIN month_ends me
  LEFT JOIN inventory_txns t ON t.item_id      = i.item_id
                            AND t.warehouse_id = 2
                            AND t.txn_date    <= me.month_end
  WHERE i.item_type = 'FG'
  GROUP BY i.item_id, me.month_end
),
stock_summary AS (
  -- 3) 품목별 평균 재고와 기말 재고
  SELECT item_id,
         AVG(stock)                                          AS avg_stock,
         MAX(stock) FILTER (WHERE month_end = DATE '2025-12-31') AS ending_stock
  FROM month_end_stock
  GROUP BY item_id
),
outflow AS (
  -- 4) 품목별 2025년 출고 수량, 하반기 월평균 출고 수량
  SELECT item_id,
         -SUM(qty)                                                   AS out_2025,
         -SUM(qty) FILTER (WHERE txn_date >= DATE '2025-07-01') / 6.0 AS out_h2_monthly
  FROM inventory_txns
  WHERE txn_type = 'SALES_OUT'
    AND warehouse_id = 2
    AND txn_date BETWEEN DATE '2025-01-01' AND DATE '2025-12-31'
  GROUP BY item_id
)
SELECT i.item_code,
       i.name,
       o.out_2025::int                                   AS out_2025,
       ROUND(s.avg_stock)::int                           AS avg_stock,
       ROUND(o.out_2025 / NULLIF(s.avg_stock, 0), 1)     AS turnover,
       ROUND(365 * s.avg_stock / NULLIF(o.out_2025, 0))  AS days_on_hand,
       s.ending_stock::int                               AS ending_stock,
       ROUND(s.ending_stock / NULLIF(o.out_h2_monthly, 0), 1) AS months_of_cover,
       CASE WHEN s.ending_stock / NULLIF(o.out_h2_monthly, 0) >= 3
            THEN '정체 의심' ELSE '' END                  AS flag
FROM stock_summary s
JOIN items i        ON s.item_id = i.item_id
LEFT JOIN outflow o ON s.item_id = o.item_id
ORDER BY months_of_cover DESC NULLS FIRST;
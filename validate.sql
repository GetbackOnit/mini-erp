-- =========================================================
-- 데이터 무결성 검증 쿼리 (적재 후 실행)
-- 각 쿼리의 결과가 "0" 또는 "빈 결과"이면 정상
-- =========================================================

-- 1. 창고·품목별 재고가 한 번이라도 음수가 된 적이 있는가 (윈도우 함수)
SELECT COUNT(*) AS negative_balance_rows
FROM (
  SELECT SUM(qty) OVER (PARTITION BY item_id, warehouse_id
                        ORDER BY txn_date, txn_id) AS running_balance
  FROM inventory_txns
) t
WHERE running_balance < 0;

-- 2. 출하 수량 합계가 수주 수량을 초과한 수주 품목
SELECT COUNT(*) AS over_shipped_lines
FROM sales_order_lines l
JOIN (SELECT order_id, line_no, SUM(qty) AS shipped
      FROM shipments GROUP BY order_id, line_no) s USING (order_id, line_no)
WHERE s.shipped > l.qty;

-- 3. 입고 수량 합계가 발주 수량을 초과한 발주 품목
SELECT COUNT(*) AS over_received_lines
FROM purchase_order_lines l
JOIN (SELECT po_id, line_no, SUM(qty) AS received
      FROM goods_receipts GROUP BY po_id, line_no) g USING (po_id, line_no)
WHERE g.received > l.qty;

-- 4. 생산 투입 원자재가 BOM × 생산지시 수량과 다른 경우
SELECT COUNT(*) AS bom_mismatch
FROM production_orders p
JOIN bom b ON b.parent_item_id = p.item_id
LEFT JOIN (SELECT ref_id, item_id, -SUM(qty) AS issued
           FROM inventory_txns
           WHERE txn_type = 'PROD_ISSUE'
           GROUP BY ref_id, item_id) i
       ON i.ref_id = p.prod_order_id AND i.item_id = b.child_item_id
WHERE p.status IN ('IN_PROGRESS', 'DONE')
  AND COALESCE(i.issued, 0) <> b.qty_per * p.planned_qty;

-- 5. 출하일이 수주일보다 빠르거나, 주말에 거래가 발생한 경우
SELECT
  (SELECT COUNT(*) FROM shipments s JOIN sales_orders o USING (order_id)
    WHERE s.ship_date <= o.order_date)                         AS ship_before_order,
  (SELECT COUNT(*) FROM inventory_txns
    WHERE EXTRACT(ISODOW FROM txn_date) IN (6, 7))             AS weekend_txns;

-- 6. 수주 상태값이 실제 출하 내역과 맞지 않는 경우
WITH line_status AS (
  SELECT l.order_id,
         BOOL_AND(COALESCE(s.shipped, 0) >= l.qty) AS all_shipped,
         BOOL_OR(COALESCE(s.shipped, 0) > 0)       AS any_shipped
  FROM sales_order_lines l
  LEFT JOIN (SELECT order_id, line_no, SUM(qty) AS shipped
             FROM shipments GROUP BY order_id, line_no) s USING (order_id, line_no)
  GROUP BY l.order_id
)
SELECT COUNT(*) AS status_mismatch
FROM sales_orders o JOIN line_status ls USING (order_id)
WHERE o.status <> CASE
        WHEN o.status = 'CANCELLED' AND NOT ls.any_shipped THEN 'CANCELLED'
        WHEN ls.all_shipped THEN 'SHIPPED'
        WHEN ls.any_shipped THEN 'PARTIAL'
        ELSE 'OPEN' END;

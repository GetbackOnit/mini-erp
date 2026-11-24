-- =========================================================
-- 07. 결품·납기 지연 원인 추적 (공급업체 → 원자재 → 생산 → 출하)
-- 질문: 고객 납기 지연은 어디서 시작되었나?
-- 연결: 01(OIS 액추에이터 재고 0인 날 10일) + 02(Hongda 입고 평균 18일 지연)
-- 사용: CTE 체인, DISTINCT로 원자재-공급업체 매핑, BOOL_OR, STRING_AGG,
--       EXISTS 서브쿼리, 그룹 비교
--
-- 원자재의 공급업체는 items에 없으므로 발주 이력(purchase_order_lines →
-- purchase_orders)에서 가져온다. (이 데이터에서는 원자재 1종 = 공급업체 1곳)
-- =========================================================


-- ---------------------------------------------------------
-- [1] 완제품별 납기 지연 출하율 + Hongda 부품 사용 여부
--     출하일 > 고객 요청 납기일이면 지연 출하
-- ---------------------------------------------------------
WITH rm_supplier AS (
  SELECT DISTINCT pol.item_id, po.supplier_id
  FROM purchase_order_lines pol
  JOIN purchase_orders po ON pol.po_id = po.po_id
),
hongda AS (
  SELECT supplier_id FROM suppliers WHERE name = 'Shenzhen Hongda Electronics'
),
fg_dependency AS (
  SELECT b.parent_item_id AS item_id,
         BOOL_OR(rs.supplier_id = (SELECT supplier_id FROM hongda)) AS uses_hongda,
         STRING_AGG(DISTINCT ri.item_code, ', ')
           FILTER (WHERE rs.supplier_id = (SELECT supplier_id FROM hongda)) AS hongda_parts
  FROM bom b
  JOIN rm_supplier rs ON rs.item_id = b.child_item_id
  JOIN items ri       ON ri.item_id = b.child_item_id
  GROUP BY b.parent_item_id
),
ship_late AS (
  SELECT l.item_id,
         COUNT(*) AS shipments,
         ROUND(100.0 * AVG(CASE WHEN s.ship_date > o.requested_date THEN 1 ELSE 0 END), 1) AS late_pct
  FROM shipments s
  JOIN sales_order_lines l ON s.order_id = l.order_id AND s.line_no = l.line_no
  JOIN sales_orders o      ON s.order_id = o.order_id
  GROUP BY l.item_id
)
SELECT i.item_code, i.name, f.uses_hongda, f.hongda_parts,
       sl.shipments, sl.late_pct
FROM items i
JOIN fg_dependency f ON i.item_id = f.item_id
JOIN ship_late sl    ON i.item_id = sl.item_id
ORDER BY sl.late_pct DESC;

-- 결과: 지연 출하율 상위 3개 품목이 모두 Hongda 부품(RM-2022 모터 드라이버 IC) 사용
--       FG-1020 13.9% / FG-1007 OIS 액추에이터 10.7% / FG-1013 10.2%


-- ---------------------------------------------------------
-- [2] Hongda 부품 사용 그룹 vs 미사용 그룹의 지연 출하율 비교
-- ---------------------------------------------------------
WITH rm_supplier AS (
  SELECT DISTINCT pol.item_id, po.supplier_id
  FROM purchase_order_lines pol
  JOIN purchase_orders po ON pol.po_id = po.po_id
),
fg_dependency AS (
  SELECT b.parent_item_id AS item_id,
         BOOL_OR(s.name = 'Shenzhen Hongda Electronics') AS uses_hongda
  FROM bom b
  JOIN rm_supplier rs ON rs.item_id = b.child_item_id
  JOIN suppliers s    ON s.supplier_id = rs.supplier_id
  GROUP BY b.parent_item_id
)
SELECT f.uses_hongda,
       COUNT(DISTINCT l.item_id) AS items,
       COUNT(*)                  AS shipments,
       ROUND(100.0 * AVG(CASE WHEN sh.ship_date > o.requested_date THEN 1 ELSE 0 END), 1) AS late_pct
FROM shipments sh
JOIN sales_order_lines l ON sh.order_id = l.order_id AND sh.line_no = l.line_no
JOIN sales_orders o      ON sh.order_id = o.order_id
JOIN fg_dependency f     ON l.item_id   = f.item_id
GROUP BY f.uses_hongda;

-- 결과: Hongda 부품 사용 5종 7.1% vs 미사용 15종 0.2% (약 35배)


-- ---------------------------------------------------------
-- [3] OIS 액추에이터(FG-1007) 생산지시: 착수 당일 Hongda 자재가 입고된 지시 vs 아닌 지시
--     착수 당일 입고 = 그 자재를 기다리다가 들어오자마자 착수했다는 신호
--     완료일 = 생산 완료 입고(PROD_RECEIPT) 날짜
-- ---------------------------------------------------------
WITH hongda_parts AS (
  SELECT DISTINCT pol.item_id
  FROM purchase_order_lines pol
  JOIN purchase_orders po ON pol.po_id = po.po_id
  JOIN suppliers s        ON po.supplier_id = s.supplier_id
  WHERE s.name = 'Shenzhen Hongda Electronics'
),
prod AS (
  SELECT p.prod_order_id,
         p.start_date,
         p.due_date,
         t.txn_date AS finish_date,
         EXISTS (
           SELECT 1
           FROM inventory_txns r
           JOIN bom b ON b.child_item_id = r.item_id AND b.parent_item_id = p.item_id
           WHERE r.txn_type = 'PURCHASE_IN'
             AND r.txn_date = p.start_date
             AND r.item_id IN (SELECT item_id FROM hongda_parts)
         ) AS started_on_hongda_receipt
  FROM production_orders p
  JOIN items i          ON p.item_id = i.item_id
  JOIN inventory_txns t ON t.ref_type = 'PROD_ORDER'
                       AND t.ref_id   = p.prod_order_id
                       AND t.txn_type = 'PROD_RECEIPT'
  WHERE i.item_code = 'FG-1007'
)
SELECT started_on_hongda_receipt,
       COUNT(*)                                      AS prod_orders,
       ROUND(AVG(GREATEST(finish_date - due_date, 0)), 1) AS avg_days_late
FROM prod
GROUP BY started_on_hongda_receipt;

-- 결과: Hongda 자재 입고 당일 착수 13건 — 완료 예정일 대비 평균 19.5일 지연
--       그 외 14건 — 평균 5.0일 지연


-- =========================================================
-- 종합 해석
--   Hongda(계약 리드타임 21일, 실제 평균 39일, 입고 100% 지연 — 02번)
--   → 모터 드라이버 IC(RM-2022)·자이로 센서 IC(RM-2023) 입고 지연
--   → 해당 IC를 쓰는 완제품의 생산 착수 지연 (FG-1007: 19.5일 vs 5.0일)
--   → 고객 납기 지연 출하 (Hongda 부품 사용 품목 7.1% vs 미사용 0.2%)
--
-- 한계:
--   - [3]의 '착수 당일 입고'는 자재 대기를 추정하는 대리 지표이며 인과의 증명은 아니다.
--     같은 날 다른 자재도 함께 입고될 수 있다.
--   - FG-1011·FG-1012도 RM-2022를 쓰지만 지연 출하율은 0~1.6%다.
--     Hongda 의존은 위험 요인이지 지연을 결정하는 유일한 요인은 아니며,
--     품목별 수요 규모·안전재고 수준을 추가로 봐야 한다.
--
-- 개선 방향: RM-2022·RM-2023의 대체 공급업체 확보, 또는 실제 리드타임(약 39일)을
--           반영한 발주점·안전재고 재설정
-- =========================================================
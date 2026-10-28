-- =========================================================
-- CSV 적재 후 1회 실행
-- ID를 CSV에서 직접 넣었기 때문에, 자동 번호(IDENTITY)의 다음 값을
-- 현재 최대 ID 뒤로 맞춰준다. 안 하면 다음 INSERT 때 PK 중복 에러가 난다.
-- =========================================================

SELECT setval(pg_get_serial_sequence('sales_reps', 'rep_id'),              (SELECT MAX(rep_id) FROM sales_reps));
SELECT setval(pg_get_serial_sequence('customers', 'customer_id'),          (SELECT MAX(customer_id) FROM customers));
SELECT setval(pg_get_serial_sequence('items', 'item_id'),                  (SELECT MAX(item_id) FROM items));
SELECT setval(pg_get_serial_sequence('warehouses', 'warehouse_id'),        (SELECT MAX(warehouse_id) FROM warehouses));
SELECT setval(pg_get_serial_sequence('suppliers', 'supplier_id'),          (SELECT MAX(supplier_id) FROM suppliers));
SELECT setval(pg_get_serial_sequence('sales_orders', 'order_id'),          (SELECT MAX(order_id) FROM sales_orders));
SELECT setval(pg_get_serial_sequence('shipments', 'shipment_id'),          (SELECT MAX(shipment_id) FROM shipments));
SELECT setval(pg_get_serial_sequence('purchase_orders', 'po_id'),          (SELECT MAX(po_id) FROM purchase_orders));
SELECT setval(pg_get_serial_sequence('goods_receipts', 'gr_id'),           (SELECT MAX(gr_id) FROM goods_receipts));
SELECT setval(pg_get_serial_sequence('production_orders', 'prod_order_id'),(SELECT MAX(prod_order_id) FROM production_orders));
SELECT setval(pg_get_serial_sequence('inventory_txns', 'txn_id'),          (SELECT MAX(txn_id) FROM inventory_txns));

-- 행 수 확인 (기대값은 README 참고)
SELECT 'sales_reps' AS table_name, COUNT(*) FROM sales_reps
UNION ALL SELECT 'customers', COUNT(*) FROM customers
UNION ALL SELECT 'items', COUNT(*) FROM items
UNION ALL SELECT 'warehouses', COUNT(*) FROM warehouses
UNION ALL SELECT 'bom', COUNT(*) FROM bom
UNION ALL SELECT 'suppliers', COUNT(*) FROM suppliers
UNION ALL SELECT 'sales_orders', COUNT(*) FROM sales_orders
UNION ALL SELECT 'sales_order_lines', COUNT(*) FROM sales_order_lines
UNION ALL SELECT 'shipments', COUNT(*) FROM shipments
UNION ALL SELECT 'sales_targets', COUNT(*) FROM sales_targets
UNION ALL SELECT 'purchase_orders', COUNT(*) FROM purchase_orders
UNION ALL SELECT 'purchase_order_lines', COUNT(*) FROM purchase_order_lines
UNION ALL SELECT 'goods_receipts', COUNT(*) FROM goods_receipts
UNION ALL SELECT 'production_orders', COUNT(*) FROM production_orders
UNION ALL SELECT 'inventory_txns', COUNT(*) FROM inventory_txns;

-- 빈 값이 NULL로 들어갔는지 확인 (원자재 40개는 정가가 NULL이어야 함)
SELECT COUNT(*) AS rm_with_null_price FROM items WHERE item_type = 'RM' AND list_price IS NULL;

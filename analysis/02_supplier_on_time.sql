-- =========================================================
-- 02. 공급업체별 납기 준수율
-- 질문: 어느 공급업체가 납기를 가장 못 지키나?
-- 사용: 3개 테이블 JOIN, 날짜 연산, CASE WHEN, AVG ... FILTER
--
-- 결과: Shenzhen Hongda Electronics — 계약 리드타임 21일, 실제 평균 39.0일,
--       지연율 100%, 지연 시 평균 18일
--
-- 해석: 국내 업체도 지연율이 30~40%로 높지만 지연 시 평균 3~5일 수준이다.
--       주말 입고와 분할 납품에서 생기는 짧은 지연이 대부분이다.
--       Hongda는 모든 입고가 평균 18일 늦어 구조적 문제로 보인다.
--       → 지연율만으로 업체를 평가하면 오판할 수 있다.
--         지연 빈도와 지연 규모를 함께 봐야 한다.
-- =========================================================

SELECT s.name,
       s.lead_time_days,
       COUNT(*)                                   AS receipts,
       ROUND(AVG(g.receipt_date - p.po_date), 1)  AS avg_actual_days,
       ROUND(100.0 * AVG(CASE WHEN g.receipt_date > p.expected_date THEN 1 ELSE 0 END), 1) AS late_pct,
       ROUND(AVG(g.receipt_date - p.expected_date)
             FILTER (WHERE g.receipt_date > p.expected_date), 1)                         AS avg_delay_when_late
FROM goods_receipts g
JOIN purchase_orders p ON g.po_id = p.po_id
JOIN suppliers s       ON p.supplier_id = s.supplier_id
GROUP BY s.supplier_id
ORDER BY late_pct DESC;


-- ROUND와 CASE을 잘 이용하는 법을 배우자;;
-- 그리고 전체적인 프로세스 흐름을 이해하는게 제일 중요하고
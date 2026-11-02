-- Prepared locally; apply only as part of the approved Online BIN release.
-- DB values override code defaults. No cards, orders or wallet rows change.
SET NAMES utf8mb4;
START TRANSACTION;

SELECT `key`, value FROM admin_settings
WHERE `key` IN ('CARD_ONLINE_PROMO_BIN', 'ONLINE_OPERATION_FEE_USD', 'ONLINE_CARD_VALIDITY_TEXT')
FOR UPDATE;

INSERT INTO admin_settings (`key`, value, description) VALUES
('CARD_ONLINE_PROMO_BIN', 'Сингапур', 'Online issuing country: O-Plata replacement type, 2026-11-02'),
('ONLINE_OPERATION_FEE_USD', '0.8', 'Online transactionConstantFee from O-Plata cardTypesList, 2026-11-02'),
('ONLINE_CARD_VALIDITY_TEXT', '2 года', 'Online validityPeriod=24 months from O-Plata, 2026-11-02')
ON DUPLICATE KEY UPDATE value = VALUES(value), description = VALUES(description);

-- Correct the old generic limit only in the card-fees FAQ, leaving custom
-- content and all other FAQ entries intact.
UPDATE faqs
SET answer = REPLACE(answer, 'Лимит на одну операцию: до $50 000', 'Лимит на одну операцию для Online: до $10 000')
WHERE question = 'Какие комиссии и лимиты у виртуальных карт?'
  AND answer LIKE '%Лимит на одну операцию: до $50 000%';

-- cardTypesList confirms the operation fee, but provides no decline tariff
-- or lifetime turnover limit. Do not present those old claims as confirmed.
UPDATE faqs
SET answer = REPLACE(
    REPLACE(answer,
        'Комиссия за каждую операцию: 0,8$ (Комиссия списывается, даже если операция оказалась отклонена)',
        'Online: комиссия за операцию — $0,8. Отклонённые операции тарифицируются банком отдельно.'),
    CONCAT('Общий лимит карты: до $2 000 000', CHAR(10)), '')
WHERE question = 'Какие комиссии и лимиты у виртуальных карт?';

COMMIT;

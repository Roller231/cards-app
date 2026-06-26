-- Add card issuance pricing settings
-- Run this after starting the application for the first time

INSERT INTO admin_settings (key, value, description) VALUES
('CARD_ISSUANCE_PRICE_USD', '10.0', 'Card issuance price (USD) - user pays this fixed amount')
ON DUPLICATE KEY UPDATE description = VALUES(description);

INSERT INTO admin_settings (key, value, description) VALUES
('CARD_INITIAL_BALANCE_USD', '5.0', 'Card initial balance (USD) - transferred from parent to user O-Plata account')
ON DUPLICATE KEY UPDATE description = VALUES(description);

-- Remove old settings that are no longer used
DELETE FROM admin_settings WHERE key IN (
    'ONLINE_ISSUE_FEE_USD',
    'ONLINE_PLUS_ISSUE_FEE_USD',
    'ISSUE_APPLY_TOPUP_MARKUP'
);

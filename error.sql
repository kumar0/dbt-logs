"""
UPDATE {{ source('dpiibc_prepared_layer', 'valuation') }} target
SET is_latest_balance = 'N',
    updated_time_stamp = timestamp '{{ run_started_at }}'
WHERE target.is_latest_balance = 'Y'
    AND target.valuation_entity_type = 'CASH_BALANCE'
    AND target.is_current = 'Y'
    AND (target.account_nk, target.valuation_date_type, target.source_system, target.effective_date) IN (
        SELECT
            account_nk,
            valuation_date_type,
            source_system,
            effective_date
        FROM (
            SELECT
                account_nk,
                valuation_date_type,
                source_system,
                effective_date,
                ROW_NUMBER() OVER (
                    PARTITION BY account_nk, valuation_date_type, source_system
                    ORDER BY effective_date DESC
                ) AS rn
            FROM {{ source('dpiibc_prepared_layer', 'valuation') }}
            WHERE valuation_entity_type = 'CASH_BALANCE'
              AND is_current = 'Y'
              AND is_latest_balance = 'Y'
        )
        WHERE rn > 1
    )
"""
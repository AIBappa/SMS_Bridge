async def validate_blacklist_check(sms, pool):
    # Use structured mobile data for blacklist tracking
    country_code = sms.country_code if hasattr(sms, 'country_code') and sms.country_code else "91"
    local_mobile = sms.local_mobile if hasattr(sms, 'local_mobile') and sms.local_mobile else sms.sender_number
    
    async with pool.acquire() as conn:
        threshold = int(await conn.fetchval("SELECT setting_value FROM system_settings WHERE setting_key = 'blacklist_threshold'"))
        count = await conn.fetchval("""
            INSERT INTO count_sms (sender_number, message_count, country_code, local_mobile) VALUES ($1, 1, $2, $3)
            ON CONFLICT (sender_number) DO UPDATE SET 
                message_count = count_sms.message_count + 1,
                country_code = EXCLUDED.country_code,
                local_mobile = EXCLUDED.local_mobile
            RETURNING message_count
        """, local_mobile, country_code, local_mobile)
        if count > threshold:
            await conn.execute("""
                INSERT INTO blacklist_sms (sender_number, country_code, local_mobile) VALUES ($1, $2, $3) 
                ON CONFLICT (sender_number) DO UPDATE SET
                    country_code = EXCLUDED.country_code,
                    local_mobile = EXCLUDED.local_mobile
            """, local_mobile, country_code, local_mobile)
            return 2  # fail
    return 1  # pass
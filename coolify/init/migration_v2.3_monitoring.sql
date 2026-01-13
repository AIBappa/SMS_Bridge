-- SMS Bridge v2.3 - Monitoring Port Access Migration
-- Adds table for tracking monitoring port access audit trail

-- Create monitoring_port_access table
CREATE TABLE IF NOT EXISTS monitoring_port_access (
    id SERIAL PRIMARY KEY,
    service VARCHAR(50) NOT NULL,
    external_port INTEGER NOT NULL,
    internal_port INTEGER NOT NULL,
    action VARCHAR(20) NOT NULL CHECK (action IN ('opened', 'closed', 'expired')),
    opened_by VARCHAR(100) NOT NULL,
    opened_at TIMESTAMP NOT NULL,
    closed_at TIMESTAMP,
    expires_at TIMESTAMP,
    duration_minutes INTEGER,
    server_ip VARCHAR(50),
    connection_info JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes for common queries
    INDEX idx_service (service),
    INDEX idx_opened_at (opened_at DESC),
    INDEX idx_opened_by (opened_by),
    INDEX idx_action (action)
);

-- Add comment to table
COMMENT ON TABLE monitoring_port_access IS 'Audit trail for monitoring port access events';

-- Add comments to columns
COMMENT ON COLUMN monitoring_port_access.service IS 'Service name: metrics, postgres, redis, pgbouncer';
COMMENT ON COLUMN monitoring_port_access.external_port IS 'External port number exposed to internet';
COMMENT ON COLUMN monitoring_port_access.internal_port IS 'Internal container port';
COMMENT ON COLUMN monitoring_port_access.action IS 'Action performed: opened, closed, expired';
COMMENT ON COLUMN monitoring_port_access.opened_by IS 'Admin username who opened the port';
COMMENT ON COLUMN monitoring_port_access.opened_at IS 'Timestamp when port was opened';
COMMENT ON COLUMN monitoring_port_access.closed_at IS 'Timestamp when port was closed (NULL if still open)';
COMMENT ON COLUMN monitoring_port_access.expires_at IS 'Scheduled expiration time';
COMMENT ON COLUMN monitoring_port_access.duration_minutes IS 'Requested duration in minutes';
COMMENT ON COLUMN monitoring_port_access.server_ip IS 'Server IP address at time of opening';
COMMENT ON COLUMN monitoring_port_access.connection_info IS 'JSON with connection details (host, port, connection string)';

-- Create view for currently open ports
CREATE OR REPLACE VIEW monitoring_ports_currently_open AS
SELECT 
    service,
    external_port,
    internal_port,
    opened_by,
    opened_at,
    expires_at,
    EXTRACT(EPOCH FROM (expires_at - CURRENT_TIMESTAMP))/60 AS minutes_remaining,
    server_ip,
    connection_info
FROM monitoring_port_access
WHERE action = 'opened'
  AND closed_at IS NULL
  AND expires_at > CURRENT_TIMESTAMP
ORDER BY expires_at ASC;

COMMENT ON VIEW monitoring_ports_currently_open IS 'Shows all currently open monitoring ports with time remaining';

-- Create view for port access history
CREATE OR REPLACE VIEW monitoring_port_access_history AS
SELECT 
    id,
    service,
    external_port,
    action,
    opened_by,
    opened_at,
    closed_at,
    CASE 
        WHEN closed_at IS NOT NULL 
        THEN EXTRACT(EPOCH FROM (closed_at - opened_at))/60
        ELSE NULL
    END AS actual_duration_minutes,
    duration_minutes AS requested_duration_minutes,
    expires_at,
    server_ip,
    created_at
FROM monitoring_port_access
ORDER BY opened_at DESC;

COMMENT ON VIEW monitoring_port_access_history IS 'Historical view of all port access events';

-- Create function to record port opening
CREATE OR REPLACE FUNCTION record_port_opened(
    p_service VARCHAR,
    p_external_port INTEGER,
    p_internal_port INTEGER,
    p_opened_by VARCHAR,
    p_duration_minutes INTEGER,
    p_server_ip VARCHAR,
    p_connection_info JSONB
) RETURNS INTEGER AS $$
DECLARE
    v_expires_at TIMESTAMP;
    v_id INTEGER;
BEGIN
    v_expires_at := CURRENT_TIMESTAMP + (p_duration_minutes || ' minutes')::INTERVAL;
    
    INSERT INTO monitoring_port_access (
        service,
        external_port,
        internal_port,
        action,
        opened_by,
        opened_at,
        expires_at,
        duration_minutes,
        server_ip,
        connection_info
    ) VALUES (
        p_service,
        p_external_port,
        p_internal_port,
        'opened',
        p_opened_by,
        CURRENT_TIMESTAMP,
        v_expires_at,
        p_duration_minutes,
        p_server_ip,
        p_connection_info
    ) RETURNING id INTO v_id;
    
    RETURN v_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION record_port_opened IS 'Records a port opening event in the audit trail';

-- Create function to record port closing
CREATE OR REPLACE FUNCTION record_port_closed(
    p_service VARCHAR,
    p_external_port INTEGER,
    p_closed_by VARCHAR,
    p_auto_closed BOOLEAN DEFAULT FALSE
) RETURNS VOID AS $$
DECLARE
    v_action VARCHAR(20);
BEGIN
    v_action := CASE WHEN p_auto_closed THEN 'expired' ELSE 'closed' END;
    
    -- Update the most recent open record for this service
    UPDATE monitoring_port_access
    SET 
        closed_at = CURRENT_TIMESTAMP,
        action = v_action
    WHERE service = p_service
      AND external_port = p_external_port
      AND closed_at IS NULL
      AND id = (
          SELECT id 
          FROM monitoring_port_access 
          WHERE service = p_service 
            AND external_port = p_external_port
            AND closed_at IS NULL
          ORDER BY opened_at DESC 
          LIMIT 1
      );
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION record_port_closed IS 'Records a port closing event in the audit trail';

-- Create function to find expired ports
CREATE OR REPLACE FUNCTION find_expired_ports()
RETURNS TABLE (
    service VARCHAR,
    external_port INTEGER,
    opened_by VARCHAR,
    opened_at TIMESTAMP,
    expires_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        mpa.service,
        mpa.external_port,
        mpa.opened_by,
        mpa.opened_at,
        mpa.expires_at
    FROM monitoring_port_access mpa
    WHERE mpa.action = 'opened'
      AND mpa.closed_at IS NULL
      AND mpa.expires_at <= CURRENT_TIMESTAMP
    ORDER BY mpa.expires_at ASC;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION find_expired_ports IS 'Finds all ports that have expired but not yet been closed';

-- Create view for audit trail summary
CREATE OR REPLACE VIEW monitoring_audit_summary AS
SELECT 
    DATE(opened_at) AS date,
    service,
    opened_by,
    COUNT(*) AS total_opens,
    SUM(CASE WHEN action = 'opened' AND closed_at IS NULL THEN 1 ELSE 0 END) AS currently_open,
    SUM(CASE WHEN action = 'closed' THEN 1 ELSE 0 END) AS manually_closed,
    SUM(CASE WHEN action = 'expired' THEN 1 ELSE 0 END) AS auto_closed,
    AVG(CASE 
        WHEN closed_at IS NOT NULL 
        THEN EXTRACT(EPOCH FROM (closed_at - opened_at))/60
        ELSE NULL
    END) AS avg_duration_minutes
FROM monitoring_port_access
GROUP BY DATE(opened_at), service, opened_by
ORDER BY date DESC, service, opened_by;

COMMENT ON VIEW monitoring_audit_summary IS 'Summary of port access by date, service, and user';

-- Insert default admin user if not exists (for testing)
-- This should be removed or modified in production
-- INSERT INTO admin_users (username, password_hash, created_at)
-- VALUES ('admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU7kNHR4QHXS', CURRENT_TIMESTAMP)
-- ON CONFLICT (username) DO NOTHING;

-- Grant permissions (adjust as needed for your setup)
-- GRANT SELECT, INSERT, UPDATE ON monitoring_port_access TO sms_bridge_app;
-- GRANT SELECT ON monitoring_ports_currently_open TO sms_bridge_app;
-- GRANT SELECT ON monitoring_port_access_history TO sms_bridge_app;
-- GRANT SELECT ON monitoring_audit_summary TO sms_bridge_app;
-- GRANT EXECUTE ON FUNCTION record_port_opened TO sms_bridge_app;
-- GRANT EXECUTE ON FUNCTION record_port_closed TO sms_bridge_app;
-- GRANT EXECUTE ON FUNCTION find_expired_ports TO sms_bridge_app;

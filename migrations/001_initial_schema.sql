-- =============================================================================
-- CBI Initial Schema Migration
-- Community Based Intelligence - Health Surveillance System
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Extensions
-- -----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- -----------------------------------------------------------------------------
-- ENUM Types
-- -----------------------------------------------------------------------------

-- Report status workflow
CREATE TYPE report_status AS ENUM (
    'open',
    'investigating',
    'resolved',
    'false_alarm'
);

-- Urgency levels for triage
CREATE TYPE urgency_level AS ENUM (
    'critical',
    'high',
    'medium',
    'low'
);

-- Alert classification types
CREATE TYPE alert_type AS ENUM (
    'suspected_outbreak',
    'cluster',
    'single_case',
    'rumor'
);

-- Suspected disease types
CREATE TYPE disease_type AS ENUM (
    'cholera',
    'dengue',
    'malaria',
    'measles',
    'meningitis',
    'unknown'
);

-- Reporter relationship to cases
CREATE TYPE reporter_rel AS ENUM (
    'self',
    'family',
    'neighbor',
    'health_worker',
    'community_leader',
    'other'
);

-- Link types for case clustering
CREATE TYPE link_type AS ENUM (
    'geographic',
    'temporal',
    'symptom',
    'manual'
);

-- -----------------------------------------------------------------------------
-- Tables
-- -----------------------------------------------------------------------------

-- Reporters: Community members who submit reports (minimal PII)
CREATE TABLE reporters (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    phone_hash VARCHAR(64) UNIQUE NOT NULL,
    phone_encrypted BYTEA NOT NULL,
    preferred_language VARCHAR(5) DEFAULT 'ar',
    total_reports INTEGER DEFAULT 0,
    first_report_at TIMESTAMPTZ,
    last_report_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Officers: Health officers who receive and act on reports
CREATE TABLE officers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    region VARCHAR(100),
    role VARCHAR(50) DEFAULT 'officer',
    is_active BOOLEAN DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Reports: Health incident reports from community
CREATE TABLE reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reporter_id UUID REFERENCES reporters(id) ON DELETE SET NULL,
    officer_id UUID REFERENCES officers(id) ON DELETE SET NULL,
    conversation_id VARCHAR(100) NOT NULL,
    status report_status DEFAULT 'open',

    -- MVS (Minimum Viable Signal) Data
    symptoms TEXT[] DEFAULT '{}',
    suspected_disease disease_type DEFAULT 'unknown',
    reporter_relation reporter_rel,
    location_text TEXT,
    location_normalized VARCHAR(200),
    location_point GEOGRAPHY(POINT, 4326),
    onset_text TEXT,
    onset_date DATE,
    cases_count INTEGER DEFAULT 1,
    deaths_count INTEGER DEFAULT 0,
    affected_groups TEXT,

    -- Classification (set by Surveillance Agent)
    urgency urgency_level DEFAULT 'medium',
    alert_type alert_type DEFAULT 'single_case',
    data_completeness FLOAT DEFAULT 0.0,
    confidence_score FLOAT,

    -- Raw data
    raw_conversation JSONB DEFAULT '[]'::jsonb,
    extracted_entities JSONB DEFAULT '{}'::jsonb,

    -- Metadata
    source VARCHAR(20) DEFAULT 'telegram',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,

    -- Constraints
    CONSTRAINT valid_completeness CHECK (data_completeness >= 0 AND data_completeness <= 1),
    CONSTRAINT valid_confidence CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    CONSTRAINT valid_counts CHECK (cases_count >= 0 AND deaths_count >= 0)
);

-- Report Links: Connections between related cases for outbreak detection
CREATE TABLE report_links (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id_1 UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    report_id_2 UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    link_type link_type NOT NULL,
    confidence FLOAT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(50) DEFAULT 'surveillance_agent',

    -- Constraints
    CONSTRAINT different_reports CHECK (report_id_1 != report_id_2),
    CONSTRAINT valid_link_confidence CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT unique_link UNIQUE (report_id_1, report_id_2, link_type)
);

-- Notifications: Alerts sent to health officers
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id UUID REFERENCES reports(id) ON DELETE CASCADE,
    officer_id UUID REFERENCES officers(id) ON DELETE CASCADE,
    urgency urgency_level NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    channels TEXT[] DEFAULT '{dashboard}',
    metadata JSONB DEFAULT '{}'::jsonb,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    read_at TIMESTAMPTZ,
    dismissed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Audit Logs: Track important system events
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    action VARCHAR(50) NOT NULL,
    actor_type VARCHAR(20) NOT NULL,
    actor_id VARCHAR(100),
    changes JSONB DEFAULT '{}'::jsonb,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Conversation States: Redis backup for conversation state
CREATE TABLE conversation_states (
    conversation_id VARCHAR(100) PRIMARY KEY,
    reporter_id UUID REFERENCES reporters(id) ON DELETE SET NULL,
    state JSONB NOT NULL DEFAULT '{}'::jsonb,
    mode VARCHAR(20) DEFAULT 'listening',
    turn_count INTEGER DEFAULT 0,
    last_message_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- Indexes
-- -----------------------------------------------------------------------------

-- Reporters
CREATE INDEX idx_reporters_phone_hash ON reporters(phone_hash);
CREATE INDEX idx_reporters_last_report ON reporters(last_report_at DESC);

-- Officers
CREATE INDEX idx_officers_email ON officers(email);
CREATE INDEX idx_officers_region ON officers(region);
CREATE INDEX idx_officers_active ON officers(is_active) WHERE is_active = TRUE;

-- Reports
CREATE INDEX idx_reports_reporter ON reports(reporter_id);
CREATE INDEX idx_reports_officer ON reports(officer_id);
CREATE INDEX idx_reports_conversation ON reports(conversation_id);
CREATE INDEX idx_reports_status ON reports(status);
CREATE INDEX idx_reports_urgency ON reports(urgency);
CREATE INDEX idx_reports_disease ON reports(suspected_disease);
CREATE INDEX idx_reports_created ON reports(created_at DESC);
CREATE INDEX idx_reports_location ON reports USING GIST(location_point);
CREATE INDEX idx_reports_open_urgent ON reports(urgency, created_at DESC)
    WHERE status = 'open';

-- Report Links
CREATE INDEX idx_report_links_report1 ON report_links(report_id_1);
CREATE INDEX idx_report_links_report2 ON report_links(report_id_2);
CREATE INDEX idx_report_links_type ON report_links(link_type);

-- Notifications
CREATE INDEX idx_notifications_officer ON notifications(officer_id);
CREATE INDEX idx_notifications_report ON notifications(report_id);
CREATE INDEX idx_notifications_unread ON notifications(officer_id, sent_at DESC)
    WHERE read_at IS NULL;

-- Audit Logs
CREATE INDEX idx_audit_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_actor ON audit_logs(actor_type, actor_id);
CREATE INDEX idx_audit_created ON audit_logs(created_at DESC);

-- Conversation States
CREATE INDEX idx_conversation_reporter ON conversation_states(reporter_id);
CREATE INDEX idx_conversation_expires ON conversation_states(expires_at)
    WHERE expires_at IS NOT NULL;

-- -----------------------------------------------------------------------------
-- Triggers
-- -----------------------------------------------------------------------------

-- Function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at trigger to all relevant tables
CREATE TRIGGER update_reporters_updated_at
    BEFORE UPDATE ON reporters
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_officers_updated_at
    BEFORE UPDATE ON officers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_reports_updated_at
    BEFORE UPDATE ON reports
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_conversation_states_updated_at
    BEFORE UPDATE ON conversation_states
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to increment reporter's total_reports
CREATE OR REPLACE FUNCTION increment_reporter_reports()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE reporters
    SET
        total_reports = total_reports + 1,
        last_report_at = NOW(),
        first_report_at = COALESCE(first_report_at, NOW())
    WHERE id = NEW.reporter_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER increment_reports_on_insert
    AFTER INSERT ON reports
    FOR EACH ROW
    WHEN (NEW.reporter_id IS NOT NULL)
    EXECUTE FUNCTION increment_reporter_reports();

-- -----------------------------------------------------------------------------
-- Initial Data
-- -----------------------------------------------------------------------------

-- Create a default admin officer (password: admin123 - CHANGE IN PRODUCTION)
INSERT INTO officers (id, email, password_hash, name, role, region)
VALUES (
    uuid_generate_v4(),
    'admin@cbi.local',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.VTtYA/pWrWuqGi',
    'System Admin',
    'admin',
    'National'
);

-- =============================================================================
-- CBI Database Initialization
-- Enable required PostgreSQL extensions
-- =============================================================================

-- PostGIS for geospatial queries (outbreak mapping)
CREATE EXTENSION IF NOT EXISTS postgis;

-- UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Fuzzy string matching (useful for location normalization)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'CBI database extensions initialized successfully';
END $$;

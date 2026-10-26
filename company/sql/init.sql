-- Initialize Keystone database
-- This runs on first container start via docker-entrypoint-initdb.d

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create a separate database for Langfuse if it doesn't exist
SELECT 'CREATE DATABASE langfuse OWNER keystone'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'langfuse')\gexec

-- Create application role that cannot bypass RLS
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'keystone_app') THEN
        CREATE ROLE keystone_app LOGIN PASSWORD 'keystone_app_password';
    END IF;
END $$;

-- Grant connect
GRANT CONNECT ON DATABASE keystone TO keystone_app;
GRANT USAGE ON SCHEMA public TO keystone_app;

-- After tables are created by the seed script, RLS policies
-- will be applied in a migration step (Phase 2).
-- The keystone_app role will NOT have BYPASSRLS.
ALTER ROLE keystone_app NOBYPASSRLS;

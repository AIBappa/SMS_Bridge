-- SMS Bridge Init Script for Coolify Deployment
-- Loads schema from root schema.sql (mounted via docker-compose)
-- postgres user is already superuser

\i /docker-entrypoint-initdb.d/schema.sql;

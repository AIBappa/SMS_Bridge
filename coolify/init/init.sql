-- SMS Bridge Init Script for Coolify Deployment
-- Just load the schema, postgres user is already superuser

\i /docker-entrypoint-initdb.d/schema.sql;

-- Development-only role bootstrap; run using a database administrator, not the API.
SELECT format('CREATE ROLE silicon_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD %L', :'migration_password') \gexec
SELECT format('CREATE ROLE silicon_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD %L', :'app_password') \gexec
ALTER DATABASE silicon OWNER TO silicon_migrator;
ALTER SCHEMA public OWNER TO silicon_migrator;
REVOKE ALL ON DATABASE silicon FROM PUBLIC;
GRANT CONNECT ON DATABASE silicon TO silicon_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO silicon_app;

"""Sample config with a hardcoded credential (test fixture for source_audit)."""

# CWE-798: hardcoded credential baked into source.
DB_PASSWORD = "s3cr3t_admin_password"
DB_DSN = "postgres://app:" + DB_PASSWORD + "@db/app"

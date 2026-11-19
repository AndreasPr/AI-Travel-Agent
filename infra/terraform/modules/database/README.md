# Database module

validated, not deployed

Consumes only the network module's two **private** subnet IDs. Public access is
false, encryption uses the provided customer-managed KMS key, multi-AZ is enabled,
backups are retained seven days, and deletion protection/final snapshot are on.
`rds.force_ssl=1` requires TLS. The API SG alone may reach TCP 5432. RDS manages its
master password; Terraform never supplies a password and the API is not given it.
Existing KMS and enhanced-monitoring role policies require independent review.

RDS PostgreSQL supports pgvector on supported engine/extension versions. The
operator must verify the selected engine minor version against AWS's extension
matrix, then separately authorize installing the `vector` extension and migrations.
Terraform validation does not connect to PostgreSQL or install/verify pgvector.

Sources: [RDS extension versions](https://docs.aws.amazon.com/AmazonRDS/latest/PostgreSQLReleaseNotes/postgresql-extensions.html)
and [RDS PostgreSQL extensions](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Appendix.PostgreSQL.CommonDBATasks.Extensions.html).

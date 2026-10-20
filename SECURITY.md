# Security Policy

## Reporting a vulnerability

Please do not open public issues for security-sensitive reports.

Instead, send a private report to the repository maintainer and include:

- a summary of the issue,
- affected files or endpoints,
- reproduction steps,
- and any suggested mitigation.

## Security expectations

- Never commit secrets, keys, tokens, `.env` files, or private infrastructure details.
- Use environment variables and example files instead of hardcoded credentials.
- Keep dependencies and tooling updated.
- Review any changes involving auth, data access, or external integrations before merging.

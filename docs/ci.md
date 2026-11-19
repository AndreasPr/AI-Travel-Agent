# CI on public pull requests

`.github/workflows/ci.yml` runs on pull requests, pushes to master and manual dispatch.
It uses hosted Ubuntu runners with read-only repository permissions. The smoke job
is pinned to Ubuntu 24.04 for compatibility with Playwright 1.51; its browser cache
includes the Ubuntu release and architecture. Diagnostics and cleanup use a
non-secret interpolation placeholder if failure occurs before the temporary JWT key
is generated. That placeholder is never used to start the stack. No PR job uses
repository secrets, paid providers, live models, model downloads, registry pushes,
`pull_request_target`, or `continue-on-error`. Test signing keys are generated in the
job, masked and discarded. The manual live evaluation workflow remains separate.

## What each job proves

These are engineering time budgets, **not measured hosted-run durations**. Target:
roughly 15 minutes end-to-end; queue time and cold caches can exceed that. Measure the
first PR's critical path before claiming the target was met.

| Job | Evidence | Target / hard timeout |
|---|---|---|
| lint | Ruff and ESLint accept tracked source | 2–3 / 5 min |
| type-check | Existing backend mypy policy passes | 3–5 / 10 min |
| unit | Offline tests and contracts; backend coverage >=70%; coverage.xml artifact | 3–5 / 10 min |
| integration | Disposable Testcontainers pgvector, migrations, synthetic pipeline, auth and quotas | 3–5 / 10 min |
| frontend | Clean npm install, Vitest and Next production build | 3–5 / 7 min |
| docker (api/web) | Production Dockerfiles build; local image artifacts, no publishing | 5–8 / 12 min each |
| trivy (api/web) | Exact built images have no unexcepted HIGH/CRITICAL advisories, including unfixed findings | 2–3 / 6 min after builds |
| pip-audit | Installed CPU Python dependency graph has no unexcepted known advisories | 3–5 / 10 min |
| npm-audit | npm dependency graph has no HIGH/CRITICAL advisory | 1–2 / 5 min |
| gitleaks | Full checked-out git history passes redacted CLI secret scan | 1–2 / 5 min |
| eval | Calls existing reusable eval-gate.yml; recorded/offline baseline gate, no credentials | 1–3 / 5 min |
| smoke | Exact built images: Playwright register/login/chat/citation flow and short two-session k6 SSE ramp | 3–5 / 7 min after builds |

Synthetic scenarios are **scripted tests of the pipeline**, not model behavior.
The real full-chat replay test explicitly skips until its actual transcript exists.
Legacy integration tests requiring a user's database are not included in the hosted
container target. The evaluation gate retains its existing recorded/synthetic
provenance rules. No test result is a claim of live model quality.

Independent jobs run in parallel. Docker builds are reused by both scanners and smoke;
the browser job never rebuilds them. Superseded runs are cancelled per PR. Old
`test-suite.yml` and `gitleaks.yml` are manual-only to avoid duplicate automatic jobs.
Existing branch protection requiring their old names must be updated deliberately.

## Caches and artifacts

- setup-python caches pip downloads; a platform/requirements-keyed .venv-ci cache
  shares the installed CPU environment between Python jobs.
- CPU PyTorch installs in its own pip process; its private index must never apply
  to the application/test requirements install.
- setup-node caches npm downloads using package-lock.json.
- Chromium cache is keyed by OS and the pinned Playwright version; OS browser
  dependencies are installed even on a cache hit.
- Hugging Face cache is keyed by platform, model configuration and dependencies.
  Offline tests do not populate it with new weights; an empty cache is normal.
- BuildKit's GitHub cache is scoped per image. Trivy caches its advisory database.
- Coverage, raw audit reports, and environment-labeled synthetic performance JSON
  are uploaded. Image artifacts expire after one day.

Caches contain no credentials, .env files or private model data. Fork PR caches
are untrusted inputs and are not reused by a privileged deployment workflow.
See [GitHub cache boundaries](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching).

## Security policy

Security jobs remain blocking. npm audit uses `--audit-level=high`. Trivy collects
all severities and the policy gate blocks HIGH/CRITICAL, even without an upstream fix.
pip-audit blocks every reported advisory except explicitly reviewed entries.

`config/security-exceptions.json` is the narrowly scoped exception registry:
package, exact installed version, advisory, scanner, severity, reachability, reason
and review date. `scripts/ci_security.py` fails on unknown findings, expired entries,
malformed reports or scanner errors. The native `.trivyignore` stays empty because
an advisory-only exclusion cannot express our package/version boundary. Raw findings
remain in artifacts; accepted findings are counted as excepted, never fixed.

See `docs/ci-security-exceptions.md` for every remaining finding and the follow-up
migration branches. No blanket package ignore or `--ignore-unfixed` is permitted.
A severity marked UNKNOWN means the scanner did not provide a score; it is not low risk.

## CodeQL and Dependabot

The owner reports CodeQL default setup is already enabled (repository settings/M7).
No duplicate CodeQL workflow is added. Confirm Python and JavaScript/TypeScript
analysis in the Security tab; settings were not independently verified locally.
Dependabot checks pip, npm, GitHub Actions and both Dockerfiles weekly. Its PRs run
this same secret-free pipeline; dependency updates are never automatically merged.

## Verification and manual step M14

Local checks: `actionlint .github/workflows/*.yml`, `make lint`, `make typecheck`,
`make test-ci`, `make test-containers`, `npm ci`, `npm test`, `npm run build`.
Python must be >=3.11.5 for the approved SoupSieve security update; Docker uses 3.12.
See docs/TEST_SUITE.md for synthetic stack/Playwright/k6 commands.

Push feat/ci and open its PR. Verify every job, inspect raw security reports and the
coverage/performance artifacts, and record total elapsed time. Configure required
checks for the new CI jobs, replacing obsolete Test suite names. Confirm README
badges render. Check a fork PR without repository secrets. These hosted/settings
checks cannot be claimed from local runs alone.

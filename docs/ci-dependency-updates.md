# Dependency security changes — 2026-11-19

All versions below are from the repository diff and measured scanner output. No framework or ML major migration was performed. Exceptions are listed individually in [ci-security-exceptions.md](ci-security-exceptions.md).

## npm

Audit package counts before: {'info': 0, 'low': 2, 'moderate': 2, 'high': 6, 'critical': 1, 'total': 11}; after: {'info': 0, 'low': 0, 'moderate': 0, 'high': 0, 'critical': 0, 'total': 0}.

| Package | Direct/transitive | Before severity | Old installed versions | New installed versions |
|---|---|---|---|---|
| @eslint/plugin-kit | transitive | low | 0.2.7 | 0.4.1 |
| @humanfs/node | transitive | moderate | 0.16.6 | 0.16.8 |
| ajv | transitive | moderate | 6.12.6 | 6.15.0 |
| brace-expansion | transitive | high | 1.1.11, 2.0.1 | 1.1.22, 5.0.13 |
| eslint | direct | low | 9.22.0 | 9.39.5 |
| flatted | transitive | high | 3.3.3 | 3.4.4 |
| js-yaml | transitive | high | 4.1.0 | 4.3.2 |
| minimatch | transitive | high | 3.1.2, 9.0.5 | 11.0.1, 3.1.5 |
| next | direct | critical | 15.2.2 | 15.5.29 |
| postcss | transitive | high | 8.4.31, 8.5.32 | 8.5.32, 8.5.33 |
| sharp | transitive | high | 0.33.5 | 0.35.5 |

Next and its matching ESLint config moved together to 15.5.29. The approved minimatch transitive major uses an override limited to the old ^9 range; Next’s nested PostCSS override is 8.5.32. Related lockfile dependency changes follow those updates. No force audit fix was used.

## Python pins

Pins are direct requirements entries; several pin dependencies used transitively by Jupyter, HTTP clients or build tooling. Severity is taken from Trivy when available; pip-audit does not supply severity.

| Pin | Old | New | Reason/advisories confirmed by initial audits |
|---|---|---|---|
| anyio | 4.8.0 | 4.14.2 | CVE-2026-63374 (CRITICAL); CVE-2026-64847 (MEDIUM) |
| bleach | 6.2.0 | 6.4.0 | GHSA-8rfp-98v4-mmr6 (LOW); GHSA-gj48-438w-jh9v (MEDIUM) |
| certifi | 2025.1.31 | 2026.10.18 | GHSA-6q48-6c7w-9gw2 (CRITICAL) |
| fsspec | 2025.3.0 | 2026.6.0 | CVE-2026-104851 (HIGH) |
| h11 | 0.14.0 | 0.16.0 | CVE-2025-43859 (CRITICAL) |
| httpcore | 1.0.7 | 1.0.9 | Required compatible h11 >=0.16 client dependency. |
| idna | 3.10 | 3.15 | CVE-2026-45409 (MEDIUM) |
| jupyter_core | 5.7.2 | 5.8.1 | CVE-2025-30167 (HIGH) |
| jupyter_server | 2.15.0 | 2.21.0 | CVE-2025-61669 (MEDIUM); CVE-2026-35397 (HIGH); CVE-2026-40110 (HIGH); CVE-2026-40934 (HIGH); CVE-2026-44727 (CRITICAL); CVE-2026-86049 (HIGH) |
| jupyterlab | 4.3.6 | 4.6.4 | CVE-2025-59842 (LOW); CVE-2026-102830 (MEDIUM); CVE-2026-102904 (MEDIUM); CVE-2026-40171 (HIGH); CVE-2026-42266 (HIGH); CVE-2026-42557 (HIGH); CVE-2026-73415 (HIGH); CVE-2026-73417 (HIGH); GHSA-h5v5-8746-g7mm (MEDIUM); GHSA-vmhf-c436-hxj4 (MEDIUM); GHSA-whvh-wf3x-g77j (LOW) |
| jupyterlab_server | 2.27.3 | 2.28.0 | JupyterLab 4.6.4 requires >=2.28.0; previous 2.27.3 conflicts. |
| mistune | 3.1.2 | 3.3.3 | CVE-2026-115355 (HIGH); CVE-2026-33079 (HIGH); CVE-2026-44708 (MEDIUM); CVE-2026-44896 (MEDIUM); CVE-2026-44897 (MEDIUM); CVE-2026-49851 (HIGH); CVE-2026-59922 (HIGH); CVE-2026-59923 (MEDIUM); CVE-2026-59924 (MEDIUM); CVE-2026-59925 (HIGH); CVE-2026-59926 (MEDIUM); CVE-2026-59927 (MEDIUM); CVE-2026-59928 (HIGH); CVE-2026-59929 (MEDIUM); CVE-2026-59930 (MEDIUM) |
| nbconvert | 7.16.6 | 7.17.2 | CVE-2025-53000 (HIGH); CVE-2026-114140 (HIGH); CVE-2026-39377 (MEDIUM); CVE-2026-39378 (MEDIUM); CVE-2026-6658 (MEDIUM) |
| nltk | 3.9.1 | 3.10.4 | CVE-2025-14009 (CRITICAL); CVE-2025-71408 (HIGH); CVE-2026-0846 (HIGH); CVE-2026-0847 (HIGH); CVE-2026-12061 (HIGH); CVE-2026-12072 (HIGH); CVE-2026-12074 (HIGH); CVE-2026-12075 (HIGH); CVE-2026-12252 (HIGH); CVE-2026-12259 (MEDIUM); CVE-2026-12261 (MEDIUM); CVE-2026-12372 (LOW); CVE-2026-126296 (MEDIUM); CVE-2026-126297 (HIGH); CVE-2026-126298 (HIGH); CVE-2026-126299 (HIGH); CVE-2026-126300 (MEDIUM); CVE-2026-126301 (MEDIUM); CVE-2026-126303 (HIGH); CVE-2026-128134 (HIGH); CVE-2026-12876 (MEDIUM); CVE-2026-33230 (MEDIUM); CVE-2026-33231 (HIGH); CVE-2026-33236 (HIGH); CVE-2026-54293 (HIGH); CVE-2026-62385 (HIGH); CVE-2026-62388 (HIGH); CVE-2026-63311 (MEDIUM); CVE-2026-63312 (HIGH); CVE-2026-65915 (MEDIUM); CVE-2026-66393 (MEDIUM); CVE-2026-70626 (HIGH); CVE-2026-72818 (HIGH); CVE-2026-78680 (HIGH); CVE-2026-78681 (HIGH); CVE-2026-78682 (HIGH); CVE-2026-78683 (CRITICAL); CVE-2026-79657 (CRITICAL); CVE-2026-79674 (HIGH); CVE-2026-79675 (CRITICAL); CVE-2026-79676 (HIGH); CVE-2026-80205 (HIGH); CVE-2026-80206 (HIGH); CVE-2026-81722 (MEDIUM); CVE-2026-81723 (MEDIUM); CVE-2026-81724 (MEDIUM); CVE-2026-81725 (MEDIUM); CVE-2026-81726 (HIGH); CVE-2026-81727 (MEDIUM); GHSA-j456-xh4h-cpf2 (HIGH) |
| notebook | 7.3.3 | 7.6.3 | CVE-2026-40171 (HIGH); CVE-2026-42557 (HIGH) |
| packaging | 24.2 | 26.3 | Security-fixed virtualenv requires packaging >=26.3. |
| platformdirs | 4.3.6 | 4.4.0 | Security-fixed virtualenv requires platformdirs >=4.4. |
| Pygments | 2.19.1 | 2.20.0 | CVE-2026-4539 (LOW) |
| requests | 2.32.3 | 2.33.0 | CVE-2024-47081 (MEDIUM); CVE-2026-25645 (MEDIUM) |
| soupsieve | 2.6 | 4.0.0 | CVE-2026-126190 (HIGH); CVE-2026-126191 (HIGH); CVE-2026-126192 (MEDIUM); CVE-2026-126193 (MEDIUM); CVE-2026-49476 (HIGH); CVE-2026-49477 (HIGH); CVE-2026-85999 (MEDIUM); CVE-2026-86000 (MEDIUM); Approved major; unchanged suite and notebook execution pass on Python 3.12. |
| tornado | 6.4.2 | 6.6.1 | CVE-2025-47287 (HIGH); CVE-2025-67724 (MEDIUM); CVE-2025-67725 (HIGH); CVE-2025-67726 (HIGH); CVE-2026-115927 (MEDIUM); CVE-2026-116577 (MEDIUM); CVE-2026-116578 (LOW); CVE-2026-126347 (LOW); CVE-2026-31958 (HIGH); CVE-2026-35536 (HIGH); CVE-2026-49853 (HIGH); CVE-2026-49854 (LOW); CVE-2026-49855 (HIGH); CVE-2026-82397 (HIGH); GHSA-3hv7-mjh2-fv65 (MEDIUM); GHSA-78cv-mqj4-43f7 (MEDIUM); GHSA-8423-8fgw-73vq (MEDIUM); GHSA-c2m8-h5v5-343r (HIGH); GHSA-chx6-46f5-w4vp (HIGH); GHSA-pw6j-qg29-8w7f (MEDIUM) |
| urllib3 | 2.3.0 | 2.8.0 | CVE-2025-50181 (MEDIUM); CVE-2025-50182 (MEDIUM); CVE-2025-66418 (HIGH); CVE-2025-66471 (HIGH); CVE-2026-21441 (HIGH); CVE-2026-44431 (HIGH); CVE-2026-97687 (HIGH); CVE-2026-97689 (HIGH) |
| setuptools | unconstrained transitive | 78.1.1 | CVE-2025-47273 (HIGH); CVE-2026-59890 (MEDIUM); GHSA-xmj3-9gf7-h52w (LOW) |
| pytest | 8.3.3 | 9.0.3 | Approved test-only major; unchanged assertions pass on Python 3.12. |
| virtualenv | unconstrained transitive | 21.14.10 | Compatible dependency/security floor required by the approved resolver/audit updates. |
| pip | unconstrained transitive | 26.2.1 | CVE-2025-8869 (MEDIUM); CVE-2026-13346 (MEDIUM); CVE-2026-1703 (LOW); CVE-2026-3219 (MEDIUM); CVE-2026-6357 (MEDIUM); CVE-2026-8643 (MEDIUM) |

Clean combined runtime/dev installation and pip check passed inside Python 3.12.16. `jupyter lab --version` returned `4.6.4`; `jupyter nbconvert --execute` completed the existing `notebooks/Verify Python.ipynb`. The developer Python 3.11.4 environment cannot install SoupSieve 4; use Docker or Python >=3.11.5.

## Image and pip scan counts

Raw finding counts include repeated aliases in pip-audit and repeated affected binary packages from a shared OS source package; they are not unique CVE counts.

| Scan | Before | After |
|---|---|---|
| API Trivy | 394 {'LOW': 79, 'HIGH': 131, 'MEDIUM': 165, 'UNKNOWN': 10, 'CRITICAL': 9} | 248 {'LOW': 70, 'HIGH': 58, 'MEDIUM': 109, 'UNKNOWN': 10, 'CRITICAL': 1} |
| Web Trivy (intermediate image before runtime cleanup) | 93 {'HIGH': 28, 'MEDIUM': 29, 'LOW': 35, 'CRITICAL': 1} | 0 {} |
| pip-audit API runtime before / runtime + dev after | 265 entries in 24 packages | 29 entries in 5 packages |

The pip before/after environments differ by development tools; this is disclosed rather than presented as an identical-environment benchmark. Final CI audits both runtime and dev dependencies.

Runtime image fixes upgrade available OpenSSL/musl/zlib Alpine packages, upgrade Debian zlib, and remove npm/Corepack/Yarn from the Node runtime (which runs `node server.js`). The Python runtime clears obsolete base-image site-packages before copying the verified builder installation. A residual setuptools 70.3.0 finding comes from pip’s vendored build SBOM, while the installed runtime version is 78.1.1.

Strict policy evaluation: API Trivy 59 excepted findings; frontend Trivy zero findings; pip-audit 29 excepted entries. There are 67 exact registry entries after alias deduplication. This is **not** a vulnerability-free result. New findings and expired exceptions still fail. Local image results are ARM64; hosted AMD64 results and end-to-end CI duration remain to be verified.

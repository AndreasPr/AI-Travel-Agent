# Deep plan state machine

Validated locally, not deployed. Run `node scripts/validate_asl.cjs` after `npm ci`.
No AWS credentials, deployment or execution is required or authorized.

The Map mirrors bounded day concurrency (3), tool budget (12), timeout (90 seconds),
and one retry. Input contains `days`, `request`, and `functions` with operator-owned
`plan_day`, `merge`, `validate` function ARNs. No function implementations or IAM
permissions are deployed by this file. The day handler must enforce its tool budget,
authentication, ownership and quotas; ASL cannot enforce Python tool policy.

Day handlers return day itineraries or throw. Merge returns `complete=false` plus
failed dates without saving a partial trip, or `complete=true` and a merged plan.
Validation must use the trusted tool ledger and return `structurally_valid` and
`budget_met`; an otherwise-valid over-budget plan explicitly has `budget_met=false`.
The Python demo timeout is shorter than this reference machine for the free proxy.
Validation proves ASL structure, not availability or correctness of hypothetical handlers.

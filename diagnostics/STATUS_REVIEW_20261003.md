# CyberNet OS v2 Status Review - 2026-10-03

## Scope

Reviewed the live ISP v2 setup on `tserver@100.66.112.67` under `/home/tserver/isp_v2`.

## Current Status

- `isp_v2.service` is active and running Uvicorn on port `9911`.
- Native browser `alert()` / `confirm()` calls were not found in `templates` or `static` during the latest scan.
- Jinja templates parse successfully.
- `main.py` compiles successfully.
- Public routing should be verified after every live change:
  - `http://isp.tawreedflow.com/` should redirect to HTTPS.
  - `https://isp.tawreedflow.com/` should redirect to `/login?next=/`.

## Live Changes Present

The following templates currently contain UI helper replacements for old browser popups:

- `templates/approvals.html`
- `templates/collections.html`
- `templates/customers.html`
- `templates/olt.html`
- `templates/reseller_portal.html`
- `templates/resellers.html`

## Fix Added In This Pass

- Fixed a fallback bug in `templates/customers.html` where the code checked whether `cyberToast` existed, but the fallback branch still called `cyberToast`. The fallback now uses a console message instead of throwing another UI error.

## Important Notes

- Production is live. Keep changes narrow and back up files before editing.
- Do not reset, delete, or migrate customer data without a fresh database backup and explicit approval.
- Existing diagnostic/helper files from prior Antigravity work are under `diagnostics/antigravity_20261003`.
- Template backups created during this pass are preserved under `diagnostics/backups_20261003`.
- `olt_sync.trigger` is currently untracked on the live server; inspect before removing or committing.

## Recommended Next Steps

1. Perform a browser UI walkthrough for the changed screens: approvals, collections, customers, OLT, reseller portal, and resellers.
2. Use the Git commit from this review as the rollback point for the popup cleanup and status note.
3. Review `diagnostics/antigravity_20261003` and archive or keep only useful evidence.
4. Review `olt_sync.trigger` to confirm whether it is operational state or diagnostic leftovers.
5. Continue subscription/SaaS hardening: onboarding, billing plans, tenant separation, audit logs, and polished empty/loading/error states.

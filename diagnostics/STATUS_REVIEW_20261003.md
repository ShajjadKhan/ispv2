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

## Customer Edit UI Readability Follow-up - 2026-10-03

- Reviewed the saved tserver template copy at `tserver_templates_work/customer_edit.html` after the user reported that input text was hard to see and the edit page looked like basic HTML.
- Added page-scoped control styling: high-contrast values/placeholders, clearer labels, 44px minimum control height, visible keyboard focus, dark native date/select controls, and roomier mobile spacing with 16px input text.
- Follow-up from the supplied screenshot: styled native date inputs and `.btn-preset` actions, which were not covered by `.form-input` styling and therefore appeared as white browser-default controls.
- Version mismatch found: screenshot includes editable Customer Joining Date and Billing Cycle Start Date fields, but the saved `tserver_templates_work/customer_edit.html` does not include them. Treat the saved template as stale and do not deploy it over the live page until it is refreshed from the server.
- This edit is currently only in the local saved template copy. The SSH attempt to `tserver@100.66.112.67` returned `Permission denied`; no live files were read or changed and no customer data was accessed.
- Before deployment, compare this file with `/home/tserver/isp_v2/templates/customer_edit.html`, back up the live template, and then deploy and visually verify at desktop and mobile widths. Do not infer deployment from this local patch.
- Later the live SSH route became available. Current live template was downloaded and confirmed to include both editable dates. A backup was created at `/home/tserver/isp_v2/diagnostics/backups_uiux_20261003/customer_edit.html.before-input-ui-20261003` (SHA-256 `0310a01a710979fd37f7d17a6a347abf66ace14f331f1039e6fc393b8513ef2a`). No upload or live template edit has been made yet; user redirected the change to Antigravity.

## Customer Edit UI Readability & Dark Theme Deployment - 2026-10-03 (Antigravity)

### 1. Scope & Pre-Flight Validation
- **Target File:** `/home/tserver/isp_v2/templates/customer_edit.html`
- **Pre-Created Backup Verified:** `/home/tserver/isp_v2/diagnostics/backups_uiux_20261003/customer_edit.html.before-input-ui-20261003` (SHA-256 `0310a01a710979fd37f7d17a6a347abf66ace14f331f1039e6fc393b8513ef2a`).
- **Live File Pre-Edit Hash Confirmed:** SHA-256 `0310a01a...` matching backup bit-for-bit.
- **Fields Preserved 100%:**
  - `Customer Joining Date` (`#custJoinDate`, `name="join_date"`)
  - `Billing Cycle Start Date` (`#custBillingStartDate`, `name="billing_start_date"`)
  - All form IDs, names, form submit JSON serialization, billing calculations, and MikroTik provisioning logic remained completely untouched.

### 2. UI/CSS Enhancements Applied
- **Form Inputs & Selects:**
  - Added `.edit-page-container .form-input, .edit-page-container .form-select` styling with dark theme background (`#080e1b`), crisp borders (`rgba(148, 163, 184, 0.35)`), high-contrast text (`#f8fafc`), 44px min-height, and visible cyan focus rings (`box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.2)`).
  - High-contrast placeholder color (`#94a3b8`).
  - Styled native select drop-downs with dark option backgrounds (`#0f172a`) and custom SVG chevron.
- **Native Date Controls & Calendar Picker:**
  - Applied `color-scheme: dark;` to `input[type="date"]`, `input[type="number"]`, and `select`.
  - Inverted native calendar picker icon (`filter: invert(0.85);`) with hover state (`filter: invert(1);`) for dark background contrast.
  - Sized at 44px height for touch ergonomics.
- **Preset Action Buttons (`.btn-preset`):**
  - Styled `.btn-preset` controls (for `+30 Days`, `+60 Days`, `+90 Days`, `End of Current Month`, and Device Quotas `1 Device (Solo)`, `2 Devices`, `3 Devices`, etc.).
  - Dark CyberNet background (`#17233a`), subtle border (`rgba(148, 163, 184, 0.3)`), readable text (`#dbeafe`), and interactive cyan hover (`rgba(56, 189, 248, 0.16)`) and active states.
  - Visible keyboard focus rings (`outline: 2px solid #38bdf8; outline-offset: 2px;`).
- **Mobile & Tablet Responsiveness:**
  - Added `@media (max-width: 768px)` enforcing `16px !important` input font size (eliminating iOS auto-zoom).
  - Ensured touch targets meet WCAG 2.1 AA (44px min-height).
  - Single-column responsive layout for `.modal-grid-2` and `.modal-grid-3` on mobile viewports.

### 3. Verification & Safety Audit
- **Diff Inspection:** `git diff templates/customer_edit.html` confirmed strictly UI/CSS additions inside the `<style>` block (216 insertions, 1 deletion).
- **Template Syntax Validation:** Tested Jinja2 compilation with Python on live server (`diagnostics/check_template.py`) -> **SUCCESS: customer_edit.html parsed cleanly with Jinja2!**
- **Service Status:** `isp_v2.service` is active and running (`PID 1474068`).
- **HTTP Endpoint Verification:**
  - `GET /login` -> HTTP 200 OK
  - `GET /customers/2/edit` -> HTTP 200 OK
  - Automated 14-point test suite (`diagnostics/verify_edit_page.py`) passed **100% (14 / 14 PASSED)**.
- **Data Safety:** Zero database records, tables, or customer records were altered.

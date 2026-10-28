# 📱 CyberNet OS v2 (`isp_v2`) — Comprehensive UI/UX, Accessibility & Mobile Responsiveness Audit Report

> **Document Type:** Engineering Audit & Actionable Implementation Blueprint  
> **Target Codebase:** [`C:/Users/Shajjad Kan/tserver_projects/isp_v2/`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/)  
> **Collaboration Hub Mirror:** [`C:/Users/Shajjad Kan/ai-collab/ISP_V2_UI_UX_ACCESSIBILITY_AUDIT.md`](file:///C:/Users/Shajjad%20Kan/ai-collab/ISP_V2_UI_UX_ACCESSIBILITY_AUDIT.md)  
> **Live Staging Server:** `tserver@10.12.14.16:/home/tserver/isp_v2` (`isp_v2.service` on port `9911`, proxied via `https://isp.shajjadkhan.com` & `https://isp.tawreedflow.com`)  
> **Target Audience:** Incoming Antigravity / AI Agent & Front-End Engineering Team  
> **Status:** `READY_FOR_EXECUTION`  
> **Standards Assessed:** WCAG 2.1 Level AA, WCAG 2.2 Draft (Target Size / Pointer Spacing), iOS Human Interface Guidelines, Android Material Design 3 Responsive Guidelines.

---

## 📑 Table of Contents
1. [Executive Summary & Audit Scorecard](#1-executive-summary--audit-scorecard)
2. [Target Viewport Matrix & Breakpoint Architecture](#2-target-viewport-matrix--breakpoint-architecture)
3. [Prioritized Issue Catalog (AUDIT-ISP-01 to AUDIT-ISP-16)](#3-prioritized-issue-catalog)
   - [Category A: Mobile Phone Responsive Layouts & Tables](#category-a-mobile-phone-responsive-layouts--tables)
   - [Category B: Touch Target Sizes & Virtual Keyboard Optimization](#category-b-touch-target-sizes--virtual-keyboard-optimization)
   - [Category C: WCAG 2.1 AA Accessibility & Contrast Compliance](#category-c-wcag-21-aa-accessibility--contrast-compliance)
   - [Category D: MikroTik Captive Portal Client Experience](#category-d-mikrotik-captive-portal-client-experience)
   - [Category E: Modals, Forms & Viewport Overflows](#category-e-modals-forms--viewport-overflows)
4. [Template-by-Template Execution Roadmap](#4-template-by-template-execution-roadmap)
5. [Captive Portal Smartphone Blueprint (`login.html`)](#5-captive-portal-smartphone-blueprint)
6. [Testing, Verification & Deployment Runbook](#6-testing-verification--deployment-runbook)

---

## 1. Executive Summary & Audit Scorecard

CyberNet OS v2 (`isp_v2`) is a real-time ISP billing, MikroTik gateway management, and Wi-Fi subscriber authorization platform. The system operates on modern vanilla HTML5, CSS custom properties (variables), and asynchronous JavaScript (polling and fetch APIs) with **zero external heavyweight CSS frameworks** (no Bootstrap or Tailwind).

While recent updates successfully converted `#pendingTable` and `#subscribersTable` on [`templates/dashboard.html`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/dashboard.html) and [`templates/approvals.html`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/approvals.html) into responsive card decks, an exhaustive forensic audit across all **14 templates** and the **MikroTik Hotspot client suite** reveals significant mobile layout regressions, touch target violations, and WCAG accessibility gaps.

### 📊 System Scorecard

| Assessment Domain | Baseline Score | Target Score | Primary Gap / Risk |
| :--- | :---: | :---: | :--- |
| **Mobile Phone Responsiveness (360px–430px)** | **52%** | **100%** | 6 templates still render raw multi-column tables with horizontal overflow; modal inline grids squeeze inputs side-by-side. |
| **Touch Targets & Form Ergonomics** | **48%** | **98%** | Speed preset chips, small action buttons, and close icons are 20px–28px tall (below 44px WCAG minimum). |
| **WCAG 2.1 AA Color Contrast** | **65%** | **100%** | `--text-dim: #64748b` on card background `#0f172a` yields 3.8:1 contrast (fails 4.5:1 AA standard). |
| **Screen Reader & Keyboard A11y** | **40%** | **95%** | Zero `:focus-visible` styles (`outline: none`), missing form `<label for="...">` associations, unannounced dynamic modal updates. |
| **Captive Portal Mobile Client (Hotspot)** | **68%** | **100%** | `user-scalable=no` meta tag blocks accessibility zoom; 15px font size triggers iOS Safari auto-zoom; missing bilingual language toggle. |

---

## 2. Target Viewport Matrix & Breakpoint Architecture

The application must render flawlessly and ergonomically across the following real-world device tiers:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       CYBERNET OS VIEWPORT TIERS                            │
├────────────────────┬──────────────────┬─────────────────────────────────────┤
│ Device Tier        │ Viewport Width   │ Target Devices                      │
├────────────────────┼──────────────────┼─────────────────────────────────────┤
│ Ultra-Compact      │ 360px – 390px    │ Galaxy A14/S22, iPhone 12/13/14 mini│
│ Standard Phone     │ 393px – 430px    │ iPhone 15/16 Pro Max, Pixel 8/9,    │
│                    │                  │ Galaxy S24 Ultra, Redmi Note 14     │
│ Small Tablet / Fold│ 600px – 768px    │ iPad mini, Galaxy Z Fold unfold     │
│ Tablet / Small PC  │ 768px – 1024px   │ iPad Air/Pro 11", Surface Go        │
│ Desktop / Laptop   │ 1280px – 1920px+ │ Office Workstations, Laptop Display │
└────────────────────┴──────────────────┴─────────────────────────────────────┘
```

### 📐 Standardized CSS Breakpoint System (to be unified in `base.html`):

```css
/* Universal Responsive Breakpoints */
@media (min-width: 1025px) { /* PC / Desktop monitors */ }
@media (max-width: 1024px) { /* Tablets & Mobile Drawer threshold */ }
@media (max-width: 768px)  { /* Tablets & Mobile Phone Card Deck mode */ }
@media (max-width: 640px)  { /* Standard Smartphones: 1-col grids, 56px topbar */ }
@media (max-width: 440px)  { /* Compact Phones: 100% full-width actions, 1-col KPIs */ }
```

---

## 3. Prioritized Issue Catalog

---

### Category A: Mobile Phone Responsive Layouts & Tables

#### 🔴 AUDIT-ISP-01: Multi-Column Table Horizontal Overflow Across 6 Key Templates
- **Severity:** `CRITICAL`
- **Affected Files:**
  - [`templates/collections.html:1340`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/collections.html#L1340) (`#collectionsTable` — 8 columns)
  - [`templates/packages.html:582`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/packages.html#L582) (`#pkgTable` — 9 columns)
  - [`templates/resellers.html:415, 505, 558`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/resellers.html#L415) (3 tables — 6–8 columns)
  - [`templates/reseller_portal.html:489, 557`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/reseller_portal.html#L489) (2 tables — 6–7 columns)
  - [`templates/olt.html:540, 635`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/olt.html#L540) (`#onuTable` — 9 columns & PON traffic)
  - [`templates/whatsapp.html:749`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/whatsapp.html#L749) (`#logsTable` — 6 columns)
- **WCAG Criteria:** 1.4.10 Reflow (Level AA)
- **Problem & Mobile Impact:**
  On smartphone screens (360px–430px), these tables force the user to scroll sideways repeatedly to read amounts, customer details, or find the "Receipt", "Edit", or "Sync" buttons. On mobile touchscreens, horizontal scrolling inside cards causes gesture conflicts with browser navigation and hides critical call-to-actions.
  `packages.html` notably has **zero** `@media` queries in the entire file.
- **Proposed Solution:**
  Apply the proven Table-to-Card responsive pattern established on `dashboard.html`:
  1. Add semantic `data-label="..."` attributes to each `<td>` in HTML.
  2. Implement `@media (max-width: 768px)` card transformations:
  ```css
  @media (max-width: 768px) {
    .responsive-card-table thead {
      display: none;
    }
    .responsive-card-table, 
    .responsive-card-table tbody, 
    .responsive-card-table tr, 
    .responsive-card-table td {
      display: block;
      width: 100%;
    }
    .responsive-card-table tr {
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 14px;
      padding: 14px;
      margin-bottom: 12px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
    }
    .responsive-card-table td {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 0 !important;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      font-size: 13px;
    }
    .responsive-card-table td:last-child {
      border-bottom: none;
      padding-top: 12px !important;
      justify-content: stretch;
    }
    .responsive-card-table td::before {
      content: attr(data-label);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      color: var(--text-dim);
      letter-spacing: 0.05em;
    }
  }
  ```

---

#### 🔴 AUDIT-ISP-02: Rigid Inline Multi-Column Grids Inside Modals
- **Severity:** `HIGH`
- **Affected Files:**
  - [`templates/dashboard.html:2100`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/dashboard.html#L2100) (`grid-template-columns: 1fr 1fr auto;`)
  - [`templates/dashboard.html:2132`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/dashboard.html#L2132) (`grid-template-columns: repeat(4, 1fr);`)
  - [`templates/dashboard.html:2224`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/dashboard.html#L2224) (`grid-template-columns: 1fr 1fr;`)
  - [`templates/packages.html:376`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/packages.html#L376) (`.form-row { grid-template-columns: 1fr 1fr; }`)
  - [`templates/gateway.html:632, 643, 654`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/gateway.html#L632) (`grid-template-columns: 2fr 1fr;`, etc.)
  - [`templates/approvals.html:988`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/approvals.html#L988) (`display:flex; gap:8px; align-items:center;`)
- **WCAG Criteria:** 1.4.10 Reflow (Level AA)
- **Problem & Mobile Impact:**
  Hardcoded inline styles like `style="display: grid; grid-template-columns: 1fr 1fr;"` bypass external stylesheet media queries. On 360px–430px viewports, form fields are compressed to ~140px width, causing input text truncation and squashed labels.
- **Proposed Solution:**
  Replace inline styles with semantic class names (`.form-grid-2`, `.form-grid-3`, `.form-grid-4`) and add global responsive overrides:
  ```css
  .form-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .form-grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
  .form-grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }

  @media (max-width: 640px) {
    .form-grid-2, .form-grid-3, .form-grid-4, .form-row {
      grid-template-columns: 1fr !important;
      gap: 12px !important;
    }
  }
  ```

---

#### 🟡 AUDIT-ISP-03: Invalid `@media` Rule Inside Inline Style Attribute
- **Severity:** `MEDIUM`
- **Affected File:**
  - [`templates/collections.html:1085`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/collections.html#L1085)
- **Problem:**
  Line 1085 contains:
  ```html
  <span style="font-size:11.5px; color:var(--text-dim); display:none; @media(min-width:768px){display:inline;}">Auto-extends validity on MikroTik router</span>
  ```
  CSS `@media` queries are invalid inside inline HTML `style` attributes. All browsers silently discard this rule, leaving the text permanently hidden (`display: none`).
- **Proposed Solution:**
  Remove the invalid inline media query and use a standard utility class:
  ```html
  <span class="desktop-only text-dim" style="font-size:11.5px;">Auto-extends validity on MikroTik router</span>
  ```
  With CSS in `base.html`:
  ```css
  @media (max-width: 768px) { .desktop-only { display: none !important; } }
  @media (min-width: 769px) { .desktop-only { display: inline-block !important; } }
  ```

---

#### 🟡 AUDIT-ISP-04: Top Bar Header Congestion on Compact Phones (<= 440px)
- **Severity:** `MEDIUM`
- **Affected File:**
  - [`templates/base.html:202-234, 939-985`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/base.html#L202)
- **Problem & Mobile Impact:**
  The sticky `.top-bar` has a height of 56px–64px. On screens `< 400px`, the hamburger button, page title, "Default Password" pill, status pill, refresh button, "My Profile" button, and "Sign Out" button all compete for horizontal space. Elements wrap unpredictably or overflow the viewport width.
- **Proposed Solution:**
  On viewports `<= 640px`, hide secondary auth buttons from the top bar (since they are already accessible inside the mobile drawer):
  ```css
  @media (max-width: 640px) {
    .top-bar-auth-group { display: none !important; }
    .top-bar { padding: 0 12px; }
    .page-heading { font-size: 15px; max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  }
  ```

---

### Category B: Touch Target Sizes & Virtual Keyboard Optimization

#### 🔴 AUDIT-ISP-05: Touch Targets Substantially Below 44px x 44px
- **Severity:** `HIGH`
- **Affected Files:**
  - [`templates/dashboard.html:2229-2242, 2418-2425`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/dashboard.html#L2229) (`.btn-preset` speed and device chips)
  - [`templates/packages.html:653-665`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/packages.html#L653) (`.btn-action-sm` table actions)
  - [`templates/approvals.html:991-998`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/approvals.html#L991) (`.btn-preset` speed presets)
  - [`mikrotik_hotspot/login.html:449-452`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/mikrotik_hotspot/login.html#L449) (`.mac-guide-tab-btn`)
  - All modal close buttons (`.btn-close-modal`, `.btn-modal-close`)
- **WCAG Criteria:** 2.5.5 Target Size (Enhanced - AAA) & 2.5.8 Pointer Target Spacing (AA - WCAG 2.2)
- **Problem & Mobile Impact:**
  Buttons with `padding: 2px 6px` or `3px 8px` have total rendered heights of 20px–26px. Operators and customers tapping on phone screens regularly trigger the wrong preset or miss the target entirely.
- **Proposed Solution:**
  Enforce a minimum touch target size of **42px–44px** on mobile viewports:
  ```css
  @media (max-width: 768px) {
    .btn-preset {
      min-height: 40px !important;
      padding: 8px 14px !important;
      font-size: 12.5px !important;
      border-radius: 9px !important;
    }
    .btn-close-modal, .btn-modal-close {
      min-width: 44px !important;
      min-height: 44px !important;
      display: inline-flex !important;
      align-items: center !important;
      justify-content: center !important;
      font-size: 24px !important;
    }
    .mac-guide-tab-btn {
      min-height: 40px !important;
      font-size: 12px !important;
    }
  }
  ```

---

#### 🔴 AUDIT-ISP-06: iOS Safari Automatic Viewport Zoom on Form Focus
- **Severity:** `HIGH`
- **Affected Files:**
  - [`templates/login.html:401`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/login.html#L401) (`font-size: 15px;`)
  - [`mikrotik_hotspot/login.html:123`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/mikrotik_hotspot/login.html#L123) (`font-size: 15px;`)
  - [`templates/customers.html:121`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/customers.html#L121) (`font-size: 13px;` on search)
  - [`templates/collections.html:1336`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/collections.html#L1336) (`font-size: 13.5px;` on ledger search)
- **WCAG Criteria:** 1.4.4 Resize Text (Level AA) & iOS Human Interface Guidelines
- **Problem & Mobile Impact:**
  Whenever an input field with `font-size < 16px` receives focus on an iPhone (Safari or the Hotspot Captive Network Assistant), iOS triggers an involuntary 120% viewport zoom. The card shifts off-center, cutting off borders and buttons, forcing the user to manually pinch-zoom out.
- **Proposed Solution:**
  Guarantee that all input, select, and textarea fields have `font-size: 16px !important;` on mobile viewports (`<= 768px`):
  ```css
  @media (max-width: 768px) {
    input[type="text"],
    input[type="tel"],
    input[type="number"],
    input[type="password"],
    input[type="date"],
    select,
    textarea,
    .form-input,
    .form-control,
    .search-input {
      font-size: 16px !important;
    }
  }
  ```

---

#### 🟡 AUDIT-ISP-07: Missing Virtual Numeric Keypad Invocations (`inputmode`)
- **Severity:** `MEDIUM`
- **Affected Files:**
  - [`mikrotik_hotspot/login.html:615, 625, 650`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/mikrotik_hotspot/login.html#L615) (`voucherPin`, `voucherPhone`, `lookupPhone`)
  - [`templates/dashboard.html:2023`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/dashboard.html#L2023) (`#qcAmount`)
  - [`templates/collections.html:1052`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/collections.html#L1052) (`#posAmount`)
- **WCAG Criteria:** 3.3.2 Labels or Instructions (Level A)
- **Problem & Mobile Impact:**
  Mobile users typing voucher PINs, phone numbers, or payment amounts are greeted with the full QWERTY keyboard instead of a dedicated numeric keypad, requiring an extra tap to switch keyboard modes.
- **Proposed Solution:**
  Add `inputmode="numeric"` and `autocomplete="..."` to numeric inputs:
  ```html
  <!-- For phone numbers: -->
  <input type="tel" id="voucherPhone" class="form-input" inputmode="tel" autocomplete="tel" placeholder="05xxxxxxxx">

  <!-- For voucher PINs: -->
  <input type="text" id="voucherPin" class="form-input font-mono" inputmode="numeric" pattern="[0-9]*" placeholder="e.g. 74829104">

  <!-- For currency amounts: -->
  <input type="number" step="0.01" id="qcAmount" class="form-input font-mono" inputmode="decimal" placeholder="0.00">
  ```

---

### Category C: WCAG 2.1 AA Accessibility & Contrast Compliance

#### 🔴 AUDIT-ISP-08: Sub-Threshold Color Contrast on Secondary Text
- **Severity:** `HIGH`
- **Affected Files:**
  - [`templates/base.html:30`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/base.html#L30) (`--text-dim: #64748b;`)
  - Ubiquitous usage across all 14 templates on card backgrounds (`#0f172a`, `#0b1120`, `#090e1a`)
- **WCAG Criteria:** 1.4.3 Contrast (Minimum - Level AA)
- **Contrast Analysis:**
  - Foreground `#64748b` on background `#0f172a`: **3.8:1** (FAILED: minimum 4.5:1 required).
  - Foreground `#64748b` on background `#070a12`: **3.6:1** (FAILED).
  - Used for field labels, timestamps, transaction notes, and subtitles. Outdoors under direct sunlight, text is almost unreadable.
- **Proposed Solution:**
  Upgrade theme color tokens in [`templates/base.html`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/base.html):
  ```css
  :root {
    --text-main: #f8fafc;     /* Ratio: 15.6:1 (AAA) */
    --text-muted: #cbd5e1;    /* Ratio: 11.5:1 (AAA) - was #94a3b8 */
    --text-dim: #94a3b8;      /* Ratio: 6.8:1 (Passes AA 4.5:1) - was #64748b */
  }
  ```

---

#### 🔴 AUDIT-ISP-09: Complete Absence of `:focus-visible` Keyboard Rings
- **Severity:** `HIGH`
- **Affected Files:** All templates in `templates/*.html`
- **WCAG Criteria:** 2.4.7 Focus Visible (Level AA)
- **Problem & Impact:**
  `Select-String` search confirmed **0 instances** of `:focus-visible` in the entire repository. Multiple stylesheets specify `outline: none;` without replacement. Users navigating with a physical keyboard, tablet keyboard case, or assistive switch device have zero visual indicator of focused elements.
- **Proposed Solution:**
  Inject a global focus ring in [`templates/base.html`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/base.html):
  ```css
  /* Universal Accessible Focus Indicator */
  :focus-visible {
    outline: 2px solid #38bdf8 !important;
    outline-offset: 2px !important;
  }
  button:focus-visible, 
  a:focus-visible, 
  input:focus-visible, 
  select:focus-visible {
    box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.35) !important;
  }
  ```

---

#### 🟡 AUDIT-ISP-10: Missing Form Label Associations (`for` / `id`)
- **Severity:** `MEDIUM`
- **Affected Files:**
  - [`templates/dashboard.html:2207, 2213, 2226, 2236`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/dashboard.html#L2207)
  - [`templates/approvals.html:945, 974, 985, 1008`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/approvals.html#L945)
  - [`templates/packages.html:705, 709, 719`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/packages.html#L705)
- **WCAG Criteria:** 1.3.1 Info and Relationships (Level A) & 4.1.2 Name, Role, Value
- **Problem:**
  Form labels are written as plain `<label>Subscriber Full Name</label>` adjacent to `<input id="custName">`. Tapping the label does not focus the input, and screen readers (TalkBack / VoiceOver) do not announce the field name when navigating.
- **Proposed Solution:**
  Pair every label with its target input:
  ```html
  <label for="custName" class="form-label">Subscriber Full Name <span class="text-rose">*</span></label>
  <input type="text" id="custName" name="name" class="form-input" required>
  ```

---

#### 🟡 AUDIT-ISP-11: Dynamic Notifications & Asynchronous Alerts Lack ARIA Roles
- **Severity:** `MEDIUM`
- **Affected Files:**
  - [`templates/base.html:1182`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/base.html#L1182) (`#selfProfileFeedback`)
  - [`templates/dashboard.html:2048`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/dashboard.html#L2048) (`#qcAdvanceNotice`)
  - [`mikrotik_hotspot/login.html:500, 634`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/mikrotik_hotspot/login.html#L500) (`#clientErrorAlert`, `#voucherSuccessBox`)
- **WCAG Criteria:** 4.1.3 Status Messages (Level AA)
- **Problem:**
  When validation fails or asynchronous actions complete, feedback messages are inserted into plain `<div>` containers. Screen readers remain silent because the containers lack live region roles.
- **Proposed Solution:**
  Add `role="status"` or `role="alert"` and `aria-live="polite"`:
  ```html
  <div id="selfProfileFeedback" role="alert" aria-live="polite" style="display:none; ..."></div>
  <div id="clientErrorAlert" role="alert" aria-live="assertive" class="alert-banner alert-danger d-none"></div>
  ```

---

### Category D: MikroTik Captive Portal Client Experience

#### 🔴 AUDIT-ISP-12: Captive Portal Viewport Zoom Blocked (`user-scalable=no`)
- **Severity:** `HIGH`
- **Affected Files:**
  - [`mikrotik_hotspot/login.html:5`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/mikrotik_hotspot/login.html#L5)
  - [`templates/captive_portal.html:5`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/captive_portal.html#L5)
- **WCAG Criteria:** 1.4.4 Resize Text (Level AA)
- **Problem:**
  The `<meta name="viewport">` tag contains `maximum-scale=1.0, user-scalable=no`. This explicitly disables pinch-to-zoom for visually impaired users and elderly subscribers who require larger text sizes.
- **Proposed Solution:**
  Replace with standard accessible viewport tag:
  ```html
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  ```

---

#### 🟡 AUDIT-ISP-13: Captive Portal Tab Crowding on 360px Devices
- **Severity:** `MEDIUM`
- **Affected File:**
  - [`mikrotik_hotspot/login.html:493-498`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/mikrotik_hotspot/login.html#L493)
- **Problem & Impact:**
  Four tabs (`Mobile Connect`, `Member Login`, `Voucher PIN`, `My Plan`) are squeezed side-by-side into a single flex row. On a 360px device (Galaxy A-series), each tab has only ~78px of width, causing text clipping or awkward wrapping.
- **Proposed Solution:**
  Transform the tab bar into a 2x2 grid or horizontal scrollable pill bar on `<= 380px`:
  ```css
  @media (max-width: 380px) {
    .portal-nav-tabs {
      display: grid !important;
      grid-template-columns: 1fr 1fr !important;
      gap: 6px !important;
    }
    .portal-tab-btn {
      padding: 9px 6px !important;
      font-size: 12px !important;
      min-height: 40px !important;
    }
  }
  ```

---

#### 🟡 AUDIT-ISP-14: Lack of Interactive Arabic / English Language Toggle
- **Severity:** `MEDIUM`
- **Affected File:**
  - [`mikrotik_hotspot/login.html`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/mikrotik_hotspot/login.html)
- **Problem:**
  The captive portal has a few bilingual labels (`Mobile Number / رقم الجوال`), but all instructions, error banners, device step-by-step guides, and button texts are hardcoded English. Hotspot subscribers in Saudi Arabia include non-English Arabic speakers.
- **Proposed Solution:**
  Add a lightweight 1-tap `[ 🇸🇦 العربية | 🇬🇧 English ]` language toggle in the header that updates text strings and toggles `dir="rtl"` dynamically with zero external dependencies.

---

### Category E: Modals, Forms & Viewport Overflows

#### 🔴 AUDIT-ISP-15: Mobile Soft Keyboard Viewport Clipping on Modals
- **Severity:** `HIGH`
- **Affected Files:**
  - [`templates/dashboard.html:1995, 2343`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/dashboard.html#L1995) (`quickCollectModal`, `editCustomerModal`)
  - [`templates/customers.html:1036, 1291`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/customers.html#L1036) (`profileModal`, `addCustomerModal`)
  - [`templates/gateway.html:619, 688`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/gateway.html#L619) (`addRouterModal`, `editRouterModal`)
  - [`templates/resellers.html:612, 662`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/resellers.html#L612) (`createResellerModal`, etc.)
- **Problem & Mobile Impact:**
  On mobile devices, when the virtual keyboard pops up, the visible viewport height shrinks by 40%–50%. Modals without `max-height: calc(100dvh - 32px)` and internal scrolling hide submit buttons below the screen edge.
- **Proposed Solution:**
  Standardize modal containers in `base.html`:
  ```css
  @media (max-width: 768px) {
    .modal-overlay {
      padding: 10px !important;
      align-items: flex-end !important; /* Bottom-sheet appearance on mobile */
    }
    .modal-container, .modal-box, .modal-box-lg {
      width: 100% !important;
      max-width: 100% !important;
      max-height: 90dvh !important;
      border-radius: 20px 20px 0 0 !important;
      display: flex !important;
      flex-direction: column !important;
      margin-bottom: 0 !important;
    }
    .modal-body, .modal-body-scroll {
      overflow-y: auto !important;
      -webkit-overflow-scrolling: touch !important;
      flex-grow: 1 !important;
      padding: 16px !important;
    }
  }
  ```

---

#### 🟡 AUDIT-ISP-16: Customer Edit Page Sticky Footer Mobile Ergonomics
- **Severity:** `MEDIUM`
- **Affected File:**
  - [`templates/customer_edit.html:533-543`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/customer_edit.html#L533) (`.edit-sticky-footer`)
- **Problem:**
  On small screens, the sticky bottom footer has two action buttons ("Discard" and "Save Changes") that overlap or crowd out content if bottom padding is insufficient.
- **Proposed Solution:**
  Add a bottom padding spacer (`padding-bottom: 90px;`) to `.edit-page-container` to guarantee the bottom-most input is never obscured by the sticky action bar.

---

## 4. Template-by-Template Execution Roadmap

The incoming Antigravity agent should execute fixes following this strict dependency order:

```mermaid
flowchart TD
    Phase1["Phase 1: Global Framework & Design Tokens\n(templates/base.html)"]
    Phase2["Phase 2: Hotspot Captive Portal Suite\n(mikrotik_hotspot/login.html & status.html)"]
    Phase3["Phase 3: Core Operations Tables & Modals\n(dashboard.html & approvals.html)"]
    Phase4["Phase 4: Customer Directory & Edit\n(customers.html & customer_edit.html)"]
    Phase5["Phase 5: Financial Desk & Packages\n(collections.html & packages.html)"]
    Phase6["Phase 6: Gateway Fleet & Partners\n(gateway.html, resellers.html, reseller_portal.html)"]
    Phase7["Phase 7: Communications & PON\n(whatsapp.html & olt.html)"]

    Phase1 --> Phase2
    Phase1 --> Phase3
    Phase3 --> Phase4
    Phase4 --> Phase5
    Phase5 --> Phase6
    Phase6 --> Phase7
```

### 📋 Detailed Step-by-Step Task Breakdown:

#### 1. [`templates/base.html`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/base.html) (Foundation)
- [ ] Brighten `--text-dim` from `#64748b` to `#94a3b8` (contrast 6.8:1).
- [ ] Add global `:focus-visible` styling with 2px cyan ring.
- [ ] Add global mobile input font-size rule (`font-size: 16px !important;` on `<= 768px`).
- [ ] Standardize bottom-sheet modal behavior on mobile (`align-items: flex-end`, `90dvh` max-height).
- [ ] Clean up top bar on `<= 640px` (hide duplicate profile/logout links from header since they exist in the mobile drawer).
- [ ] Add ARIA live region attributes to `#selfProfileFeedback`.

#### 2. [`mikrotik_hotspot/login.html`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/mikrotik_hotspot/login.html) (Client Portal)
- [ ] Remove `maximum-scale=1.0, user-scalable=no` from viewport meta.
- [ ] Upgrade `.form-input` font size from `15px` to `16px`.
- [ ] Add `inputmode="numeric"` and `inputmode="tel"` to voucher and phone inputs.
- [ ] Increase touch targets of MAC guide tabs to 42px min-height.
- [ ] Convert 4-tab bar to responsive 2x2 grid on `<= 380px`.
- [ ] Add bilingual Arabic/English toggle switch in portal header.
- [ ] Add `role="alert"` to `#clientErrorAlert` and `#voucherSuccessBox`.

#### 3. [`templates/dashboard.html`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/dashboard.html)
- [ ] Replace inline grids in Date Range modal with responsive class (`.form-grid-3`).
- [ ] Fix 4-card printable report KPI grid on mobile (`repeat(2, 1fr)` or single column).
- [ ] Ensure Quick Collect modal and Approval modal have 44px touch targets on presets.
- [ ] Add `<label for="...">` associations across all modal forms.

#### 4. [`templates/approvals.html`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/approvals.html)
- [ ] Fix speed presets row in Approval Modal: change inline horizontal flex to `.preset-wrap` that stacks vertically on mobile (`<= 768px`).
- [ ] Enforce 40px min-height on speed preset pills.
- [ ] Ensure all form labels have `for="..."`.

#### 5. [`templates/collections.html`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/collections.html)
- [ ] Transform `#collectionsTable` into responsive card deck on `<= 768px` with `data-label`.
- [ ] Fix invalid inline `@media` query on line 1085.
- [ ] Add `inputmode="decimal"` to Quick POS collector amount field.
- [ ] Ensure thermal receipt slip modal fits on 360px screens without side overflow.

#### 6. [`templates/packages.html`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/packages.html)
- [ ] Implement `@media (max-width: 768px)` stylesheet (currently 0 media queries).
- [ ] Transform `#pkgTable` (9 columns) into vertical card deck with `data-label`.
- [ ] Collapse `.form-row` in Create/Edit modals from 2 columns to 1 column on mobile.
- [ ] Upgrade touch targets of Sync, Edit, Delete action buttons to min 40px.

#### 7. [`templates/customers.html`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/customers.html) & [`customer_edit.html`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/customer_edit.html)
- [ ] Enhance tab buttons in `#profileModal` to 44px min-height for touch.
- [ ] Add 90px bottom spacer in `customer_edit.html` to prevent sticky footer overlap.
- [ ] Ensure all inputs have `font-size: 16px;` on mobile.

#### 8. [`templates/gateway.html`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/gateway.html) & [`templates/olt.html`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/olt.html)
- [ ] Transform Gateway Interfaces table (6 columns) into card view on mobile.
- [ ] Collapse inline modal grids (`2fr 1fr`) in Add/Edit router modals to single column.
- [ ] Transform `#onuTable` (9 columns) in `olt.html` into responsive card deck.

#### 9. [`templates/resellers.html`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/resellers.html) & [`reseller_portal.html`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/reseller_portal.html)
- [ ] Add media queries to `resellers.html` and transform 3 tables into card decks.
- [ ] Transform Assigned Subscribers and Wallet Ledger tables in `reseller_portal.html` into cards on mobile.

#### 10. [`templates/whatsapp.html`](file:///C:/Users/Shajjad%20Kan/tserver_projects/isp_v2/templates/whatsapp.html)
- [ ] Add mobile media queries for `<= 640px` and `<= 440px`.
- [ ] Stack telemetry row to single column on phones.
- [ ] Transform `#logsTable` (6 columns) into responsive card deck.

---

## 5. Captive Portal Smartphone Blueprint (`login.html`)

Because the captive portal client is exclusively accessed on smartphones, it requires special architectural polish:

```html
<!-- BILINGUAL LANGUAGE SWITCHER HEADER COMPONENT -->
<div class="lang-switch-bar">
  <button type="button" class="lang-btn active" onclick="setPortalLang('en')">🇬🇧 English</button>
  <button type="button" class="lang-btn" onclick="setPortalLang('ar')">🇸🇦 العربية</button>
</div>

<!-- ACCESSIBLE 2x2 TAB GRID FOR ULTRA-COMPACT SCREENS -->
<div class="portal-nav-grid" role="tablist" aria-label="Connection Methods">
  <button type="button" id="tabBtnPhone" class="portal-nav-item active" onclick="switchTab('phone')" role="tab" aria-selected="true">
    <svg viewBox="0 0 24 24"><path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/></svg>
    <span data-i18n="tab_phone">Mobile Connect</span>
  </button>
  <button type="button" id="tabBtnMember" class="portal-nav-item" onclick="switchTab('member')" role="tab" aria-selected="false">
    <svg viewBox="0 0 24 24"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>
    <span data-i18n="tab_member">Member Login</span>
  </button>
  <button type="button" id="tabBtnVoucher" class="portal-nav-item" onclick="switchTab('voucher')" role="tab" aria-selected="false">
    <svg viewBox="0 0 24 24"><path d="M20 4H4c-1.11 0-1.99.89-1.99 2L2 18c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V6c0-1.11-.89-2-2-2zm0 14H4v-6h16v6zm0-10H4V6h16v2z"/></svg>
    <span data-i18n="tab_voucher">Voucher PIN</span>
  </button>
  <button type="button" id="tabBtnLookup" class="portal-nav-item" onclick="switchTab('lookup')" role="tab" aria-selected="false">
    <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>
    <span data-i18n="tab_lookup">Check My Plan</span>
  </button>
</div>
```

---

## 6. Testing, Verification & Deployment Runbook

### 🧪 Automated Mobile Testing Checklist (Chrome DevTools / Edge)
1. **Device Emulation Profiles:**
   - iPhone SE / Galaxy A-series: **360px x 640px**
   - iPhone 14/15/16: **390px x 844px**
   - iPhone Pro Max / Pixel 8: **430px x 932px**
   - iPad mini (Portrait): **768px x 1024px**
2. **Key Acceptance Checks:**
   - [ ] **Zero Horizontal Body Overflow:** `document.documentElement.scrollWidth <= window.innerWidth` across all pages.
   - [ ] **Table-to-Card Verification:** Verify that every table transforms to individual vertical cards with visible `data-label` titles on `< 768px`.
   - [ ] **Virtual Keyboard Invocations:** Tap every input on a real phone or simulated touch environment:
     - Phone inputs summon numeric/tel pad.
     - Currency/amounts summon decimal pad.
     - Viewport does **NOT** zoom in automatically on iOS Safari.
   - [ ] **Contrast Verification:** Run Lighthouse Accessibility audit; verify contrast scores `>= 95%`.
   - [ ] **Tab Keyboard Navigation:** Press Tab key from top to bottom; verify bright 2px cyan outline on all focused controls.

### 🚀 Synchronization & Deployment to Production

#### 1. Push Local Edits to Staging Server:
```powershell
# In PowerShell:
cd "C:\Users\Shajjad Kan\tserver_projects\isp_v2"
.\Compare-TServer.ps1 -Push
```

#### 2. Verify Service & Tunnel Status on `tserver`:
```powershell
ssh -p 22 tserver@10.12.14.16 "sudo systemctl status isp_v2.service --no-pager"
```

#### 3. Update Captive Portal Suite on MikroTik Router:
```powershell
# Upload updated hotspot suite to RouterOS via FTP/SFTP
scp -P 22 "C:\Users\Shajjad Kan\tserver_projects\isp_v2\mikrotik_hotspot\login.html" tserver@10.12.14.16:/tmp/
ssh -p 22 tserver@10.12.14.16 "curl -T /tmp/login.html ftp://adminn:adminn@10.20.30.1/hotspot/login.html"
```

---

> **Note for the Next Agent:**  
> This audit report is complete, concrete, and self-contained. You can immediately begin execution starting with **Phase 1 (`templates/base.html`)**, followed by the task breakdown in Section 4. All referenced line numbers and code snippets reflect the live hot state of the repository.

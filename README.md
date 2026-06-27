# Songa Mobility Phase 2

Frappe app for **Songa Mobility** — the ERPNext integration layer between the Songa platform and back-office operations. It manages **driver wallets** (commission, rental days, energy kWh), **M-Pesa STK push recharges**, **commission ledger approvals**, and **asset maintenance**, with REST APIs for the Songa platform and native Frappe reports/dashboards for operations and finance.

**Module:** `Songa App Integration`  
**Publisher:** Teamweb Limited · **License:** MIT

---

## What this app does

Songa Mobility leases electric trikes and related equipment to drivers. Drivers earn commission, spend it on rental days and battery energy (kWh), or top up wallets via M-Pesa. This app:

- Tracks three wallet balances per driver and posts commission movements to the GL
- Exposes whitelisted REST endpoints consumed by the Songa platform
- Runs approval workflows for commission allocations/deductions and asset repairs
- Sends webhooks back to Songa when commission ledger states change
- Provides operations dashboards and script reports for wallet health and fleet maintenance

Balance logic is centralised in `report_helpers.py` and reused by reports, desk UI, and API responses so numbers stay consistent everywhere.

---

## Dependencies

Install on a Frappe v15 bench with at least:

| App | Purpose |
|-----|---------|
| **ERPNext** | Driver, Supplier, Asset, Asset Repair, accounting documents |
| **HRMS** (or ERPNext Driver) | `Driver` doctype |
| **frappe_mpsa_payments** (or equivalent) | `Mpesa Express Request` for STK push |

---

## Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app songa_mobility_phase_2
bench migrate
```

After install, open **Songa Customization Settings** (from the workspace) and configure:

- Driver Commission Account
- STK Push payment gateway
- Songa Webhook Endpoint
- Asset repair stock expense accounts (lease-to-own, internal consumption)

---

## Workspace
<img width="2424" height="1680" alt="image" src="https://github.com/user-attachments/assets/b45c153c-bdd5-496f-add3-9c98d5d02dbf" />

**Songa App Integration** is the main entry point in Desk.

| Area | Contents |
|------|----------|
| **Shortcuts** | Driver · Driver Wallet Dashboard · Asset Maintenance Dashboard · STK Push · Songa Customization Settings |
| **Driver Wallet card** | Driver · Driver Commission Ledger · Rental Days · Energy KWh |
| **Asset Repair card** | Asset · Asset Type · Severity Type |
| **Settings card** | Songa Customization Settings |
| **Reports card** | All six script reports (see below) |

---

## DocTypes

### App DocTypes (`songa_app_integration/doctype/`)

| DocType | Essence |
|---------|---------|
| **Driver Commission Ledger** | Submittable ledger for commission **Allocation** (credit to driver supplier) and **Deduction** (debit for rental/kWh recharge). On approval, posts a Journal Entry. Workflow: Pending → Approved / Rejected / Cancelled. |
| **Rental Days** | Submittable wallet for trike rental days. **Recharge** (via commission or M-Pesa) adds days; **Usage** consumes them. Links to Driver Commission Ledger or Mpesa Express Request. |
| **Energy KWh** | Submittable wallet for battery energy. Same recharge/usage pattern as Rental Days, quantity in kWh. |
| **Songa Customization Settings** | Single settings record: commission GL account, M-Pesa gateway, webhook URL, asset-repair stock expense accounts. |
| **Asset Type** | Master list of repairable asset categories (e.g. TRIKE, BATTERY). Referenced from Asset Repair. |
| **Severity Type** | Master list of fault severity levels (e.g. LOW, MEDIUM, SERIOUS, CRITICAL). Referenced from Asset Repair. |

### Standard DocTypes extended by this app

Custom fields and client scripts are shipped via fixtures for:

- **Driver** — links driver to supplier/transporter for commission GL balance
- **Asset** / **Asset Repair** — Songa repair ID, asset/severity type, trike registration, workflow state
- **Asset Repair Consumed Item** — UOM fetch on stock lines
- **Payment Entry**, **Journal Entry**, **Purchase Invoice**, **Purchase Order**, **Sales Invoice**, **Stock Entry** — branch/cost-centre and accounting hooks

---

## Workflows

### Driver Commission Ledger

| State | Docstatus | Typical next actions |
|-------|-----------|----------------------|
| Pending | 0 | Approve · Reject |
| Approved | 1 | Cancel |
| Rejected | 0 | — |
| Cancelled | 2 | — |

**Roles:** Commission Ledger Approver, Songa App (cancel on approved).

On **Approved** or **Rejected**, a webhook is POSTed to the URL in Songa Customization Settings with driver ID, amount, updated balances, and ledger reference.

Auto-approval: commission-funded wallet recharges create a Deduction ledger entry and call `apply_workflow(..., "Approve")` immediately after the linked recharge is submitted.

### Asset Repair

Multi-step approval before work is authorised and completed:

```
Draft
  → Pending Approval - Technical Agent
    → Pending Approval - Lead Technician
      → Pending Approval HM
        → Approved → Completed
```

Any approval step can **Reject** or **Return for Amendment**. Hub Manager can **Cancel** from Completed.

**Roles:** Technical Agent · Lead Technician · Hub Manager · Stock User (Draft / To Amend)

Asset Repair also has ERPNext’s own `repair_status` (Pending / Completed / Cancelled), separate from `workflow_state`.

---

## Reports & dashboards

### Script reports

| Report | Purpose | Roles |
|--------|---------|-------|
| **Driver Wallet Summary** | Fleet-wide commission, rental days, and kWh balances | System Manager · Commission Ledger Approver · Songa App |
| **Driver Wallet Activity** | Unified transaction ledger across DCL, Rental Days, Energy KWh | ↑ |
| **Wallet Recharge Analytics** | Recharge volume, success rate, M-Pesa vs Commission by period (+ chart) | ↑ |
| **Songa STK Push Status** | M-Pesa Express Request scoped to wallet recharges | ↑ |
| **Commission Ledger Status** | Approval queue and commission movement by workflow state (+ chart) | ↑ |
| **Asset Repair Analytics** | Repairs by severity, asset type, cost, downtime, stock (+ cost trend chart) | System Manager · Technical Agent · Songa App |

### Dashboards

**Driver Wallet Dashboard**

| Widget | Type |
|--------|------|
| Active Drivers | Number card |
| Pending Commission Approvals | Number card |
| M-Pesa Recharges (This Month) | Number card |
| Failed STK Push (Last 7 Days) | Number card |
| Recharge Trend | Report chart (Wallet Recharge Analytics) |
| STK Push Outcomes | Donut (Group By) |
| Commission Ledger by Status | Donut (Group By) |

**Asset Maintenance Dashboard**

| Widget | Type |
|--------|------|
| Open Repairs | Number card |
| Completed Repairs (This Month) | Number card |
| Total Repair Cost (This Month) | Number card |
| Repairs with Stock Consumption | Number card |
| Repair Cost Trend | Report chart (Asset Repair Analytics) |
| Repairs by Severity | Donut (Group By) |
| Repairs by Asset Type | Donut (Group By) |

---

## API documentation

All Songa platform endpoints live under `songa_mobility_phase_2.songa_app_integration.api.api`. They require an authenticated Frappe session or API key (`allow_guest=False`).

**Base URL pattern:**

```
POST /api/method/songa_mobility_phase_2.songa_app_integration.api.api.<method>
Content-Type: application/json
```

Responses use `{ "status": "success" | "error" | "pending", "message": "...", ... }`. HTTP status codes are set on errors (400, 403, 404, 500).

### Driver wallet

#### `allocate_commission`

Create a commission allocation ledger entry (awaiting approval).

| Field | Required | Description |
|-------|----------|-------------|
| `driver_id` | Yes | Driver name/ID |
| `amount` | Yes | Positive number |
| `company` | No | Defaults to user default company |

#### `recharge_rental_days`

| Field | Required | Description |
|-------|----------|-------------|
| `driver_id` | Yes | |
| `amount` | Yes | Positive number |
| `no_of_days` | Yes | Positive integer |
| `payment_method` | Yes | `"commission"` or `"mpesa"` |
| `phone_number` | If mpesa | Kenyan mobile format |
| `company` | No | |

Commission path: validates balance, submits Rental Days, creates/auto-approves Deduction ledger.  
M-Pesa path: returns `"status": "pending"` with `mpesa_request` until STK push completes.

#### `recharge_kwh`

Same as rental days, but `kwh` (float) instead of `no_of_days`.

#### `consume_rental_days`

| Field | Required | Description |
|-------|----------|-------------|
| `driver_id` | Yes | |
| `no_of_days` | Yes | Must not exceed balance |
| `company` | No | |

#### `consume_kwh`

| Field | Required | Description |
|-------|----------|-------------|
| `driver_id` | Yes | |
| `kwh` | Yes | Must not exceed balance |
| `company` | No | |

#### `cancel_rental_days` / `cancel_energy_kwh`

| Field | Required | Description |
|-------|----------|-------------|
| `rental_day_id` / `energy_kwh_id` | Yes | Document name to cancel |

Cancels the wallet document and reverses linked commission ledger or M-Pesa request where applicable.

### Asset repair

#### `create_asset_repair`

| Field | Required | Description |
|-------|----------|-------------|
| `asset_repair_id` | Yes | External Songa ID (stored as `custom_asset_repair_id`) |
| `asset_id` | Yes | ERPNext Asset name |
| `asset_type_id` | Yes | Asset Type link |
| `severity_type_id` | Yes | Severity Type link |
| `failure_date` | Yes | ISO datetime |
| `description` | Yes | Error description |
| `user_email` | Yes | Frappe User (creator context) |
| `company` | No | |

Submits into workflow at **Pending Approval - Technical Agent**. Idempotent on duplicate `asset_repair_id`.

#### `check_asset_repair_status`

| Field | Required |
|-------|----------|
| `asset_repair_id` | Yes |

Returns repair details, workflow state, costs, and stock items if consumed.

#### `comment_on_asset_repair`

| Field | Required |
|-------|----------|
| `asset_repair_id` | Yes |
| `comment` | Yes |
| `user_email` | Yes |

#### `update_asset_repair`

| Field | Required | Description |
|-------|----------|-------------|
| `asset_repair_id` | Yes | |
| `updated_values` | Yes | Object with any of: `severity_type_id`, `asset_type_id`, `description`, `failure_date` |
| `user_email` | Yes | |

### Internal / desk utility methods

These are also whitelisted under `songa_mobility_phase_2.songa_app_integration.utils.utils` for desk buttons and integrations:

| Method | Description |
|--------|-------------|
| `get_commission_balance_by_driver` | GL commission balance via driver’s supplier |
| `get_rental_days_balance_by_driver` | Completed recharges minus usage |
| `get_energy_kwh_balance_by_driver` | Completed recharges minus usage |
| `get_overall_balance` | All three balances in one call |
| `allocate_commission` | Post approved allocation (Journal Entry) |
| `deduct_commission` | Post approved deduction |
| `process_mpesa_express_request` | Complete wallet recharge after STK success |
| `get_linked_supplier` | Supplier for a customer |
| `get_branch_and_cost_center_by_supplier` | Accounting dimensions for supplier |

---

## Background jobs

| Schedule | Task |
|----------|------|
| Every minute (`cron`) | `process_pending_mpesa_express_requests` — polls in-progress M-Pesa requests linked to Rental Days / Energy KWh and completes wallet recharges on payment success |

---

## Document events (hooks)

| DocType | Event | Handler |
|---------|-------|---------|
| Driver Commission Ledger | `on_update` | Workflow webhook + auto GL on approval |
| Driver | `after_insert` | Supplier / transporter setup |
| Asset Repair | `validate`, `on_update` | Validation + Songa sync on state change |
| Comment | `on_update` | Asset repair comment notifications |
| Payment Entry | `on_submit` | Commission allocation from payments |
| Journal Entry | `on_submit` | Linked ledger validation |
| Purchase Invoice / Stock Entry | `validate` | Branch and cost-centre rules |

Client-side scripts in `public/js/` extend Driver, Payment Entry, Sales/Purchase documents, Stock Entry, and Journal Entry forms.

---

## Roles shipped via fixtures

| Role | Typical use |
|------|-------------|
| **Songa App** | API / integration user |
| **Commission Ledger Approver** | Approve or reject commission ledger entries |

Asset Repair workflow additionally uses **Technical Agent**, **Lead Technician**, **Hub Manager**, and **Stock User** (standard ERPNext roles).

---

## Project layout

```
songa_mobility_phase_2/
├── songa_mobility_phase_2/
│   ├── hooks.py                          # doc_events, scheduler, fixtures, app_include_js
│   ├── fixtures/                         # workflows, custom fields, roles, masters
│   ├── public/js/                        # desk form scripts
│   ├── services/workflow_handlers/       # commission ledger webhook handler
│   └── songa_app_integration/
│       ├── api/api.py                    # Songa platform REST API
│       ├── doctype/                      # app DocTypes
│       ├── events/events.py              # document event handlers
│       ├── report/                       # six script reports
│       ├── report_helpers.py             # shared wallet balance logic
│       ├── number_card/                  # dashboard number cards
│       ├── dashboard_chart/              # dashboard charts
│       ├── songa_app_integration_dashboard/
│       ├── utils/utils.py                # GL posting + balance helpers
│       └── workspace/songa_app_integration/
└── README.md
```

---

## Contributing

This app uses [pre-commit](https://pre-commit.com/) for formatting and linting (Ruff, tab indent, 110 char line length):

```bash
cd apps/songa_mobility_phase_2
pre-commit install
```

---

## License

MIT

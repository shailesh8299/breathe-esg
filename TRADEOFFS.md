# TRADEOFFS.md — Breathe ESG Ingestion Platform
### By: Shailesh Mishra | VIT Vellore

---

## Overview

This document covers three things I deliberately chose not to build in the four days available. These are not accidental gaps — they are scope decisions I made consciously after thinking about what would take the most time vs. deliver the least value for a prototype. I've been honest about what the real production consequences would be.

---

## Tradeoff 1 — Real Concur / Navan OAuth2 API Integration

### What it is
A real corporate travel integration would connect directly to Concur (or Navan/TripActions) using OAuth2. Instead of an analyst manually exporting a CSV and uploading it, the platform would authenticate with the travel system, call the Expense Reports or Trip API on a schedule (say, nightly), and pull new travel data automatically. The Concur API returns JSON with trip details, expense amounts, traveler IDs, and flight segment data. This would eliminate the manual upload step entirely.

### Why I skipped it
Setting up Concur OAuth2 requires registering an app in the Concur App Center, getting a client_id and client_secret from SAP Concur's developer portal, implementing the authorization code flow with token refresh, and handling the specific quirks of Concur's API versioning (v3 and v4 APIs coexist with different schemas for the same data). I estimated this would take at least 1.5 days on its own — roughly a third of my entire build time — for something that is purely transport-layer plumbing with no emissions logic in it. I made the call that getting all three ingestion parsers, the normalization logic, the audit workflow, and the React dashboard working was more valuable than automating one of the three upload flows.

### What the real consequence would be in production
Analysts have to manually export the Concur travel report CSV at the end of every reporting period (monthly or quarterly), remember to set the correct date range, and upload it to the platform. This introduces human error — wrong date ranges, missing expense categories, forgot to include one department. It also means there's always a lag between a trip happening and the data appearing in the emissions platform. For a company trying to do real-time carbon monitoring, this is a meaningful gap.

### What I'd build next if given another week
I'd implement the full Concur OAuth2 flow: redirect to Concur for authorization, exchange code for tokens, store encrypted refresh tokens per tenant, and set up a Celery periodic task to call `GET /api/v4/travelprofile/trips` every 24 hours. The ingestion pipeline already exists — the only new part would be replacing the file upload with an API call that feeds data into the same TravelParser class I already wrote.

---

## Tradeoff 2 — Automated Emission Factor Lookup via External API (Climatiq / Ecoinvent)

### What it is
Right now, all emission factors are hardcoded in `ingestion/constants.py`. For example, Diesel is hardcoded at 2.68 kgCO2e per litre, the Maharashtra grid factor is hardcoded at 0.82 kgCO2e per kWh, and Economy domestic flights use 0.133 kgCO2e per passenger-km. A proper system would query a maintained emission factor database — like Climatiq, Ecoinvent, or the UK DESNZ conversion factors spreadsheet — to get the most current, methodology-specific factor for each activity. Climatiq, for example, has an API that takes an activity type, geography, and year and returns the correct factor with source citation.

### Why I skipped it
Climatiq requires account registration and an API key. More importantly, selecting the right emission factor is not trivial — it depends on the GHG Protocol methodology the client has committed to, the geographical scope (India-specific vs. global average), the base year of the factor, and whether the client wants location-based or market-based accounting for electricity. Getting this right requires a product decision, not just a technical one. Hardcoding the most commonly used Indian emission factors (from CEA for the grid, from IPCC AR5 for fuels, from DEFRA for travel) gives a working prototype without adding that complexity. I documented exactly which values I used and where they come from so they can be replaced.

### What the real consequence would be in production
Hardcoded factors go stale. The Central Electricity Authority (CEA) publishes updated grid emission factors for India every year — the Maharashtra value changes between reporting periods. IPCC AR6 (2021) updated some fuel combustion factors from AR5. If we don't update constants.py when these change, all calculations silently use outdated numbers. More seriously, we can't explain to an auditor exactly which version of which methodology produced a specific number — we can only say "it was in our code." That's a red flag in a formal GHG audit.

### What I'd build next if given another week
I'd replace constants.py with an EmissionFactor database model that stores the factor value, the source (e.g. "CEA 2023-24 Annual Report"), the effective date, the geography, and the activity type. The parsers would query this table to find the current valid factor rather than reading from a Python dict. I'd also add an admin interface to update factors when new versions are published, with a complete version history so historical calculations remain reproducible.

---

## Tradeoff 3 — Role-Based Access Control (RBAC)

### What it is
A production ESG platform serving enterprise clients needs at least three distinct roles. An Analyst can view, review, flag, and approve data records. An Admin can manage tenants, create user accounts, and configure lookup tables (plant codes, material codes, emission factors). An Auditor gets read-only access to records that have been locked — they can export data but cannot modify anything. Right now, my platform has none of this — every authenticated user can do everything, including approve their own uploaded records, which violates basic separation-of-duties requirements in financial and sustainability reporting.

### Why I skipped it
Django has a built-in permissions system and I know how it works. The technical implementation is not complex — it's about 6-8 hours of work to add permission checks to every API endpoint, create the three groups in fixtures, wire the frontend to conditionally show/hide buttons based on the current user's role, and write tests to verify a user in one role can't access another role's endpoints. The problem was time. At 6-8 hours, adding RBAC would have pushed the entire build past the deadline, and I had to prioritize the core functionality — data in, normalize, review, approve — over access control. I also knew I'd be writing about this in TRADEOFFS.md, which is an honest place to surface it.

### What the real consequence would be in production
Currently, anyone who can log in can approve any record, including their own uploads. That's a control failure — in GHG accounting you need at least a maker-checker process where the person who uploads data is not the same person who approves it. Auditors would also currently see unapproved and flagged rows if they logged in, which is not appropriate — they should only see the locked, verified dataset. And there's no way right now for an admin to give a new analyst access to only one tenant's data. These are not cosmetic issues; they would prevent real enterprise adoption.

### What I'd build next if given another week
I'd use Django's built-in Group and Permission system to create three groups (Analyst, Admin, Auditor) and assign model-level permissions to each. I'd add a `@permission_required` decorator or DRF `IsAuthenticated` + custom permission class to every endpoint. On the frontend I'd add a role check to the AuthContext and conditionally render action buttons based on the user's group. The Auditor view would only call `GET /api/review/rows/?status=locked` and expose an export button — no approve or flag controls visible.

---

## Summary

| Feature | Why Skipped | Priority if Given More Time |
|---|---|---|
| Concur OAuth2 API integration | 1.5 days of plumbing for transport layer | High — eliminates manual upload step |
| Climatiq emission factor API | Product decision needed, API key required | High — required for audit defensibility |
| Role-based access control | 6-8 hours, would miss deadline | Critical — needed before any real client use |

All three of these are the right next steps before this platform could serve a real client. I'd tackle RBAC first because it's a security issue, then emission factor versioning because it affects audit credibility, then API integrations to eliminate manual upload steps.

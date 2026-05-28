# DECISIONS.md — Breathe ESG Ingestion Platform
### By: Shailesh Mishra | VIT Vellore

---

## Overview

This document explains every design and technical decision I made while building the Breathe ESG data ingestion platform. For each decision I've written what I chose, why I chose it, what the trade-off is, and what I'd ask the PM if I had the chance.

---

## Decision 1 — SAP Data Format: IDoc Flat File (Pipe-Delimited)

**What I chose:** I accepted SAP data as a pipe-delimited IDoc flat file export rather than integrating with SAP's OData API or using BAPI remote function calls.

**Why I chose it:** Most Indian enterprise companies running SAP don't expose their OData or BAPI endpoints to external systems without significant IT overhead — firewall rules, SAP BASIS configuration, and dedicated credentials. In practice, when a sustainability consultant asks an Indian manufacturing company for their fuel data, the answer is almost always "we'll send you the IDoc export." It's what SAP generates natively for batch data handoffs and it can be emailed, SFTP'd, or dropped into a shared folder without needing API access. I researched real IDoc formats and found the German-abbreviated column headers (WERKS, MATNR, MEINS, MENGE, BUDAT) are standard across most SAP ECC and S/4HANA installations. I kept those exact headers in my sample data so the ingestion logic reflects what a real file would look like.

**Trade-off:** IDoc flat files are a manual process. Someone at the client's plant has to run the export transaction (like MB51 or ME2M in SAP), download the file, and upload it to our platform. There's no automatic sync. If a client has 50 plants, that's 50 manual exports every reporting period.

**What I'd ask the PM:** Is there a minimum upload frequency requirement? If clients are reporting quarterly, manual uploads are fine. If they need monthly or weekly data, we'd need to build a proper SAP RFC/OData integration and the timeline estimate would change significantly.

---

## Decision 2 — Utility Data Format: Portal CSV Export

**What I chose:** I built the utility ingestion endpoint to accept a CSV export from the client's utility portal rather than parsing PDF bills or integrating with utility provider APIs.

**Why I chose it:** Every major Indian electricity utility — MSEDCL (Maharashtra), BSES and TPDDL (Delhi), TNEB (Tamil Nadu), DGVCL (Gujarat), TSSPDCL (Telangana) — provides a CSV export option in their online portal. It's the most universally available format. PDF bill parsing would require OCR and a custom parser for each utility's unique PDF layout, which would be extremely fragile and time-consuming. Utility APIs exist but require separate registration and credentials with each provider, and many Indian utilities don't offer public APIs at all. The CSV export gets me 80% of the way there with 20% of the complexity.

**Trade-off:** CSV exports are manual and inconsistent. MSEDCL's CSV looks nothing like BSES's CSV — column names differ, date formats differ, even the unit conventions differ (some use "Units", some use "kWh"). I handled the most common variations in my normalization logic, but a new utility could have a format we don't recognize.

**What I'd ask the PM:** How many different utility providers do our initial clients use? If it's 3–4, I can map their formats manually. If it's 20+, we'd need a more flexible mapping layer where a client admin can configure which column means what.

---

## Decision 3 — Travel Data Format: Concur-Style CSV Upload

**What I chose:** I built travel ingestion to accept a CSV file export from corporate travel platforms (Concur, Navan/TripActions, etc.) rather than integrating directly with the Concur REST API using OAuth2.

**Why I chose it:** Setting up a real Concur OAuth2 integration requires a Concur sandbox account, App Center registration, client credentials, token refresh logic, and webhook endpoints for real-time expense events. That's a week of work on its own, and it's entirely separate from the actual emissions calculation logic which is what this assignment is about. The CSV export path is available in every version of Concur and Navan as a standard feature — any travel manager can produce it. I focused on building solid normalization and emission factor logic (including the Haversine distance calculation for flights) rather than spending time on OAuth plumbing.

**Trade-off:** Analysts have to manually export the travel report from Concur every reporting period. There's also a risk of the analyst exporting the wrong date range or forgetting to include certain expense categories. An API integration would automate this and reduce human error.

**What I'd ask the PM:** Does the client's Concur subscription include API access? Some Concur plans restrict API access to enterprise tiers. Also — do we need real-time data or is monthly reporting sufficient? The answer changes the build completely.

---

## Decision 4 — Unit Normalization: Store Original AND Normalized Values

**What I chose:** For every record, I store both the original value and unit from the source file, and the normalized value in a standard unit (litres for fuel, kWh for electricity, km for travel). I also store the calculated kgCO2e separately.

**Why I chose it:** Auditors need to be able to trace every number back to its source. If I only store the normalized value, an auditor looking at a utility record showing 48,200 kWh can't verify whether that came from a file that said "48200 kWh" or "48.2 MWh" or "48,200 Units." Storing the original value means any dispute can be resolved by looking at the raw data. I also keep the RawIngestionRow with the complete unparsed JSON so even if my normalization logic has a bug, the original data is never lost.

**Trade-off:** This doubles the storage for numeric fields. For a small platform it doesn't matter. At scale (millions of rows per month), the extra columns add up.

**What I'd ask the PM:** Is there a data retention policy? Do we need to keep raw rows indefinitely for audit purposes, or only for the current reporting year? That would affect the storage design.

---

## Decision 5 — Multi-Tenancy: Shared Schema with Tenant FK

**What I chose:** All tenants (client companies) share the same database and the same tables. Every record has a tenant foreign key to identify which client it belongs to.

**Why I chose it:** Shared schema is simpler to build, simpler to migrate, and simpler to query when you need cross-tenant analytics. Separate databases per tenant (sometimes called database-per-tenant) means running migrations 50 times when you add a new column. For a prototype serving a handful of enterprise clients, shared schema is the right call. Django's ORM makes it easy to filter by tenant on every query.

**Trade-off:** If one tenant's data is ever subpoenaed or needs to be completely isolated for regulatory reasons, you can't just hand over their database — you have to export their rows carefully. Also, a bug that accidentally omits the tenant filter would expose data across clients, which is a serious security risk in production.

**What I'd ask the PM:** Do any of our target clients have data residency requirements (e.g. data must stay in India, or EU GDPR requirements)? That could force a move to separate schemas or databases per tenant, which would affect the deployment architecture.

---

## Decision 6 — Status Lifecycle: pending → approved/flagged → locked

**What I chose:** Every data row goes through a four-state lifecycle: `pending` (just ingested, needs review), `approved` (analyst has signed off), `flagged` (suspicious, needs attention), and `locked` (approved data handed to auditors — immutable).

**Why I chose it:** This maps directly to the real-world ESG audit workflow. Data comes in messy. An analyst reviews it. Some rows get approved, some get flagged for clarification. Once a client's reporting period closes and the data goes to auditors, it cannot change — otherwise the audit trail is invalid. The `locked` state enforces that. I also built the AuditLog model as append-only (no updates, only inserts) so every status change is permanently recorded with who did it and when.

**Trade-off:** There's currently no "unlock" path. If an analyst approves a row and later discovers it was wrong, they can't easily reverse it — they'd need a superuser to manually update the status. In a real system you'd want a formal re-opening workflow with a reason field and second-approval requirement.

**What I'd ask the PM:** What's the policy if an analyst approves bad data? Is there a correction workflow, or does the client submit an amendment in the next period? And do we need two-person approval (maker-checker) for rows above a certain kgCO2e threshold?

---

## Decision 7 — Flight Distance Calculation: Haversine Formula with Airport Code Lookup

**What I chose:** When a travel record has flight data but no distance provided, I calculate the great-circle distance using the Haversine formula with a hardcoded lookup table of airport coordinates.

**Why I chose it:** The alternative was calling an external API (like AviationStack, OAG, or FlightAware) to get actual flight distances. That requires API keys, adds latency to every ingestion run, introduces an external dependency that can fail, and costs money at scale. The Haversine formula gives a great-circle (straight-line over a sphere) distance which is a standard methodology accepted in most GHG Protocol-compliant emission calculations. It's accurate to within 2–5% of actual flight distance for most routes. I stored a lookup table of 11 major airports (BOM, DEL, BLR, MAA, COK, HYD, CCU, AMD, LHR, DXB, SFO) which covers the vast majority of routes an Indian enterprise company's employees would fly.

**Trade-off:** My airport lookup only has 11 airports. Any flight to an airport not in the list gets flagged as "unknown airport code." A real system would need the full IATA airport database (10,000+ airports). The Haversine formula also gives point-to-point distance, not actual flight path distance, which can be 5–10% shorter than the actual route for long-haul flights.

**What I'd ask the PM:** Is the GHG Protocol's great-circle distance methodology acceptable to our auditors? Some clients require ICAO-standard distances which account for actual flight paths. Also — should we integrate with a proper aviation distance API for production, or is the lookup table sufficient?

---

## What I Would Have Done Differently With More Time

If I had two more days, I would have added role-based access control properly. Right now any authenticated user can approve any row — there's no separation between Analyst (review/approve), Admin (manage tenants and users), and Auditor (read-only view of locked records). I would also have implemented the billing period splitting for cross-month utility data (currently I flag it but don't split it), and I would have replaced the hardcoded emission factors in constants.py with a proper versioned emission factor table that tracks which IPCC/CEA version each factor came from, so we can explain to auditors exactly where each number comes from.

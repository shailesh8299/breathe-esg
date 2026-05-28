# MODEL.md — Breathe ESG Data Ingestion Platform
### By: Shailesh Mishra | VIT Vellore
### Stack: Django + PostgreSQL + React

---

## Overview

Breathe ESG is a carbon emissions data ingestion and review platform. Enterprise clients generate emissions data from three operational sources — SAP (fuel and procurement), utility portals (electricity), and corporate travel platforms (flights, hotels, ground transport). This platform ingests that data, normalizes it into comparable units, calculates kgCO2e for each record, and routes it through an analyst review workflow before the data is locked for external auditors.

The data model is built around four core requirements:

1. **Multi-tenancy** — Multiple enterprise client companies share one platform
2. **Source traceability** — Every normalized record traces back to its original raw file row
3. **Unit normalization** — All quantities convert to standard units (litres, kWh, km) and kgCO2e
4. **Immutable audit trail** — Every status change is permanently logged with user and timestamp

---

## Schema Diagram

```
Tenant
  │
  ├──── IngestionRun (one per file upload)
  │          │
  │          └──── RawIngestionRow (one per row in file, original JSON)
  │                     │
  │                     ├──── SAPRecord      (normalized fuel data, Scope 1)
  │                     ├──── UtilityRecord  (normalized electricity data, Scope 2)
  │                     └──── TravelRecord   (normalized travel data, Scope 3)
  │
  └──── AuditLog (append-only, one row per status change)

Reference Tables (populated at setup, not per-tenant):
  PlantLookup    (SAP plant codes → plant names and states)
  MaterialLookup (SAP material codes → fuel types and emission factors)
```

---

## Tables

---

### 1. Tenant

Represents one enterprise client company using the platform.

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| name | CharField | e.g. "Acme Corp" |
| slug | SlugField (unique) | e.g. "acme-corp" |
| created_at | DateTimeField | Auto set on creation |

**Design decision:** Every record in the system (SAPRecord, UtilityRecord, TravelRecord) has a `tenant` foreign key. This is a shared-schema multi-tenancy approach — all clients share the same database tables, distinguished by tenant FK. I chose this over separate databases per tenant because it is simpler to manage, simpler to migrate (one migration runs once, not once per client), and sufficient for a prototype. The trade-off is that every query must filter by tenant to avoid cross-client data leaks.

---

### 2. IngestionRun

One row is created each time a file is uploaded. It tracks metadata about the upload and aggregates success/failure counts.

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| tenant | FK → Tenant | Which client uploaded this |
| source_type | CharField | Choices: SAP / UTILITY / TRAVEL |
| uploaded_filename | CharField | Original filename |
| uploaded_at | DateTimeField | Auto set on creation |
| uploaded_by | FK → User | Which analyst uploaded |
| total_rows | PositiveIntegerField | Total rows in the file |
| success_rows | PositiveIntegerField | Rows saved successfully |
| failed_rows | PositiveIntegerField | Rows that completely failed to parse |
| status | CharField | Choices: processing / completed / failed |

**Design decision:** The IngestionRun is the entry point for all data. Before any row-level processing begins, an IngestionRun record is created with `status=processing`. After all rows are processed, it is updated to `completed`. This means if the server crashes mid-processing, any IngestionRun stuck at `processing` is immediately visible as a problem. Analysts can see the upload history and know exactly which file produced which records.

---

### 3. RawIngestionRow

Stores the original, unparsed row from the source file as a JSON blob. This is the source of truth.

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| ingestion_run | FK → IngestionRun | Which upload this row came from |
| row_number | PositiveIntegerField | Row number in the original file |
| raw_data | JSONField | The entire original row as JSON |
| parse_error | TextField (nullable) | Error message if row failed completely |
| created_at | DateTimeField | Auto set on creation |

**Design decision:** This is the most important design decision in the whole model. I store the original data before any transformation happens. If normalization logic has a bug, the original data is never lost. If an auditor asks "what exactly was in the file?", we can show them. If we fix a normalization bug and need to reprocess, we have the raw data to reprocess from. The `OneToOneField` relationship from SAPRecord/UtilityRecord/TravelRecord back to RawIngestionRow means one raw row maps to exactly one normalized record — no duplication, no ambiguity.

---

### 4. BaseRecord (Abstract)

An abstract Django model. It is not a database table — its fields are copied into each of the three concrete record models. This avoids repeating the same 10+ fields in SAPRecord, UtilityRecord, and TravelRecord.

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| tenant | FK → Tenant | Which client this belongs to |
| ingestion_run | FK → IngestionRun | Which upload produced this |
| raw_row | OneToOneField → RawIngestionRow | Original unparsed data |
| kgco2e | FloatField (nullable) | Calculated carbon in kg CO2 equivalent |
| scope | IntegerField | 1, 2, or 3 (set automatically in save()) |
| status | CharField | pending / approved / flagged / locked |
| flagged_reason | TextField (nullable) | Why this row was flagged |
| approved_by | FK → User (nullable) | Who approved this record |
| approved_at | DateTimeField (nullable) | When it was approved |
| is_manually_edited | BooleanField | True if analyst edited any value directly |
| created_at | DateTimeField | Auto set on creation |
| updated_at | DateTimeField | Auto updated on every save |

**Design decision:** All three record types go through the same review lifecycle (pending → approved/flagged → locked) and all calculate kgCO2e. Putting these shared fields in an abstract base class makes the model DRY and ensures the review API can be written generically. Django's `abstract = True` means no extra join table is created — the fields are physically duplicated into each table, which is the right call for query performance.

---

### 5. SAPRecord

Normalized fuel and procurement data from SAP. Extends BaseRecord. Scope 1 (direct emissions from fuel combustion).

| Field | Type | Notes |
|---|---|---|
| plant_code | CharField | Original WERKS value from file (e.g. PL01) |
| plant_name | CharField (nullable) | Looked up from PlantLookup (e.g. Mumbai Plant) |
| material_code | CharField | Original MATNR value (e.g. DIESEL-001) |
| fuel_type | CharField (nullable) | Looked up from MaterialLookup (e.g. Diesel) |
| original_quantity | FloatField (nullable) | Quantity exactly as it appeared in file |
| original_unit | CharField (nullable) | Unit exactly as it appeared (L, GAL, LTR, KG) |
| normalized_quantity_liters | FloatField (nullable) | Converted to litres; null for mass-based fuels |
| normalized_quantity_kg | FloatField (nullable) | In KG; null for volume-based fuels |
| cost | FloatField (nullable) | Net value (NETWR) |
| currency | CharField (nullable) | WAERS field (INR, USD etc.) |
| posting_date | DateField (nullable) | Parsed from BUDAT (YYYYMMDD) |
| movement_type | CharField (nullable) | BWART field (e.g. 101 = goods receipt) |
| cost_centre | CharField (nullable) | KOSTL field |

The `save()` method automatically sets `scope = 1`.

**kgCO2e calculation:**
- Volume-based fuels (Diesel, Petrol, HFO): `kgco2e = normalized_quantity_liters × emission_factor_kg_per_litre`
- Mass-based fuels (CNG, LPG): `kgco2e = normalized_quantity_kg × emission_factor_kg_per_litre`

**Unit normalization:**
- L, LTR, LITRE → normalized to litres ×1.0
- GAL, GALLON → converted to litres ×3.785
- KG → stored in normalized_quantity_kg
- Anything else → row is flagged with reason "unknown unit: [value]"

---

## 6. UtilityRecord

Normalized electricity consumption data from utility portals. Extends BaseRecord. Scope 2 (indirect emissions from purchased electricity).

| Field | Type | Notes |
|---|---|---|
| account_id | CharField | Utility account ID |
| meter_id | CharField | Individual meter identifier |
| site_name | CharField (nullable) | Human-readable site name |
| state | CharField (nullable) | Indian state (used for grid emission factor lookup) |
| tariff_code | CharField (nullable) | e.g. HT-I, LT-II |
| supply_voltage | CharField (nullable) | e.g. 11kV, 415V |
| billing_period_start | DateField (nullable) | Start of billing period |
| billing_period_end | DateField (nullable) | End of billing period |
| period_days | IntegerField (nullable) | Calculated: (end - start).days |
| original_consumption | FloatField (nullable) | Consumption exactly as in file |
| original_unit | CharField (nullable) | Unit exactly as in file (kWh, Units, MWh) |
| normalized_kwh | FloatField (nullable) | Always in kWh after conversion |
| demand_kva | FloatField (nullable) | Maximum demand in kVA |
| bill_amount | FloatField (nullable) | Bill amount |
| currency | CharField (nullable) | INR |
| grid_emission_factor | FloatField (nullable) | kgCO2e/kWh for that state, stored at calculation time |

The `save()` method automatically sets `scope = 2`.

**Unit normalization:**
- kWh, KWH → use as-is
- Units, UNITS → treated as kWh (1 Unit = 1 kWh in India)
- MWh, MWH → multiply by 1000
- Anything else → flagged as "unknown consumption unit"

**Grid emission factors used (CEA 2022-23):**
Maharashtra: 0.82 | Delhi: 0.87 | Tamil Nadu: 0.78 | Gujarat: 0.88 | Telangana: 0.85

**Reason for storing `grid_emission_factor` on the record:** Grid factors change every year when CEA publishes updated data. Storing the factor used at calculation time means historical records remain reproducible even after the factor table is updated.

---

## 7. TravelRecord

Normalized corporate travel data. Extends BaseRecord. Scope 3 (value chain emissions from employee travel).

| Field | Type | Notes |
|---|---|---|
| trip_id | CharField | Groups all expenses for one trip |
| expense_type | CharField | FLIGHT / HOTEL / CAR / TRAIN |
| traveler_id | CharField (nullable) | Employee ID |
| traveler_name | CharField (nullable) | Employee name |
| travel_date | DateField (nullable) | Date of travel |
| origin | CharField (nullable) | Airport code or city |
| destination | CharField (nullable) | Airport code or city |
| distance_km | FloatField (nullable) | Distance — may be calculated |
| distance_was_calculated | BooleanField | True if calculated via Haversine, False if provided |
| class_of_travel | CharField (nullable) | Economy / Business / AC-2Tier etc. |
| nights | IntegerField (nullable) | For hotel records |
| amount_inr | FloatField (nullable) | Expense amount in INR |
| vendor | CharField (nullable) | Airline, hotel, cab company |
| booking_ref | CharField (nullable) | Booking reference number |
| is_international | BooleanField | True if either airport is outside India |
| emission_factor_used | FloatField (nullable) | Stored at calculation time |

The `save()` method automatically sets `scope = 3`.

**kgCO2e calculation by expense type:**

| Type | Calculation |
|---|---|
| FLIGHT Economy domestic | distance_km × 0.133 |
| FLIGHT Economy international | distance_km × 0.195 |
| FLIGHT Business (any) | Economy factor × 2.9 |
| TRAIN (AC) | distance_km × 0.041 |
| CAR / Taxi | distance_km × 0.171 |
| HOTEL | nights × 31.2 |

**Flight distance calculation:** When distance_km is not provided (which is almost always the case in Concur exports), the Haversine great-circle formula is applied using airport coordinates from `constants.py`. If an airport code is not in the lookup table, the row is flagged with "unknown airport code: [code]".

**Reason for storing `emission_factor_used`:** Same rationale as `grid_emission_factor` in UtilityRecord — emission factors update with new DEFRA/IPCC publications, so the factor used for a historical record must be frozen at the time of calculation.

---

## 8. AuditLog

Immutable record of every status change. One row is written each time a record moves from one status to another.

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| changed_by | FK → User | Who made the change |
| changed_at | DateTimeField | Exact timestamp (auto set) |
| record_type | CharField | SAP / UTILITY / TRAVEL |
| record_id | UUID | ID of the changed record |
| old_status | CharField | Status before the change |
| new_status | CharField | Status after the change |
| reason | TextField (nullable) | Required for flag actions |
| ip_address | GenericIPAddressField (nullable) | For security tracing |

**Design decision:** AuditLog uses `record_type + record_id` instead of a Django `GenericForeignKey`. A GenericForeignKey would allow direct ORM traversal but adds complexity and makes the table harder to query with raw SQL. For an audit log, raw queryability and simplicity matter more than ORM convenience. The table is append-only — the application never updates or deletes AuditLog rows.

---

## 9. PlantLookup

Reference table for SAP plant codes. Populated once via fixtures.

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| code | CharField (unique) | SAP plant code, e.g. PL01 |
| name | CharField | Human-readable name, e.g. Mumbai Plant |
| state | CharField | Indian state |
| country | CharField | Country |

**Seeded data:**
PL01 → Mumbai Plant, Maharashtra | PL02 → Delhi NCR Plant, Haryana | PL03 → Chennai Plant, Tamil Nadu | PL04 → Pune Plant, Maharashtra | PL05 → Ahmedabad Plant, Gujarat

---

## 10. MaterialLookup

Reference table for SAP material codes. Maps material code to fuel type and emission factor.

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| code | CharField (unique) | SAP material code, e.g. DIESEL-001 |
| fuel_type | CharField | e.g. Diesel, Petrol, CNG |
| scope | IntegerField | Always 1 for combustion fuels |
| emission_factor_kg_per_litre | FloatField | kgCO2e per litre (or per kg for CNG/LPG) |

**Seeded data (IPCC AR5 / DEFRA 2023 sources):**

| Code | Fuel | Factor | Unit |
|---|---|---|---|
| DIESEL-001 | Diesel | 2.68 | kgCO2e/litre |
| PETROL-002 | Petrol | 2.31 | kgCO2e/litre |
| HFO-003 | Heavy Fuel Oil | 3.17 | kgCO2e/litre |
| CNG-004 | CNG | 2.04 | kgCO2e/kg |
| LPG-005 | LPG | 1.51 | kgCO2e/kg |

**Design decision:** Emission factors are stored in MaterialLookup rather than hardcoded in the parser. When a SAPRecord is created, the factor is retrieved from this table and the calculated kgco2e is stored on the record. This means if a material's emission factor is updated, it only changes future calculations — historical records are unaffected because the calculation result is frozen on the record itself.

---

## Scope Categorization

GHG Protocol defines three scopes for emissions accounting:

| Scope | Category | Source in this platform | Why |
|---|---|---|---|
| Scope 1 | Direct emissions | SAP fuel records | Fuel burned in company-owned equipment |
| Scope 2 | Indirect — purchased energy | Utility electricity records | Electricity bought from the grid |
| Scope 3 | Indirect — value chain | Travel records | Employee travel not in company vehicles |

Scope is set automatically in each model's `save()` method and cannot be changed manually. This prevents accidental miscategorization.

---

## Status Lifecycle

```
                    ┌──────────────────────┐
                    │        pending        │  ← set on ingestion
                    └──────┬───────────────┘
                           │
              ┌────────────┼────────────────┐
              ▼                             ▼
     ┌────────────────┐          ┌─────────────────┐
     │    approved    │          │     flagged      │
     │ (analyst OK)   │          │  (needs review)  │
     └────────┬───────┘          └────────┬─────────┘
              │                           │
              │                    ┌──────▼──────────┐
              │                    │    approved      │
              │                    │ (after review)   │
              │                    └──────┬───────────┘
              │                           │
              └──────────────┬────────────┘
                             ▼
                    ┌────────────────┐
                    │     locked     │  ← immutable, sent to auditor
                    └────────────────┘
```

- **pending** → Record ingested, awaiting analyst review
- **flagged** → Automatically flagged by parser (missing data, unknown code, anomaly) or manually flagged by analyst with a reason
- **approved** → Analyst has reviewed and signed off
- **locked** → Data period is closed, handed to auditors — no further changes allowed

Every transition writes one row to AuditLog.

---

## What I Would Do Differently With More Time

**Role-based access control** — Currently any authenticated user can approve any record. A production system needs at minimum: Analyst (review/approve), Admin (manage tenants, users, lookup tables), and Auditor (read-only access to locked records only). This is the most critical missing piece before real client use.

**Emission factor versioning** — MaterialLookup stores one factor per material with no version history. When IPCC AR6 or CEA publishes updated factors, there is no way to know which factor version was used for a historical calculation (since I store the calculated kgco2e result but not which table version produced it). A proper design would add `effective_from` and `effective_to` date fields to MaterialLookup.

**Cross-month billing period splitting** — UtilityRecord currently stores the full billing period even when it crosses a calendar month boundary, and flags it for review. A proper implementation would split the consumption proportionally by days into two records (one for each month), enabling accurate monthly reporting.

**Second-approver requirement** — For records above a threshold kgco2e value (e.g. any record above 10,000 kgCO2e), a single analyst approval should not be sufficient. A maker-checker pattern — where the analyst who uploaded the file cannot be the same person who approves it — is standard practice in financial and sustainability reporting.

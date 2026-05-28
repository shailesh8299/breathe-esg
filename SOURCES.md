# SOURCES.md — Research Notes
### By: Shailesh Mishra | VIT Vellore

---

## How I Researched the Data Sources

Before writing a single line of ingestion code, I spent the first day researching what data from SAP, utility portals, and corporate travel platforms actually looks like in the real world. I did this because the assignment specifically says "we will ask why your sample data looks the way it does" — which means the sample data has to be defensible, not invented randomly. Below is what I found for each source, why I made the specific choices I made, and what would realistically break in a production deployment.

---

## Source 1 — SAP Fuel and Procurement Data

### What format I researched

SAP stores fuel and materials procurement data in the MM (Materials Management) module. The standard way to extract this data in batch is via an IDoc (Intermediate Document) — SAP's native format for exchanging data between systems. IDocs are flat files, usually pipe-delimited or fixed-width, with column headers that are SAP's internal technical field names. Most of these field names are German abbreviations because SAP was built in Germany by SAP SE.

The most relevant SAP transaction for fuel data extraction is MB51 (Material Document List) or MB52 (Warehouse Stocks of Material). Both can export to a flat file. The column headers they produce are the ones I used in my sample: MANDT (Mandant = client/tenant), WERKS (Werk = plant), MATNR (Materialnummer = material number), MEINS (Mengeneinheit = unit of measure), MENGE (Menge = quantity), NETWR (Nettowert = net value), WAERS (Währung = currency), BUDAT (Buchungsdatum = posting date), BWART (Bewegungsart = movement type).

### What I learned

Four things stood out in my research that shaped my sample data:

First, movement type 101 in SAP means "goods receipt against purchase order" — it's the standard code for recording that fuel was physically received at a plant. I used 101 for all rows because that's what a fuel procurement export would realistically contain.

Second, SAP plant codes (WERKS) like PL01, PL02 are meaningless without a lookup table. Different companies configure their own plant codes. An Indian manufacturer might have PL01 = Mumbai, PL02 = Delhi, but a different company might use MUM, DEL, or even numeric codes like 1000, 2000. I built a PlantLookup model so the ingestion pipeline translates codes to human-readable plant names.

Third, unit of measure inconsistency (MEINS field) is a real and common problem. Different procurement clerks at different plants may enter quantities in different units — one plant records diesel in litres (L or LTR), another might have a legacy SAP config that uses gallons (GAL) because the measurement equipment is imported. I included GAL in my sample to trigger the unit conversion logic (1 gallon = 3.785 litres).

Fourth, SAP's BUDAT (posting date) is always in YYYYMMDD format with no separators — for example "20240103" for January 3, 2024. This is a known parsing headache and I specifically included it so my parser has to handle it with datetime.strptime(value, '%Y%m%d').

### What my sample data looks like and why

I included 10 rows with these intentional problems:

- Row 2 uses GAL (gallons) instead of L — triggers unit conversion logic
- Row 5 uses LTR instead of L — tests that the normalizer accepts both spellings
- Row 6 (CNG-004) has blank MEINS unit — triggers "unknown unit" flag
- Row 7 uses USD currency instead of INR — tests that currency mismatches are saved as-is without flagging (currency is informational, not used in CO2e calculation)
- Row 9 has blank MENGE quantity — triggers "missing quantity" flag and sets kgco2e to null
- Rows use both KG-based fuels (HFO, CNG, LPG) and volume-based fuels (Diesel, Petrol) — tests both normalization branches

### What would break in real deployment

Every SAP installation is configured differently. A client running SAP S/4HANA might export additional columns we don't expect (Z-fields are custom fields with names like ZMATNR or ZWERKS added by the company's SAP consultants). A client running SAP ECC 6.0 might have a slightly different IDoc structure. Also, the plant code and material code lookup tables would need to be populated fresh for each new client — our current fixtures are just example data. The real onboarding process would need a client-specific mapping exercise before their first upload.

---

## Source 2 — Utility Electricity Data

### What format I researched

Indian electricity utilities provide online portals for commercial and industrial consumers to view and download bills. The download format varies by utility but CSV is universally available. I looked at what fields appear in portal exports from the major utilities that large Indian enterprises use: MSEDCL (Maharashtra State Electricity Distribution Co. Ltd), BSES Rajdhani and BSES Yamuna (Delhi), TNEB/TANGEDCO (Tamil Nadu), DGVCL (Gujarat), and TSSPDCL (Telangana).

Key fields that appear across all of them: account ID, meter ID, site name, billing period start and end dates, consumption figure, unit of measurement, demand in kVA, tariff code, bill amount, and the state. The tariff code is important because it identifies the consumer category — HT-I means High Tension industrial, LT-II means Low Tension commercial, etc.

### What I learned

Three things were critical for building the normalization logic:

First, Indian utilities use three different unit conventions in their exports. Most use kWh directly. Older systems — particularly older MSEDCL meters and some TNEB meters — show consumption as "Units" where 1 Unit = 1 kWh. This is a legacy holdover from when meters were read manually. A few high-voltage industrial connections report in MWh. My normalization logic handles all three: Units → 1:1 kWh, MWh → multiply by 1000.

Second, billing periods don't follow calendar months in India. MSEDCL reads meters every 30 days on a rolling cycle starting from when the meter was installed. So one site might have billing periods of Dec 26 to Jan 25, while the adjacent site has Jan 1 to Jan 31. This is a problem because clients want to report emissions by calendar month (Q1 = Jan+Feb+Mar). In my current implementation I flag cross-month billing periods but don't split them — that's a known limitation I documented in TRADEOFFS.md.

Third, grid emission factors in India are state-specific and published annually by the Central Electricity Authority (CEA). The national average is around 0.82 kgCO2e/kWh but Maharashtra is 0.82, Delhi is 0.87 (more coal-dependent), Tamil Nadu is 0.78 (higher renewable penetration), Gujarat is 0.88, and Telangana is 0.85. I used CEA's 2022-23 emission factor report as my source for these values.

### What my sample data looks like and why

I included 10 rows with these intentional problems:

- Row 2 (MTR-BOM-02): billing period Dec 26 to Jan 25 — crosses calendar month boundary, triggers the cross-month flag
- Row 4 (MTR-CHN-01): consumption unit is "Units" — triggers 1:1 conversion to kWh with a note in flagged_reason
- Row 6 (MTR-BOM-03): billing_period_start is blank — triggers "missing billing period start" flag
- Row 7 (MTR-HYD-01): consumption is 88400 MWh — after conversion this becomes 88,400,000 kWh which is unrealistically large for a single meter in one bill, triggering the anomaly detection flag ("unusually high consumption — verify before approving")
- Row 10 (MTR-DEL-02): consumption value is blank — triggers "missing consumption value" flag

The fact that rows 2 and 4 are flagged-but-valid (they should still be processed, just reviewed) was what exposed the success_rows counting bug I documented.

### What would break in real deployment

Different utilities export completely different column names. MSEDCL's CSV uses "Bill From" and "Bill To" where BSES uses "Start Date" and "End Date." A production system would need a per-utility column mapping configuration. Also, some utility portals export in Excel (.xlsx) not CSV — we'd need to handle that. The biggest production risk is meters at the same site being on different billing cycles — aggregating consumption for a site requires careful date-range handling that my current implementation doesn't do.

---

## Source 3 — Corporate Travel Data

### What format I researched

Concur (now SAP Concur) is the dominant corporate travel and expense management platform in Indian enterprises. Navan (formerly TripActions) is increasingly common in tech companies. Both platforms allow finance or HR teams to export travel data as CSV. I researched what a Concur expense report export looks like based on Concur's public documentation and community resources.

A Concur travel export has one row per expense line item — so a trip from Mumbai to Delhi and back produces two FLIGHT rows, plus a HOTEL row if the traveler booked accommodation, plus CAR rows for ground transport. Key fields: trip_id (groups all expenses for one trip), expense_type (FLIGHT/HOTEL/CAR/TRAIN), traveler details, travel date, origin, destination, amount, and vendor. Critically, Concur does not provide distance_km for flights — it only provides origin and destination airport codes. Distance calculation is the platform's responsibility.

### What I learned

Three key things shaped my travel ingestion design:

First, IATA airport codes are the standard way flights are identified in Concur data. For Indian routes the codes are: BOM (Mumbai), DEL (Delhi), BLR (Bengaluru), MAA (Chennai), COK (Kochi/Cochin), HYD (Hyderabad), CCU (Kolkata). International codes like LHR (London Heathrow), DXB (Dubai), and SFO (San Francisco) appear when employees travel internationally. I built an airport coordinate lookup table in constants.py and implemented the Haversine formula to calculate great-circle distances from these coordinates.

Second, the GHG Protocol's Corporate Value Chain (Scope 3) Standard specifies how to calculate flight emissions. You multiply distance by a passenger emission factor. The factor depends on cabin class — Business class has a significantly higher factor than Economy because business class seats take up more space per passenger (roughly 2.9× more). The DEFRA 2023 conversion factors give: Economy domestic at 0.133 kgCO2e/passenger-km, Economy international at 0.195 kgCO2e/passenger-km, with a Business class multiplier of 2.9×.

Third, different expense types need completely different calculation approaches. Hotels don't have distances — they use a per-night factor (31.2 kgCO2e/night is the global average from DEFRA). Trains have distances provided in the export. Cars/taxis have distances from the ride-hailing app. Only flights need distance calculation from airport codes. My travel parser handles all four branches.

### What my sample data looks like and why

I included 12 rows representing a realistic mix of travel scenarios:

- TRP-001 FLIGHT BOM→DEL (Economy domestic) + HOTEL 2 nights — basic domestic trip
- TRP-002 FLIGHT DEL→LHR + LHR→DEL (Business class) — international business class round trip, both flights should show the 2.9× multiplier
- TRP-003 FLIGHT BOM→BLR (Economy domestic) + CAR 18km (Uber from airport) — tests that CAR origin/destination being city names instead of airport codes is acceptable
- TRP-004 TRAIN NDLS→BCT 1384km — tests that railway station codes (NDLS, BCT) don't trigger the "unknown airport code" error since the expense_type is TRAIN not FLIGHT
- TRP-006 FLIGHT COK→DXB — tests Kochi as origin and international route
- TRP-007 FLIGHT BOM→SFO (Business) + HOTEL 5 nights — long-haul international Business class
- TRP-008 CAR MUM→PUNE 148km — distance provided directly, no calculation needed

### What would break in real deployment

The airport lookup table has 11 airports. Any flight to an airport not in the list (like Goa GOI, Jaipur JAI, or any smaller airport) gets flagged as "unknown airport code." For production I would need the complete IATA airport database with coordinates for all ~10,000 airports. Also, Concur exports vary significantly by company configuration — some companies enable fields like booking_class or cabin_type that others don't. The column names can differ between Concur versions. A Navan export has slightly different column names than a Concur export for the same data. Production would need a configurable column mapper.

---

## Emission Factor Sources

| Source | Factor | Value Used | Publication |
|---|---|---|---|
| Diesel | kgCO2e per litre | 2.68 | IPCC AR5 / DEFRA 2023 |
| Petrol | kgCO2e per litre | 2.31 | IPCC AR5 / DEFRA 2023 |
| Heavy Fuel Oil | kgCO2e per litre | 3.17 | IPCC AR5 |
| CNG | kgCO2e per kg | 2.04 | IPCC AR5 |
| LPG | kgCO2e per kg | 1.51 | IPCC AR5 |
| Maharashtra grid | kgCO2e per kWh | 0.82 | CEA 2022-23 |
| Delhi grid | kgCO2e per kWh | 0.87 | CEA 2022-23 |
| Tamil Nadu grid | kgCO2e per kWh | 0.78 | CEA 2022-23 |
| Gujarat grid | kgCO2e per kWh | 0.88 | CEA 2022-23 |
| Telangana grid | kgCO2e per kWh | 0.85 | CEA 2022-23 |
| Flight Economy domestic | kgCO2e per pass-km | 0.133 | DEFRA 2023 |
| Flight Economy international | kgCO2e per pass-km | 0.195 | DEFRA 2023 |
| Business class multiplier | dimensionless | 2.9× | DEFRA 2023 |
| Train AC | kgCO2e per pass-km | 0.041 | DEFRA 2023 |
| Car / Taxi | kgCO2e per km | 0.171 | DEFRA 2023 |
| Hotel | kgCO2e per night | 31.2 | DEFRA 2023 global average |

CEA = Central Electricity Authority, Government of India  
DEFRA = UK Department for Environment, Food and Rural Affairs  
IPCC AR5 = Intergovernmental Panel on Climate Change Fifth Assessment Report

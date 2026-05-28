import io
from datetime import datetime
import pandas as pd
from django.db import transaction
from django.contrib.auth.models import User
from ingestion.models import (
    RawIngestionRow, UtilityRecord
)
from ingestion.constants import GRID_EMISSION_FACTORS

class UtilityParser:
    """
    Service class responsible for parsing and processing CSV files for Utility 
    electricity data ingestion, handling raw row logging, validations, normalization,
    anomaly detection, and emission footprint calculation.
    """
    
    def parse(self, file, ingestion_run, tenant):
        # Read file content
        file_content = file.read()
        
        # Decode file bytes
        try:
            decoded_file = io.StringIO(file_content.decode('utf-8'))
        except UnicodeDecodeError:
            decoded_file = io.StringIO(file_content.decode('latin-1'))
            
        # Parse CSV file using pandas
        df = pd.read_csv(decoded_file, dtype=str)
        
        total_rows = len(df)
        success_rows = 0
        failed_rows = 0
        flagged_rows = 0
        errors = []
        
        for idx, row in df.iterrows():
            row_number = idx + 1
            
            # Strip whitespace and convert NaN/blank to None
            raw_data = {}
            for col_name, val in row.items():
                if pd.isna(val) or val is None:
                    raw_data[col_name] = None
                else:
                    raw_data[col_name] = str(val).strip()
            
            # STEP B - Store every raw row as RawIngestionRow with raw_data as JSON
            raw_row = RawIngestionRow.objects.create(
                ingestion_run=ingestion_run,
                row_number=row_number,
                raw_data=raw_data,
                parse_error=None
            )
            
            try:
                # STEP C - Validate and normalize each row
                flagged_reasons = []
                
                # 1. BILLING PERIOD validation
                start_str = raw_data.get('billing_period_start')
                end_str = raw_data.get('billing_period_end')
                
                start_date = None
                end_date = None
                period_days = None
                
                if not start_str or start_str == "":
                    flagged_reasons.append("missing billing period start")
                else:
                    try:
                        start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
                    except ValueError:
                        flagged_reasons.append(f"invalid billing period start: {start_str}")
                        
                if not end_str or end_str == "":
                    flagged_reasons.append("missing billing period end")
                else:
                    try:
                        end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
                    except ValueError:
                        flagged_reasons.append(f"invalid billing period end: {end_str}")
                        
                # If both dates parsed successfully, calculate period_days and cross-month checks
                if start_date and end_date:
                    period_days = (end_date - start_date).days
                    
                    # CROSS-MONTH note: If billing_period_start.month != billing_period_end.month
                    if start_date.month != end_date.month:
                        flagged_reasons.append("billing period crosses calendar month boundary")
                
                # 2. CONSUMPTION validation
                consumption_str = raw_data.get('consumption')
                consumption = None
                if not consumption_str or consumption_str == "":
                    flagged_reasons.append("missing consumption value")
                else:
                    try:
                        consumption = float(consumption_str)
                    except ValueError:
                        flagged_reasons.append(f"invalid consumption value: {consumption_str}")
                
                # 3. UNIT normalization (consumption_unit field)
                unit_str = raw_data.get('consumption_unit')
                unit_clean = str(unit_str).strip() if unit_str else ""
                normalized_kwh = None
                
                if unit_clean in ['kWh', 'KWH', 'kwh']:
                    if consumption is not None:
                        normalized_kwh = consumption
                elif unit_clean in ['Units', 'UNITS', 'Unit', 'unit']:
                    if consumption is not None:
                        normalized_kwh = consumption
                    flagged_reasons.append("unit was Units - treated as kWh")
                elif unit_clean in ['MWh', 'MWH', 'mwh']:
                    if consumption is not None:
                        normalized_kwh = consumption * 1000
                else:
                    flagged_reasons.append(f"unknown consumption unit: {unit_clean}")
                
                # 4. ANOMALY detection
                if normalized_kwh is not None:
                    if normalized_kwh > 50000:
                        flagged_reasons.append(f"unusually high consumption: {normalized_kwh} kWh - verify before approving")
                
                # STEP D - Calculate kgco2e
                grid_factor = 0.82
                state_val = raw_data.get('state')
                if state_val and state_val in GRID_EMISSION_FACTORS:
                    grid_factor = GRID_EMISSION_FACTORS[state_val]
                else:
                    grid_factor = GRID_EMISSION_FACTORS['default']
                    
                kgco2e = None
                if normalized_kwh is not None:
                    kgco2e = normalized_kwh * grid_factor
                
                # STEP E - Set status
                if flagged_reasons:
                    status_val = 'flagged'
                    flagged_reason_val = '; '.join(flagged_reasons)
                    flagged_rows += 1
                    success_rows += 1  # ← ADD THIS LINE
                    errors.append({
                        "row_number": row_number,
                        "reason": flagged_reason_val,
                        "raw_data": raw_data
                    })
                else:
                    status_val = 'pending'
                    flagged_reason_val = None
                    success_rows += 1
                
                # Extract other optional or straight-mapped fields
                account_id_val = raw_data.get('account_id')
                meter_id_val = raw_data.get('meter_id')
                site_name_val = raw_data.get('site_name')
                tariff_code_val = raw_data.get('tariff_code')
                supply_voltage_val = raw_data.get('supply_voltage')
                currency_val = raw_data.get('currency')
                
                demand_kva_val = None
                demand_str = raw_data.get('demand_kva')
                if demand_str:
                    try:
                        demand_kva_val = float(demand_str)
                    except ValueError:
                        pass
                        
                bill_amount_val = None
                bill_str = raw_data.get('bill_amount')
                if bill_str:
                    try:
                        bill_amount_val = float(bill_str)
                    except ValueError:
                        pass
                
                # Create and save UtilityRecord
                UtilityRecord.objects.create(
                    tenant=tenant,
                    ingestion_run=ingestion_run,
                    raw_row=raw_row,
                    account_id=account_id_val or "",
                    meter_id=meter_id_val or "",
                    site_name=site_name_val,
                    state=state_val,
                    tariff_code=tariff_code_val,
                    supply_voltage=supply_voltage_val,
                    billing_period_start=start_date,
                    billing_period_end=end_date,
                    period_days=period_days,
                    original_consumption=consumption,
                    original_unit=unit_str,
                    normalized_kwh=normalized_kwh,
                    demand_kva=demand_kva_val,
                    bill_amount=bill_amount_val,
                    currency=currency_val,
                    grid_emission_factor=grid_factor,
                    kgco2e=kgco2e,
                    status=status_val,
                    flagged_reason=flagged_reason_val
                )
                
            except Exception as e:
                # Fatal parsing/database save error for this row
                failed_rows += 1
                raw_row.parse_error = str(e)
                raw_row.save()
                
                errors.append({
                    "row_number": row_number,
                    "reason": f"fatal error: {str(e)}",
                    "raw_data": raw_data
                })
                
        # STEP F - Update IngestionRun at end
        ingestion_run.total_rows = total_rows
        ingestion_run.success_rows = success_rows
        ingestion_run.failed_rows = failed_rows
        ingestion_run.status = 'completed'
        ingestion_run.save()
        
        # STEP G - Return exact JSON response
        return {
            "run_id": str(ingestion_run.id),
            "source_type": "UTILITY",
            "total_rows": total_rows,
            "success_rows": success_rows,
            "failed_rows": failed_rows,
            "flagged_rows": flagged_rows,
            "errors": errors
        }

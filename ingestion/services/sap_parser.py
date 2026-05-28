import io
from datetime import datetime
import pandas as pd
from django.db import transaction
from django.contrib.auth.models import User
from ingestion.models import (
    RawIngestionRow, SAPRecord, PlantLookup, MaterialLookup
)

class SAPParser:
    """
    Service class responsible for parsing and processing pipe-delimited flat files 
    for SAP record ingestion, handling raw row logging, validation, normalization,
    and emission calculation.
    """
    
    def parse(self, file, ingestion_run, tenant):
        # Read the file content
        file_content = file.read()
        
        # Decode the file bytes to string safely
        try:
            decoded_file = io.StringIO(file_content.decode('utf-8'))
        except UnicodeDecodeError:
            decoded_file = io.StringIO(file_content.decode('latin-1'))
            
        # Parse the pipe-delimited flat file using pandas
        # Keep default NA to parse blank values as NaN
        df = pd.read_csv(decoded_file, sep='|', dtype=str)
        
        total_rows = len(df)
        success_rows = 0
        failed_rows = 0
        flagged_rows = 0
        errors = []
        
        for idx, row in df.iterrows():
            row_number = idx + 1
            
            # Clean row values: convert NaN to None and strip spaces
            raw_data = {}
            for col_name, val in row.items():
                if pd.isna(val) or val is None:
                    raw_data[col_name] = None
                else:
                    raw_data[col_name] = str(val).strip()
            
            # STEP B - Store every raw row as RawIngestionRow before any processing
            raw_row = RawIngestionRow.objects.create(
                ingestion_run=ingestion_run,
                row_number=row_number,
                raw_data=raw_data,
                parse_error=None
            )
            
            try:
                # STEP C - Validate and normalize
                flagged_reasons = []
                
                # 1. PLANT CODE lookup (WERKS field)
                werks_value = raw_data.get('WERKS')
                plant = None
                plant_name = None
                if not werks_value:
                    flagged_reasons.append("unknown plant code: None")
                else:
                    try:
                        plant = PlantLookup.objects.get(code=werks_value)
                        plant_name = plant.name
                    except PlantLookup.DoesNotExist:
                        flagged_reasons.append(f"unknown plant code: {werks_value}")
                
                # 2. MATERIAL lookup (MATNR field)
                matnr_value = raw_data.get('MATNR')
                material = None
                fuel_type = None
                if not matnr_value:
                    flagged_reasons.append("unknown material code: None")
                else:
                    try:
                        material = MaterialLookup.objects.get(code=matnr_value)
                        fuel_type = material.fuel_type
                    except MaterialLookup.DoesNotExist:
                        flagged_reasons.append(f"unknown material code: {matnr_value}")
                
                # 3. DATE parsing (BUDAT field)
                budat_value = raw_data.get('BUDAT')
                posting_date = None
                if not budat_value:
                    flagged_reasons.append("missing date")
                else:
                    try:
                        posting_date = datetime.strptime(budat_value, '%Y%m%d').date()
                    except ValueError:
                        flagged_reasons.append(f"invalid date format: {budat_value}")
                
                # 4. QUANTITY validation (MENGE field)
                menge_value = raw_data.get('MENGE')
                quantity = None
                if not menge_value or menge_value == "":
                    flagged_reasons.append("missing quantity")
                else:
                    try:
                        quantity = float(menge_value)
                    except ValueError:
                        flagged_reasons.append(f"invalid quantity: {menge_value}")
                
                # 5. UNIT normalization (MEINS field)
                meins_val = raw_data.get('MEINS')
                meins_str = str(meins_val).strip() if meins_val else ""
                normalized_quantity_liters = None
                normalized_quantity_kg = None
                
                if meins_str.upper() in ['L', 'LTR', 'LITRE', 'LITRES']:
                    if quantity is not None:
                        normalized_quantity_liters = quantity * 1.0
                elif meins_str.upper() in ['GAL', 'GALLON']:
                    if quantity is not None:
                        normalized_quantity_liters = quantity * 3.785
                elif meins_str.upper() == 'KG':
                    if quantity is not None:
                        normalized_quantity_kg = quantity
                else:
                    flagged_reasons.append(f"unknown unit: {meins_str}")
                
                # STEP D - Calculate kgco2e
                kgco2e = None
                if quantity is not None and material is not None:
                    if normalized_quantity_liters is not None:
                        kgco2e = normalized_quantity_liters * material.emission_factor_kg_per_litre
                    elif normalized_quantity_kg is not None:
                        kgco2e = normalized_quantity_kg * material.emission_factor_kg_per_litre
                
                # STEP E - Set status
                if flagged_reasons:
                    status_val = 'flagged'
                    flagged_reason_val = '; '.join(flagged_reasons)
                    flagged_rows += 1
                    
                    # Record the validation failure for returning in response
                    errors.append({
                        "row_number": row_number,
                        "reason": flagged_reason_val,
                        "raw_data": raw_data
                    })
                else:
                    status_val = 'pending'
                    flagged_reason_val = None
                    success_rows += 1
                
                # Retrieve additional optional fields for SAPRecord
                cost_val = None
                netwr_value = raw_data.get('NETWR')
                if netwr_value:
                    try:
                        cost_val = float(netwr_value)
                    except ValueError:
                        pass
                        
                currency_val = raw_data.get('WAERS')
                movement_type_val = raw_data.get('BWART')
                cost_centre_val = raw_data.get('KOSTL')
                
                # Create and save SAPRecord
                SAPRecord.objects.create(
                    tenant=tenant,
                    ingestion_run=ingestion_run,
                    raw_row=raw_row,
                    plant_code=werks_value or "",
                    plant_name=plant_name,
                    material_code=matnr_value or "",
                    fuel_type=fuel_type,
                    original_quantity=quantity,
                    original_unit=meins_val,
                    normalized_quantity_liters=normalized_quantity_liters,
                    normalized_quantity_kg=normalized_quantity_kg,
                    cost=cost_val,
                    currency=currency_val,
                    posting_date=posting_date,
                    movement_type=movement_type_val,
                    cost_centre=cost_centre_val,
                    kgco2e=kgco2e,
                    status=status_val,
                    flagged_reason=flagged_reason_val
                )
                
            except Exception as e:
                # Fatal error in row processing / database save
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
        # Ingestion run status is set to completed
        ingestion_run.status = 'completed'
        ingestion_run.save()
        
        # STEP G - Return exact JSON format structure
        return {
            "run_id": str(ingestion_run.id),
            "source_type": "SAP",
            "total_rows": total_rows,
            "success_rows": success_rows,
            "failed_rows": failed_rows,
            "flagged_rows": flagged_rows,
            "errors": errors
        }

import io
import math
from datetime import datetime
import pandas as pd
from django.db import transaction
from django.contrib.auth.models import User
from ingestion.models import (
    RawIngestionRow, TravelRecord
)
from ingestion.constants import (
    TRAVEL_EMISSION_FACTORS, AIRPORT_COORDINATES, INDIAN_AIRPORT_CODES
)

def haversine(lat1, lon1, lat2, lon2):
    """
    Haversine formula to compute great-circle distance between two points in km.
    """
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

class TravelParser:
    """
    Service class responsible for parsing and processing corporate travel CSV files,
    handling flight distance calculation using Haversine formula, hotel nights check,
    car/train mileage check, and emission calculation.
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
            
            # Clean row values
            raw_data = {}
            for col_name, val in row.items():
                if pd.isna(val) or val is None:
                    raw_data[col_name] = None
                else:
                    raw_data[col_name] = str(val).strip()
            
            # STEP B - Store every raw row as RawIngestionRow
            raw_row = RawIngestionRow.objects.create(
                ingestion_run=ingestion_run,
                row_number=row_number,
                raw_data=raw_data,
                parse_error=None
            )
            
            try:
                # STEP C - Validate and normalize
                flagged_reasons = []
                
                # Extract clean core fields
                trip_id = raw_data.get('trip_id') or ""
                expense_type = raw_data.get('expense_type') or ""
                traveler_id = raw_data.get('traveler_id')
                traveler_name = raw_data.get('traveler_name')
                origin = raw_data.get('origin')
                destination = raw_data.get('destination')
                class_of_travel = raw_data.get('class_of_travel')
                vendor = raw_data.get('vendor')
                booking_ref = raw_data.get('booking_ref')
                
                # Safe date parse
                travel_date_str = raw_data.get('travel_date')
                travel_date = None
                if travel_date_str:
                    try:
                        travel_date = datetime.strptime(travel_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        flagged_reasons.append(f"invalid travel date: {travel_date_str}")
                
                # Safe numeric parsing
                dist_val = raw_data.get('distance_km')
                distance_km = None
                if dist_val and dist_val != "":
                    try:
                        distance_km = float(dist_val)
                    except ValueError:
                        pass
                        
                prov_val = str(raw_data.get('distance_provided')).lower().strip() if raw_data.get('distance_provided') else ""
                distance_provided = prov_val in ['true', '1', 'yes']
                
                nights_val = raw_data.get('nights')
                nights = None
                if nights_val and nights_val != "":
                    try:
                        nights = int(float(nights_val))
                    except ValueError:
                        pass
                
                amount_val = raw_data.get('amount_inr')
                amount_inr = None
                if amount_val and amount_val != "":
                    try:
                        amount_inr = float(amount_val)
                    except ValueError:
                        pass
                
                # Init variables for processing
                distance_was_calculated = False
                is_international = False
                emission_factor_used = None
                kgco2e = None
                
                exp_type_upper = expense_type.upper()
                
                # Process based on expense type
                if exp_type_upper == 'FLIGHT':
                    # Check distance calculation requirements
                    if distance_km is None or not distance_provided:
                        # Haversine distance lookup & calculation
                        orig_coords = AIRPORT_COORDINATES.get(origin)
                        dest_coords = AIRPORT_COORDINATES.get(destination)
                        
                        if not orig_coords:
                            flagged_reasons.append(f"unknown airport code: {origin}")
                        if not dest_coords:
                            flagged_reasons.append(f"unknown airport code: {destination}")
                            
                        if orig_coords and dest_coords:
                            lat1 = orig_coords['lat']
                            lon1 = orig_coords['lon']
                            lat2 = dest_coords['lat']
                            lon2 = dest_coords['lon']
                            distance_km = haversine(lat1, lon1, lat2, lon2)
                            distance_was_calculated = True
                    
                    # Determine international classification
                    if origin not in INDIAN_AIRPORT_CODES or destination not in INDIAN_AIRPORT_CODES:
                        is_international = True
                    else:
                        is_international = False
                        
                    # Determine emission factor
                    class_clean = str(class_of_travel).strip() if class_of_travel else ""
                    is_business = "business" in class_clean.lower()
                    
                    if is_business:
                        multiplier = TRAVEL_EMISSION_FACTORS['FLIGHT_BUSINESS_MULTIPLIER']
                        if is_international:
                            factor = TRAVEL_EMISSION_FACTORS['FLIGHT_ECONOMY_INTERNATIONAL'] * multiplier
                        else:
                            factor = TRAVEL_EMISSION_FACTORS['FLIGHT_ECONOMY_DOMESTIC'] * multiplier
                    else:
                        if is_international:
                            factor = TRAVEL_EMISSION_FACTORS['FLIGHT_ECONOMY_INTERNATIONAL']
                        else:
                            factor = TRAVEL_EMISSION_FACTORS['FLIGHT_ECONOMY_DOMESTIC']
                            
                    emission_factor_used = factor
                    if distance_km is not None:
                        kgco2e = distance_km * factor
                
                elif exp_type_upper == 'HOTEL':
                    emission_factor_used = TRAVEL_EMISSION_FACTORS['HOTEL_PER_NIGHT']
                    if nights is None or nights == 0:
                        flagged_reasons.append("missing nights for hotel booking")
                    else:
                        kgco2e = nights * emission_factor_used
                
                elif exp_type_upper == 'CAR':
                    emission_factor_used = TRAVEL_EMISSION_FACTORS['CAR']
                    if distance_km is None:
                        flagged_reasons.append("missing distance for car journey")
                    else:
                        kgco2e = distance_km * emission_factor_used
                
                elif exp_type_upper == 'TRAIN':
                    emission_factor_used = TRAVEL_EMISSION_FACTORS['TRAIN_AC']
                    if distance_km is None:
                        flagged_reasons.append("missing distance for train journey")
                    else:
                        kgco2e = distance_km * emission_factor_used
                else:
                    flagged_reasons.append(f"unknown expense type: {expense_type}")
                
                # STEP E - Set status
                if flagged_reasons:
                    status_val = 'flagged'
                    flagged_reason_val = '; '.join(flagged_reasons)
                    flagged_rows += 1
                    success_rows += 1
                    
                    # Record the validation failure/warning for response
                    errors.append({
                        "row_number": row_number,
                        "reason": flagged_reason_val,
                        "raw_data": raw_data
                    })
                else:
                    status_val = 'pending'
                    flagged_reason_val = None
                    success_rows += 1
                
                # Create and save TravelRecord
                TravelRecord.objects.create(
                    tenant=tenant,
                    ingestion_run=ingestion_run,
                    raw_row=raw_row,
                    trip_id=trip_id,
                    expense_type=expense_type,
                    traveler_id=traveler_id,
                    traveler_name=traveler_name,
                    travel_date=travel_date,
                    origin=origin,
                    destination=destination,
                    distance_km=distance_km,
                    distance_was_calculated=distance_was_calculated,
                    class_of_travel=class_of_travel,
                    nights=nights,
                    amount_inr=amount_inr,
                    vendor=vendor,
                    booking_ref=booking_ref,
                    is_international=is_international,
                    emission_factor_used=emission_factor_used,
                    kgco2e=kgco2e,
                    status=status_val,
                    flagged_reason=flagged_reason_val
                )
                
            except Exception as e:
                # Fatal row processing / DB save failure
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
            "source_type": "TRAVEL",
            "total_rows": total_rows,
            "success_rows": success_rows,
            "failed_rows": failed_rows,
            "flagged_rows": flagged_rows,
            "errors": errors
        }

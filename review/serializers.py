from rest_framework import serializers
from ingestion.models import IngestionRun

class IngestionRunSerializer(serializers.ModelSerializer):
    """
    Serializer to represent ingestion runs.
    """
    class Meta:
        model = IngestionRun
        fields = [
            'id', 'source_type', 'uploaded_filename', 
            'uploaded_at', 'total_rows', 'success_rows', 
            'failed_rows', 'status'
        ]

class UnifiedRowSerializer(serializers.Serializer):
    """
    Unified serializer representing records from all three models:
    SAPRecord, UtilityRecord, and TravelRecord.
    """
    
    def to_representation(self, instance):
        class_name = instance.__class__.__name__
        
        # Check source type and run mapping logic
        if class_name == 'SAPRecord':
            source_type = 'SAP'
            record_date = instance.posting_date
            description = f"{instance.fuel_type or ''} — {instance.plant_name or ''}"
            
            original_value = instance.original_quantity
            original_unit = instance.original_unit
            
            if instance.normalized_quantity_liters is not None:
                normalized_value = instance.normalized_quantity_liters
                normalized_unit = "L"
            else:
                normalized_value = instance.normalized_quantity_kg
                normalized_unit = "kg"
                
        elif class_name == 'UtilityRecord':
            source_type = 'UTILITY'
            record_date = instance.billing_period_start
            description = f"{instance.meter_id or ''} — {instance.site_name or ''}"
            
            original_value = instance.original_consumption
            original_unit = instance.original_unit
            
            normalized_value = instance.normalized_kwh
            normalized_unit = "kWh"
            
        elif class_name == 'TravelRecord':
            source_type = 'TRAVEL'
            record_date = instance.travel_date
            description = f"{instance.expense_type or ''} {instance.origin or ''}→{instance.destination or ''}".strip()
            
            original_value = instance.amount_inr
            original_unit = "INR"
            
            # Hotels use nights, flights/trains/cars use distance_km
            if str(instance.expense_type).upper() == 'HOTEL':
                normalized_value = instance.nights
                normalized_unit = "nights"
            else:
                normalized_value = instance.distance_km
                normalized_unit = "km"
        else:
            # Fallback for generic representations or dictionaries
            return instance
            
        return {
            "id": str(instance.id),
            "source_type": source_type,
            "tenant_name": instance.tenant.name if instance.tenant else None,
            "record_date": record_date.strftime('%Y-%m-%d') if record_date else None,
            "description": description,
            "original_value": original_value,
            "original_unit": original_unit,
            "normalized_value": normalized_value,
            "normalized_unit": normalized_unit,
            "kgco2e": instance.kgco2e,
            "scope": instance.scope,
            "status": instance.status,
            "flagged_reason": instance.flagged_reason,
            "approved_by_name": instance.approved_by.username if instance.approved_by else None,
            "approved_at": instance.approved_at.isoformat() if instance.approved_at else None,
            "is_manually_edited": instance.is_manually_edited
        }

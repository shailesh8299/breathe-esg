from django.contrib import admin
from .models import (
    Tenant, IngestionRun, RawIngestionRow, 
    SAPRecord, UtilityRecord, TravelRecord, 
    PlantLookup, MaterialLookup, AuditLog
)

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at')
    search_fields = ('name', 'slug')

@admin.register(IngestionRun)
class IngestionRunAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'source_type', 'status', 'uploaded_at', 'total_rows', 'success_rows')
    list_filter = ('source_type', 'status', 'tenant')
    search_fields = ('uploaded_filename',)

@admin.register(RawIngestionRow)
class RawIngestionRowAdmin(admin.ModelAdmin):
    list_display = ('ingestion_run', 'row_number', 'created_at')
    list_filter = ('ingestion_run__source_type',)

class BaseRecordAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'status', 'scope', 'kgco2e', 'created_at')
    list_filter = ('status', 'scope', 'is_manually_edited')
    search_fields = ('id',)

@admin.register(SAPRecord)
class SAPRecordAdmin(BaseRecordAdmin):
    list_display = BaseRecordAdmin.list_display + ('plant_code', 'fuel_type')
    search_fields = ('plant_code', 'material_code')

@admin.register(UtilityRecord)
class UtilityRecordAdmin(BaseRecordAdmin):
    list_display = BaseRecordAdmin.list_display + ('account_id', 'site_name', 'normalized_kwh')
    search_fields = ('account_id', 'meter_id', 'site_name')

@admin.register(TravelRecord)
class TravelRecordAdmin(BaseRecordAdmin):
    list_display = BaseRecordAdmin.list_display + ('expense_type', 'origin', 'destination', 'distance_km')
    list_filter = BaseRecordAdmin.list_filter + ('expense_type', 'is_international')

@admin.register(PlantLookup)
class PlantLookupAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'state', 'country')
    search_fields = ('code', 'name')

@admin.register(MaterialLookup)
class MaterialLookupAdmin(admin.ModelAdmin):
    list_display = ('code', 'fuel_type', 'scope', 'emission_factor_kg_per_litre')
    search_fields = ('code', 'fuel_type')

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('record_type', 'record_id', 'old_status', 'new_status', 'changed_by', 'changed_at')
    list_filter = ('record_type', 'old_status', 'new_status', 'changed_at')
    search_fields = ('record_id', 'reason', 'ip_address')

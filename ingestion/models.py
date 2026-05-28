import uuid
from django.db import models
from django.contrib.auth.models import User

SOURCE_CHOICES = [
    ('SAP', 'SAP'),
    ('UTILITY', 'UTILITY'),
    ('TRAVEL', 'TRAVEL'),
]

RUN_STATUS_CHOICES = [
    ('processing', 'Processing'),
    ('completed', 'Completed'),
    ('failed', 'Failed'),
]

RECORD_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    ('flagged', 'Flagged'),
    ('locked', 'Locked'),
]

EXPENSE_TYPE_CHOICES = [
    ('FLIGHT', 'Flight'),
    ('HOTEL', 'Hotel'),
    ('CAR', 'Car'),
    ('TRAIN', 'Train'),
]

class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.name

class IngestionRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ingestion_runs')
    source_type = models.CharField(max_length=10, choices=SOURCE_CHOICES)
    uploaded_filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    total_rows = models.PositiveIntegerField(default=0)
    success_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=RUN_STATUS_CHOICES, default='processing')
    def __str__(self):
        return f"{self.tenant.name} - {self.source_type} - {self.uploaded_at.strftime('%Y-%m-%d')}"

class RawIngestionRow(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ingestion_run = models.ForeignKey(IngestionRun, on_delete=models.CASCADE, related_name='raw_rows')
    row_number = models.PositiveIntegerField()
    raw_data = models.JSONField()
    parse_error = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['row_number']
    def __str__(self):
        return f"Run {self.ingestion_run.id} - Row {self.row_number}"

class PlantLookup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    def __str__(self):
        return f"{self.code} - {self.name}"

class MaterialLookup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True)
    fuel_type = models.CharField(max_length=100)
    scope = models.IntegerField(default=1)
    emission_factor_kg_per_litre = models.FloatField()
    def __str__(self):
        return f"{self.code} ({self.fuel_type})"

class BaseRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    ingestion_run = models.ForeignKey(IngestionRun, on_delete=models.CASCADE)
    raw_row = models.OneToOneField(RawIngestionRow, on_delete=models.CASCADE)
    kgco2e = models.FloatField(null=True, blank=True)
    scope = models.IntegerField()
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default='pending')
    flagged_reason = models.TextField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    is_manually_edited = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

class SAPRecord(BaseRecord):
    plant_code = models.CharField(max_length=50)
    plant_name = models.CharField(max_length=255, null=True, blank=True)
    material_code = models.CharField(max_length=50)
    fuel_type = models.CharField(max_length=100, null=True, blank=True)
    original_quantity = models.FloatField(null=True, blank=True)
    original_unit = models.CharField(max_length=20, null=True, blank=True)
    normalized_quantity_liters = models.FloatField(null=True, blank=True)
    normalized_quantity_kg = models.FloatField(null=True, blank=True)
    cost = models.FloatField(null=True, blank=True)
    currency = models.CharField(max_length=10, null=True, blank=True)
    posting_date = models.DateField(null=True, blank=True)
    movement_type = models.CharField(max_length=50, null=True, blank=True)
    cost_centre = models.CharField(max_length=100, null=True, blank=True)
    def save(self, *args, **kwargs):
        self.scope = 1
        super().save(*args, **kwargs)

class UtilityRecord(BaseRecord):
    account_id = models.CharField(max_length=100)
    meter_id = models.CharField(max_length=100)
    site_name = models.CharField(max_length=255, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    tariff_code = models.CharField(max_length=100, null=True, blank=True)
    supply_voltage = models.CharField(max_length=50, null=True, blank=True)
    billing_period_start = models.DateField(null=True, blank=True)
    billing_period_end = models.DateField(null=True, blank=True)
    period_days = models.IntegerField(null=True, blank=True)
    original_consumption = models.FloatField(null=True, blank=True)
    original_unit = models.CharField(max_length=20, null=True, blank=True)
    normalized_kwh = models.FloatField(null=True, blank=True)
    demand_kva = models.FloatField(null=True, blank=True)
    bill_amount = models.FloatField(null=True, blank=True)
    currency = models.CharField(max_length=10, null=True, blank=True)
    grid_emission_factor = models.FloatField(null=True, blank=True)
    def save(self, *args, **kwargs):
        self.scope = 2
        super().save(*args, **kwargs)

class TravelRecord(BaseRecord):
    trip_id = models.CharField(max_length=100)
    expense_type = models.CharField(max_length=20, choices=EXPENSE_TYPE_CHOICES)
    traveler_id = models.CharField(max_length=100, null=True, blank=True)
    traveler_name = models.CharField(max_length=255, null=True, blank=True)
    travel_date = models.DateField(null=True, blank=True)
    origin = models.CharField(max_length=100, null=True, blank=True)
    destination = models.CharField(max_length=100, null=True, blank=True)
    distance_km = models.FloatField(null=True, blank=True)
    distance_was_calculated = models.BooleanField(default=False)
    class_of_travel = models.CharField(max_length=50, null=True, blank=True)
    nights = models.IntegerField(null=True, blank=True)
    amount_inr = models.FloatField(null=True, blank=True)
    vendor = models.CharField(max_length=255, null=True, blank=True)
    booking_ref = models.CharField(max_length=100, null=True, blank=True)
    is_international = models.BooleanField(default=False)
    emission_factor_used = models.FloatField(null=True, blank=True)
    def save(self, *args, **kwargs):
        self.scope = 3
        super().save(*args, **kwargs)

class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='ingestion_audit_logs')
    changed_at = models.DateTimeField(auto_now_add=True)
    record_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    record_id = models.UUIDField()
    old_status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES)
    new_status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES)
    reason = models.TextField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    def __str__(self):
        return f"{self.record_type} {self.record_id}: {self.old_status} -> {self.new_status}"

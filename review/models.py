import uuid
from django.db import models
from django.contrib.auth.models import User
from ingestion.models import SOURCE_CHOICES, RECORD_STATUS_CHOICES

class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='review_audit_logs')
    changed_at = models.DateTimeField(auto_now_add=True)
    
    record_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    record_id = models.UUIDField()
    
    old_status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES)
    new_status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES)
    reason = models.TextField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    def __str__(self):
        return f"{self.record_type} {self.record_id}: {self.old_status} -> {self.new_status}"


from django.contrib import admin
from .models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('record_type', 'record_id', 'old_status', 'new_status', 'changed_by', 'changed_at')
    list_filter = ('record_type', 'old_status', 'new_status')
    search_fields = ('record_id', 'reason')


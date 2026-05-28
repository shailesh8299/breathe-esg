import uuid
from review.models import AuditLog

def create_audit_log(user, record_type, record_id, old_status, new_status, reason, request):
    """
    Creates an AuditLog entry in the review database, extracting the remote IP address
    from the request context.
    """
    ip_address = None
    if request is not None:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0].strip()
        else:
            ip_address = request.META.get('REMOTE_ADDR')

    return AuditLog.objects.create(
        changed_by=user,
        record_type=record_type,
        record_id=record_id,
        old_status=old_status,
        new_status=new_status,
        reason=reason,
        ip_address=ip_address
    )

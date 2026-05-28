from datetime import datetime
from django.db import transaction
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage
from django.db.models import Sum

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication

from ingestion.models import SAPRecord, UtilityRecord, TravelRecord, IngestionRun
from review.serializers import UnifiedRowSerializer, IngestionRunSerializer
from review.utils import create_audit_log

class UnifiedRowListView(APIView):
    """
    ENDPOINT 1 - Unified paginated list of rows from SAP, Utility, and Travel models.
    Supports query filters for source, status, date_from, date_to, and page.
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        source = request.query_params.get('source')
        status_param = request.query_params.get('status')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        page_number = request.query_params.get('page', 1)

        # Parse date filters
        parsed_from = None
        parsed_to = None
        if date_from:
            try:
                parsed_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            except ValueError:
                pass
        if date_to:
            try:
                parsed_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            except ValueError:
                pass

        # Build initial querysets
        sap_qs = SAPRecord.objects.all()
        utility_qs = UtilityRecord.objects.all()
        travel_qs = TravelRecord.objects.all()

        # Apply status filters
        if status_param:
            sap_qs = sap_qs.filter(status=status_param)
            utility_qs = utility_qs.filter(status=status_param)
            travel_qs = travel_qs.filter(status=status_param)

        # Apply date filters (mapping to respective date fields)
        if parsed_from:
            sap_qs = sap_qs.filter(posting_date__gte=parsed_from)
            utility_qs = utility_qs.filter(billing_period_start__gte=parsed_from)
            travel_qs = travel_qs.filter(travel_date__gte=parsed_from)
        if parsed_to:
            sap_qs = sap_qs.filter(posting_date__lte=parsed_to)
            utility_qs = utility_qs.filter(billing_period_start__lte=parsed_to)
            travel_qs = travel_qs.filter(travel_date__lte=parsed_to)

        # Combine list based on source filter
        combined_list = []
        if source:
            source_upper = source.upper()
            if source_upper == 'SAP':
                combined_list = list(sap_qs)
            elif source_upper == 'UTILITY':
                combined_list = list(utility_qs)
            elif source_upper == 'TRAVEL':
                combined_list = list(travel_qs)
        else:
            combined_list = list(sap_qs) + list(utility_qs) + list(travel_qs)

        # Sort unified list by created_at desc
        combined_list.sort(key=lambda x: x.created_at, reverse=True)

        # Paginate (page size 50)
        paginator = Paginator(combined_list, 50)
        try:
            page_obj = paginator.page(page_number)
        except EmptyPage:
            return Response([], status=status.HTTP_200_OK)

        serializer = UnifiedRowSerializer(page_obj.object_list, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ApproveRowView(APIView):
    """
    ENDPOINT 2 - PATCH to approve a specific data row.
    Body requires: { "source_type": "SAP" or "UTILITY" or "TRAVEL" }
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, id, *args, **kwargs):
        source_type = request.data.get('source_type')
        if not source_type:
            return Response({"error": "source_type is required in body"}, status=status.HTTP_400_BAD_REQUEST)
        
        source_upper = source_type.upper()
        record = None

        try:
            if source_upper == 'SAP':
                record = SAPRecord.objects.get(id=id)
            elif source_upper == 'UTILITY':
                record = UtilityRecord.objects.get(id=id)
            elif source_upper == 'TRAVEL':
                record = TravelRecord.objects.get(id=id)
            else:
                return Response({"error": f"Invalid source_type: {source_type}"}, status=status.HTTP_400_BAD_REQUEST)
        except (SAPRecord.DoesNotExist, UtilityRecord.DoesNotExist, TravelRecord.DoesNotExist):
            return Response({"error": f"Record with ID {id} not found in {source_type}"}, status=status.HTTP_404_NOT_FOUND)

        old_status = record.status
        new_status = 'approved'

        # Execute status change and logging within an atomic transaction
        with transaction.atomic():
            record.status = new_status
            record.approved_by = request.user
            record.approved_at = timezone.now()
            record.save()

            # Record AuditLog
            create_audit_log(
                user=request.user,
                record_type=source_upper,
                record_id=record.id,
                old_status=old_status,
                new_status=new_status,
                reason="Analyst approved record.",
                request=request
            )

        serializer = UnifiedRowSerializer(record)
        return Response(serializer.data, status=status.HTTP_200_OK)


class FlagRowView(APIView):
    """
    ENDPOINT 3 - PATCH to flag a specific data row with a reason.
    Body requires: { "source_type": "SAP" or "UTILITY" or "TRAVEL", "reason": "string" }
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, id, *args, **kwargs):
        source_type = request.data.get('source_type')
        reason = request.data.get('reason')

        if not source_type:
            return Response({"error": "source_type is required in body"}, status=status.HTTP_400_BAD_REQUEST)
        if not reason:
            return Response({"error": "reason is required in body"}, status=status.HTTP_400_BAD_REQUEST)

        source_upper = source_type.upper()
        record = None

        try:
            if source_upper == 'SAP':
                record = SAPRecord.objects.get(id=id)
            elif source_upper == 'UTILITY':
                record = UtilityRecord.objects.get(id=id)
            elif source_upper == 'TRAVEL':
                record = TravelRecord.objects.get(id=id)
            else:
                return Response({"error": f"Invalid source_type: {source_type}"}, status=status.HTTP_400_BAD_REQUEST)
        except (SAPRecord.DoesNotExist, UtilityRecord.DoesNotExist, TravelRecord.DoesNotExist):
            return Response({"error": f"Record with ID {id} not found in {source_type}"}, status=status.HTTP_404_NOT_FOUND)

        old_status = record.status
        new_status = 'flagged'

        with transaction.atomic():
            record.status = new_status
            record.flagged_reason = reason
            record.save()

            # Record AuditLog
            create_audit_log(
                user=request.user,
                record_type=source_upper,
                record_id=record.id,
                old_status=old_status,
                new_status=new_status,
                reason=reason,
                request=request
            )

        serializer = UnifiedRowSerializer(record)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SuspiciousRowListView(APIView):
    """
    ENDPOINT 4 - GET all suspicious rows (status = 'flagged').
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        sap_qs = SAPRecord.objects.filter(status='flagged')
        utility_qs = UtilityRecord.objects.filter(status='flagged')
        travel_qs = TravelRecord.objects.filter(status='flagged')

        combined_list = list(sap_qs) + list(utility_qs) + list(travel_qs)
        combined_list.sort(key=lambda x: x.created_at, reverse=True)

        serializer = UnifiedRowSerializer(combined_list, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class IngestionRunListView(APIView):
    """
    ENDPOINT 5 - GET all IngestionRun records.
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        runs = IngestionRun.objects.all().order_by('-uploaded_at')
        serializer = IngestionRunSerializer(runs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DashboardSummaryView(APIView):
    """
    ENDPOINT 6 - GET comprehensive counts and summed emissions ($kgCO2e$) across all records.
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # 1. Row counts across all three models combined
        sap_count = SAPRecord.objects.count()
        utility_count = UtilityRecord.objects.count()
        travel_count = TravelRecord.objects.count()
        total = sap_count + utility_count + travel_count

        # 2. Status counts
        pending = (
            SAPRecord.objects.filter(status='pending').count() +
            UtilityRecord.objects.filter(status='pending').count() +
            TravelRecord.objects.filter(status='pending').count()
        )
        approved = (
            SAPRecord.objects.filter(status='approved').count() +
            UtilityRecord.objects.filter(status='approved').count() +
            TravelRecord.objects.filter(status='approved').count()
        )
        flagged = (
            SAPRecord.objects.filter(status='flagged').count() +
            UtilityRecord.objects.filter(status='flagged').count() +
            TravelRecord.objects.filter(status='flagged').count()
        )
        locked = (
            SAPRecord.objects.filter(status='locked').count() +
            UtilityRecord.objects.filter(status='locked').count() +
            TravelRecord.objects.filter(status='locked').count()
        )

        # 3. Scope categorization counts
        by_scope = {
            "scope_1": sap_count,
            "scope_2": utility_count,
            "scope_3": travel_count
        }

        # 4. Total kgco2e sum
        sap_sum = SAPRecord.objects.aggregate(total=Sum('kgco2e'))['total'] or 0.0
        utility_sum = UtilityRecord.objects.aggregate(total=Sum('kgco2e'))['total'] or 0.0
        travel_sum = TravelRecord.objects.aggregate(total=Sum('kgco2e'))['total'] or 0.0
        total_kgco2e = sap_sum + utility_sum + travel_sum

        return Response({
            "total": total,
            "pending": pending,
            "approved": approved,
            "flagged": flagged,
            "locked": locked,
            "by_scope": by_scope,
            "total_kgco2e": round(total_kgco2e, 2)
        }, status=status.HTTP_200_OK)

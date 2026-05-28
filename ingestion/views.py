from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication

from .serializers import SAPUploadSerializer, UtilityUploadSerializer, TravelUploadSerializer
from .services.sap_parser import SAPParser
from .services.utility_parser import UtilityParser
from .services.travel_parser import TravelParser
from .models import IngestionRun, Tenant

class SAPIngestView(APIView):
    """
    API view to ingest SAP records from an uploaded pipe-delimited flat file.
    Requires token authentication.
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        # Validate the uploaded file payload
        serializer = SAPUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = serializer.validated_data['file']

        # Get or create the default Tenant in the system
        tenant, _ = Tenant.objects.get_or_create(
            slug="default",
            defaults={"name": "Default Tenant"}
        )

        # STEP A - Create IngestionRun record at start with status='processing'
        ingestion_run = IngestionRun.objects.create(
            tenant=tenant,
            source_type='SAP',
            uploaded_filename=uploaded_file.name,
            uploaded_by=request.user,
            status='processing'
        )

        try:
            parser = SAPParser()
            result = parser.parse(uploaded_file, ingestion_run, tenant)
            return Response(result, status=status.HTTP_201_CREATED)
        except Exception as e:
            # Catch catastrophic parsing/server failures
            ingestion_run.status = 'failed'
            ingestion_run.save()
            return Response(
                {"error": f"Catastrophic ingestion failure: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UtilityIngestView(APIView):
    """
    API view to ingest Utility electricity records from an uploaded CSV file.
    Requires token authentication.
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        # Validate the uploaded file payload
        serializer = UtilityUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = serializer.validated_data['file']

        # Get or create the default Tenant in the system
        tenant, _ = Tenant.objects.get_or_create(
            slug="default",
            defaults={"name": "Default Tenant"}
        )

        # STEP A - Create IngestionRun record at start with status='processing'
        ingestion_run = IngestionRun.objects.create(
            tenant=tenant,
            source_type='UTILITY',
            uploaded_filename=uploaded_file.name,
            uploaded_by=request.user,
            status='processing'
        )

        try:
            parser = UtilityParser()
            result = parser.parse(uploaded_file, ingestion_run, tenant)
            return Response(result, status=status.HTTP_201_CREATED)
        except Exception as e:
            # Catch catastrophic parsing/server failures
            ingestion_run.status = 'failed'
            ingestion_run.save()
            return Response(
                {"error": f"Catastrophic ingestion failure: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TravelIngestView(APIView):
    """
    API view to ingest Corporate Travel records from an uploaded CSV file.
    Requires token authentication.
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        # Validate the uploaded file payload
        serializer = TravelUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = serializer.validated_data['file']

        # Get or create the default Tenant in the system
        tenant, _ = Tenant.objects.get_or_create(
            slug="default",
            defaults={"name": "Default Tenant"}
        )

        # STEP A - Create IngestionRun record at start with status='processing'
        ingestion_run = IngestionRun.objects.create(
            tenant=tenant,
            source_type='TRAVEL',
            uploaded_filename=uploaded_file.name,
            uploaded_by=request.user,
            status='processing'
        )

        try:
            parser = TravelParser()
            result = parser.parse(uploaded_file, ingestion_run, tenant)
            return Response(result, status=status.HTTP_201_CREATED)
        except Exception as e:
            # Catch catastrophic parsing/server failures
            ingestion_run.status = 'failed'
            ingestion_run.save()
            return Response(
                {"error": f"Catastrophic ingestion failure: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

from rest_framework import serializers

class SAPUploadSerializer(serializers.Serializer):
    """
    Serializer to validate the file upload payload for the SAP ingestion endpoint.
    """
    file = serializers.FileField(required=True, help_text="The pipe-delimited flat file containing SAP records.")


class UtilityUploadSerializer(serializers.Serializer):
    """
    Serializer to validate the file upload payload for the Utility electricity ingestion endpoint.
    """
    file = serializers.FileField(required=True, help_text="The CSV file containing Utility electricity consumption records.")


class TravelUploadSerializer(serializers.Serializer):
    """
    Serializer to validate the file upload payload for the Corporate Travel ingestion endpoint.
    """
    file = serializers.FileField(required=True, help_text="The CSV file containing Corporate Travel booking records.")

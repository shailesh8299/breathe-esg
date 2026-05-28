from django.urls import path
from .views import SAPIngestView, UtilityIngestView, TravelIngestView

app_name = 'ingestion'

urlpatterns = [
    path('sap/', SAPIngestView.as_view(), name='sap_ingest'),
    path('utility/', UtilityIngestView.as_view(), name='utility_ingest'),
    path('travel/', TravelIngestView.as_view(), name='travel_ingest'),
]

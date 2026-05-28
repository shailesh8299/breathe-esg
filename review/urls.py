from django.urls import path
from .views import (
    UnifiedRowListView, ApproveRowView, FlagRowView,
    SuspiciousRowListView, IngestionRunListView, DashboardSummaryView
)

app_name = 'review'

urlpatterns = [
    path('rows/', UnifiedRowListView.as_view(), name='rows_list'),
    path('rows/<uuid:id>/approve/', ApproveRowView.as_view(), name='row_approve'),
    path('rows/<uuid:id>/flag/', FlagRowView.as_view(), name='row_flag'),
    path('rows/suspicious/', SuspiciousRowListView.as_view(), name='rows_suspicious'),
    path('ingest-runs/', IngestionRunListView.as_view(), name='ingest_runs'),
    path('dashboard/summary/', DashboardSummaryView.as_view(), name='dashboard_summary'),
]

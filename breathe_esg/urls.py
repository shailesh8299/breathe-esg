from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from rest_framework.authtoken.views import obtain_auth_token

# Simple health check endpoint directly in root urls.py
# (No models required yet)
def health_check(request):
    return JsonResponse({"status": "ok"})

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API Endpoints
    path('api/health/', health_check, name='health_check'),
    
    # App routers
    path('api/ingest/', include('ingestion.urls')),
    path('api/review/', include('review.urls')),
    path('api/auth/login/', obtain_auth_token, name='api_token_auth'),
]

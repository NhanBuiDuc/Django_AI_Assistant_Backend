# ===================================
# backend/deeptalk/urls.py - DEEPTALK AI URLS (CLEANED)
# ===================================

from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from . import views

app_name = 'deeptalk'

urlpatterns = [
    # ===================================
    # JARVIS AI ENDPOINTS
    # ===================================
    
    # Main AI processing endpoint
    path('jarvis/process-task/', views.jarvis_process_task, name='jarvis_process_task'),
    
    # Health check for AI system
    path('jarvis/health/', views.jarvis_health_check, name='jarvis_health_check'),
    
    # ===================================
    # DEBUGGING (remove in production)
    # ===================================
    
    path('debug/auth/', views.debug_auth, name='debug_auth'),
]
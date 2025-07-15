# ===================================
# backend/gmail_oauth_project/urls.py (or your main project urls.py)
# ===================================

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Gmail Auth endpoints
    path('', include('gmail_auth.urls')),
    
    # DeepTalk API endpoints
    path('deeptalk/', include('deeptalk.urls')),
    
    path('task_manager/', include('task_manager.urls')),
]
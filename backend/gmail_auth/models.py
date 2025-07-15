
# gmail-oauth-project\backend\gmail_auth\models.py

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import json
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator


class GoogleToken(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    access_token = models.TextField()
    refresh_token = models.TextField()
    token_uri = models.URLField()
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)
    scopes = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)  # Token expiration
    is_active = models.BooleanField(default=True)  # Allow disabling tokens
    
    def __str__(self):
        return f"Google Token for {self.user.username}"
    
    def is_expired(self):
        """Check if the access token is expired"""
        if not self.expires_at:
            return False
        return timezone.now() >= self.expires_at
    
    def is_valid(self):
        """Check if token is valid and active"""
        return self.is_active and not self.is_expired()
    
    def refresh_if_needed(self):
        """Refresh token if needed"""
        if self.is_expired():
            # This would trigger a token refresh
            return True
        return False

class UserSession(models.Model):
    """Track user sessions for persistent login"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    session_key = models.CharField(max_length=255, unique=True)
    jwt_token = models.TextField()  # Store JWT token
    created_at = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    device_info = models.JSONField(default=dict, blank=True)  # Store device/browser info
    
    def __str__(self):
        return f"Session for {self.user.username} - {self.session_key[:8]}..."
    
    def is_expired(self):
        """Check if session is expired"""
        return timezone.now() >= self.expires_at
    
    def is_valid(self):
        """Check if session is valid and active"""
        return self.is_active and not self.is_expired()
    
    def extend_session(self, days=7):
        """Extend session expiration"""
        self.expires_at = timezone.now() + timedelta(days=days)
        self.save()
    
    @classmethod
    def cleanup_expired(cls):
        """Remove expired sessions"""
        expired_sessions = cls.objects.filter(expires_at__lt=timezone.now())
        count = expired_sessions.count()
        expired_sessions.delete()
        return count

class EmailSummary(models.Model):
    """Store AI-generated email summaries"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    summary_type = models.CharField(max_length=50)  # daily, weekly, unread, important, custom
    query = models.TextField(blank=True)  # Search query used
    summary_content = models.TextField()  # AI-generated summary
    email_count = models.IntegerField(default=0)  # Number of emails summarized
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)  # Additional data
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.summary_type} summary ({self.created_at.date()})"

class AIConfiguration(models.Model):
    """Store user's AI preferences"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    openai_api_key = models.TextField(blank=True)  # User's own API key (encrypted)
    preferred_model = models.CharField(max_length=50, default='gpt-3.5-turbo')
    summary_length = models.CharField(
        max_length=20, 
        choices=[('short', 'Short'), ('medium', 'Medium'), ('detailed', 'Detailed')],
        default='medium'
    )
    auto_summarize = models.BooleanField(default=False)  # Auto-generate daily summaries
    summary_schedule = models.CharField(
        max_length=20,
        choices=[('daily', 'Daily'), ('weekly', 'Weekly'), ('manual', 'Manual')],
        default='manual'
    )
    language = models.CharField(max_length=10, default='en')
    timezone = models.CharField(max_length=50, default='UTC')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"AI Config for {self.user.username}"


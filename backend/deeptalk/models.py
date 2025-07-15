# gmail-oauth-project\backend\deeptalk\models.py
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal

def default_list():
    """Helper function to provide default empty list for JSONField"""
    return []


def default_dict():
    """Helper function to provide default empty dict for JSONField"""
    return {}

class DeepTalkUser(models.Model):
    """Extended user profile for DeepTalk"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='deeptalk_profile')
    
    # Personal Information
    phone_number = models.CharField(max_length=20, blank=True)
    timezone = models.CharField(max_length=50, default='UTC')
    avatar_url = models.URLField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    occupation = models.CharField(max_length=200, blank=True)
    
    # Account Status
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    subscription_tier = models.CharField(
        max_length=20, 
        choices=[('free', 'Free'), ('premium', 'Premium'), ('pro', 'Pro')],
        default='free'
    )
    
    # Security and Login
    last_login_at = models.DateTimeField(null=True, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    
    # Audit Fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)  # Soft delete
    
    class Meta:
        db_table = 'deeptalk_users'
        
    def __str__(self):
        return f"{self.user.email} - {self.subscription_tier}"
    
    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save()

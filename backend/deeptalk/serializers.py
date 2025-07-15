# ===================================
# backend/deeptalk/serializers.py - COMPLETE DEEPTALK SERIALIZERS
# ===================================

from rest_framework import serializers
from django.utils import timezone
from .models import (
    DeepTalkUser
)
from task_manager.models import (
    Task, TaskCategory
)
# ===================================
# CORE MODEL SERIALIZERS
# ===================================

class DeepTalkUserSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = DeepTalkUser
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'phone_number', 'timezone', 'avatar_url', 'date_of_birth',
            'occupation', 'is_active', 'is_verified', 'subscription_tier',
            'last_login_at', 'email_verified_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

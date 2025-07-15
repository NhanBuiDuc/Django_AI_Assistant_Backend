from rest_framework import serializers
from .models import (
    Task, Schedule, TaskCategory, UserPreferences, TaskDependency, TaskLog, Reminder
)
from django.utils import timezone
import re

class SimpleTaskSerializer(serializers.ModelSerializer):
    """Simplified task serializer for lists and references"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = Task
        fields = [
            'id', 'name', 'status', 'priority', 'deadline', 'category_name',
            'completion_percentage', 'created_at'
        ]
        read_only_fields = ['id', 'category_name', 'created_at']


class TaskSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_icon = serializers.CharField(source='category.icon', read_only=True)
    category_color = serializers.CharField(source='category.color_hex', read_only=True)
    is_overdue = serializers.SerializerMethodField()
    time_until_deadline = serializers.SerializerMethodField()
    created_by = serializers.CharField(source='user.user.email', read_only=True)
    
    class Meta:
        model = Task
        fields = [
            'id', 'name', 'description', 'category', 'category_name', 
            'category_icon', 'category_color', 'tags', 'deadline', 
            'duration_minutes', 'specific_time', 'is_repeat', 'repeat_pattern',
            'repeat_frequency', 'repeat_days_of_week', 'repeat_end_date',
            'parent_task', 'priority', 'urgency', 'difficulty_level',
            'status', 'completion_percentage', 'estimated_effort_hours',
            'actual_time_spent_minutes', 'location', 'required_tools',
            'prerequisite_tasks', 'blocking_tasks',
            'ai_suggested', 'user_satisfaction_rating', 'ai_confidence_score',
            'is_overdue', 'time_until_deadline', 'created_by',
            'typed_in', 'created_at', 'updated_at', 'completed_at', 'cancelled_at'
        ]
        read_only_fields = [
            'id', 'is_overdue', 'time_until_deadline', 'created_by',
            'typed_in', 'created_at', 'updated_at'
        ]
    
    def get_is_overdue(self, obj):
        return obj.is_overdue()
    
    def get_time_until_deadline(self, obj):
        if obj.deadline and obj.status == 'pending':
            delta = obj.deadline - timezone.now()
            if delta.total_seconds() > 0:
                days = delta.days
                hours = delta.seconds // 3600
                return {
                    'days': days,
                    'hours': hours,
                    'total_hours': days * 24 + hours,
                    'is_overdue': False
                }
            else:
                return {
                    'days': 0,
                    'hours': 0,
                    'total_hours': 0,
                    'is_overdue': True
                }
        return None

class TaskListResponseSerializer(serializers.Serializer):
    """Serializer for task list API responses"""
    tasks = TaskSerializer(many=True)
    total_count = serializers.IntegerField()
    page = serializers.IntegerField(required=False)
    page_size = serializers.IntegerField(required=False)
    has_next = serializers.BooleanField(required=False)
    has_previous = serializers.BooleanField(required=False)
    
class ScheduleSerializer(serializers.ModelSerializer):
    task_name = serializers.CharField(source='task.name', read_only=True)
    task_category = serializers.CharField(source='task.category.name', read_only=True)
    duration_minutes = serializers.SerializerMethodField()
    
    class Meta:
        model = Schedule
        fields = [
            'id', 'task', 'task_name', 'task_category', 'scheduled_start_time',
            'scheduled_end_time', 'actual_start_time', 'actual_end_time',
            'schedule_type', 'is_flexible', 'buffer_time_minutes', 'status',
            'rescheduled_from', 'reschedule_reason', 'location', 'resources_needed',
            'calendar_event_id', 'ai_optimized', 'optimization_score',
            'conflict_resolution_applied', 'reminder_sent', 'notification_times',
            'duration_minutes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'duration_minutes', 'created_at', 'updated_at']
    
    def get_duration_minutes(self, obj):
        if obj.scheduled_start_time and obj.scheduled_end_time:
            delta = obj.scheduled_end_time - obj.scheduled_start_time
            return int(delta.total_seconds() / 60)
        return None
    
class TaskCategorySerializer(serializers.ModelSerializer):
    task_count = serializers.SerializerMethodField()
    
    class Meta:
        model = TaskCategory
        fields = [
            'id', 'name', 'color_hex', 'icon', 'default_duration',
            'default_priority', 'is_system_category', 'task_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'task_count']
    
    def get_task_count(self, obj):
        return obj.tasks.filter(deleted_at__isnull=True).count()

class UserPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreferences
        fields = [
            'id', 'work_start_time', 'work_end_time', 'preferred_work_days',
            'lunch_break_duration', 'preferred_break_duration', 'default_task_duration',
            'max_daily_tasks', 'preferred_task_categories', 'avoid_back_to_back_meetings',
            'enable_email_notifications', 'enable_push_notifications', 
            'enable_sms_notifications', 'reminder_lead_time', 'ai_suggestion_frequency',
            'auto_schedule_low_priority', 'learning_from_behavior', 'most_productive_hours',
            'least_productive_hours', 'preferred_task_grouping', 'exercise_reminder',
            'hydration_reminder', 'screen_break_reminder', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class TaskDependencySerializer(serializers.ModelSerializer):
    predecessor_name = serializers.CharField(source='predecessor_task.name', read_only=True)
    successor_name = serializers.CharField(source='successor_task.name', read_only=True)
    
    class Meta:
        model = TaskDependency
        fields = [
            'id', 'predecessor_task', 'successor_task', 'predecessor_name',
            'successor_name', 'dependency_type', 'lag_time_minutes', 'created_at'
        ]
        read_only_fields = ['id', 'predecessor_name', 'successor_name', 'created_at']

class TaskLogSerializer(serializers.ModelSerializer):
    task_name = serializers.CharField(source='task.name', read_only=True)
    user_email = serializers.CharField(source='user.user.email', read_only=True)
    
    class Meta:
        model = TaskLog
        fields = [
            'id', 'task', 'task_name', 'user_email', 'action', 'previous_values',
            'new_values', 'action_reason', 'triggered_by', 'ip_address',
            'user_agent', 'created_at'
        ]
        read_only_fields = ['id', 'task_name', 'user_email', 'created_at']

class ReminderSerializer(serializers.ModelSerializer):
    task_name = serializers.CharField(source='task.name', read_only=True)
    schedule_info = serializers.SerializerMethodField()
    
    class Meta:
        model = Reminder
        fields = [
            'id', 'task', 'task_name', 'schedule', 'schedule_info', 'reminder_type',
            'message', 'reminder_time', 'delivery_method', 'is_sent', 'sent_at',
            'delivery_status', 'is_recurring', 'recurrence_pattern',
            'next_reminder_time', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'task_name', 'schedule_info', 'created_at', 'updated_at']
    
    def get_schedule_info(self, obj):
        if obj.schedule:
            return {
                'scheduled_start_time': obj.schedule.scheduled_start_time,
                'scheduled_end_time': obj.schedule.scheduled_end_time,
                'status': obj.schedule.status
            }
        return None

# ===================================
# SPECIALIZED SERIALIZERS
# ===================================


class TaskCreateSerializer(serializers.ModelSerializer):
    """Serializer specifically for task creation"""
    
    class Meta:
        model = Task
        fields = [
            'name', 'description', 'category', 'tags', 'deadline',
            'duration_minutes', 'specific_time', 'priority', 'urgency',
            'difficulty_level', 'location', 'required_tools',
            'estimated_effort_hours'
        ]
    
    def validate_deadline(self, value):
        """Validate that deadline is in the future"""
        if value and value <= timezone.now():
            raise serializers.ValidationError("Deadline must be in the future")
        return value
    
    def validate_priority(self, value):
        """Validate priority is within range"""
        if value < 1 or value > 5:
            raise serializers.ValidationError("Priority must be between 1 and 5")
        return value

class TaskUpdateSerializer(serializers.ModelSerializer):
    """Serializer specifically for task updates"""
    
    class Meta:
        model = Task
        fields = [
            'name', 'description', 'category', 'tags', 'deadline',
            'duration_minutes', 'specific_time', 'priority', 'urgency',
            'difficulty_level', 'status', 'completion_percentage',
            'location', 'required_tools', 'estimated_effort_hours',
            'actual_time_spent_minutes'
        ]
    
    def validate_completion_percentage(self, value):
        """Validate completion percentage is within range"""
        if value < 0 or value > 100:
            raise serializers.ValidationError("Completion percentage must be between 0 and 100")
        return value

class CategoryCreateSerializer(serializers.ModelSerializer):
    """Serializer specifically for category creation"""
    
    class Meta:
        model = TaskCategory
        fields = ['name', 'color_hex', 'icon', 'default_duration', 'default_priority']
    
    def validate_color_hex(self, value):
        """Validate hex color format"""
        if not re.match(r'^#[0-9A-Fa-f]{6}$', value):
            raise serializers.ValidationError("Color must be a valid hex color (e.g., #FF0000)")
        return value

# ===================================
# STATISTICS AND SUMMARY SERIALIZERS
# ===================================

class TaskSummarySerializer(serializers.Serializer):
    """Serializer for task summary statistics"""
    total = serializers.IntegerField()
    pending = serializers.IntegerField()
    completed = serializers.IntegerField()
    in_progress = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    overdue = serializers.IntegerField()
    completion_rate = serializers.FloatField()
    category_breakdown = serializers.ListField()
    priority_breakdown = serializers.DictField()
    recent_activity = serializers.DictField()

class ProductivityInsightsSerializer(serializers.Serializer):
    """Serializer for productivity insights"""
    period_days = serializers.IntegerField()
    tasks_created = serializers.IntegerField()
    tasks_completed = serializers.IntegerField()
    completion_rate = serializers.FloatField()
    average_completion_time = serializers.FloatField(allow_null=True)
    most_productive_day = serializers.CharField(allow_null=True)
    preferred_categories = serializers.ListField()
    daily_completion_trend = serializers.DictField()

class UserStatsSerializer(serializers.Serializer):
    """Serializer for user statistics"""
    total_tasks = serializers.IntegerField()
    completed_tasks = serializers.IntegerField()
    pending_tasks = serializers.IntegerField()
    overdue_tasks = serializers.IntegerField()
    completion_rate = serializers.FloatField()
    categories_count = serializers.IntegerField()
    average_task_completion_time = serializers.FloatField(allow_null=True)
    most_active_day = serializers.CharField(allow_null=True)
    productivity_score = serializers.FloatField(allow_null=True)

# ===================================
# BULK OPERATION SERIALIZERS
# ===================================

class BulkTaskUpdateSerializer(serializers.Serializer):
    """Serializer for bulk task updates"""
    task_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1
    )
    updates = serializers.DictField()

class BulkTaskDeleteSerializer(serializers.Serializer):
    """Serializer for bulk task deletion"""
    task_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1
    )

# ===================================
# SEARCH AND FILTER SERIALIZERS
# ===================================

class TaskSearchSerializer(serializers.Serializer):
    """Serializer for task search parameters"""
    q = serializers.CharField(required=True, min_length=1)
    status = serializers.ChoiceField(
        choices=['pending', 'in_progress', 'completed', 'cancelled', 'on_hold'],
        required=False
    )
    priority = serializers.IntegerField(min_value=1, max_value=5, required=False)
    category = serializers.CharField(required=False)

class TaskFilterSerializer(serializers.Serializer):
    """Serializer for task filtering parameters"""
    status = serializers.MultipleChoiceField(
        choices=['pending', 'in_progress', 'completed', 'cancelled', 'on_hold'],
        required=False
    )
    priority = serializers.MultipleChoiceField(
        choices=[1, 2, 3, 4, 5],
        required=False
    )
    category = serializers.ListField(
        child=serializers.UUIDField(),
        required=False
    )
    deadline_start = serializers.DateTimeField(required=False)
    deadline_end = serializers.DateTimeField(required=False)
    created_start = serializers.DateTimeField(required=False)
    created_end = serializers.DateTimeField(required=False)
    overdue_only = serializers.BooleanField(required=False, default=False)
    has_deadline = serializers.BooleanField(required=False)
    
    def validate(self, data):
        """Validate date ranges"""
        if 'deadline_start' in data and 'deadline_end' in data:
            if data['deadline_start'] >= data['deadline_end']:
                raise serializers.ValidationError(
                    "deadline_start must be before deadline_end"
                )
        
        if 'created_start' in data and 'created_end' in data:
            if data['created_start'] >= data['created_end']:
                raise serializers.ValidationError(
                    "created_start must be before created_end"
                )
        
        return data

# ===================================
# API RESPONSE SERIALIZERS
# ===================================


class CategoryListResponseSerializer(serializers.Serializer):
    """Serializer for category list API responses"""
    categories = TaskCategorySerializer(many=True)
    total_count = serializers.IntegerField()

class TaskStatsResponseSerializer(serializers.Serializer):
    """Serializer for task statistics API responses"""
    total = serializers.IntegerField()
    pending = serializers.IntegerField()
    completed = serializers.IntegerField()
    in_progress = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    overdue = serializers.IntegerField()
    completion_rate = serializers.FloatField()
    category_breakdown = serializers.ListField()
    priority_breakdown = serializers.DictField()
    recent_activity = serializers.DictField()

class ErrorResponseSerializer(serializers.Serializer):
    """Serializer for error responses"""
    error = serializers.CharField()
    details = serializers.DictField(required=False)
    timestamp = serializers.DateTimeField(required=False)

class SuccessResponseSerializer(serializers.Serializer):
    """Serializer for success responses"""
    message = serializers.CharField()
    data = serializers.DictField(required=False)

# ===================================
# PAGINATION SERIALIZERS
# ===================================

class PaginationSerializer(serializers.Serializer):
    """Serializer for pagination metadata"""
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = serializers.ListField()

class PageNumberPaginationSerializer(serializers.Serializer):
    """Serializer for page number pagination"""
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, default=20)

# ===================================
# EXPORT SERIALIZERS
# ===================================

class TaskExportSerializer(serializers.ModelSerializer):
    """Serializer for task data export"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    user_email = serializers.CharField(source='user.user.email', read_only=True)
    
    class Meta:
        model = Task
        fields = [
            'id', 'name', 'description', 'category_name', 'tags',
            'status', 'priority', 'urgency', 'difficulty_level',
            'deadline', 'completion_percentage', 'location',
            'user_email', 'created_at', 'updated_at', 'completed_at'
        ]

class CategoryExportSerializer(serializers.ModelSerializer):
    """Serializer for category data export"""
    task_count = serializers.SerializerMethodField()
    user_email = serializers.CharField(source='user.user.email', read_only=True)
    
    class Meta:
        model = TaskCategory
        fields = [
            'id', 'name', 'color_hex', 'icon', 'is_system_category',
            'task_count', 'user_email', 'created_at'
        ]
    
    def get_task_count(self, obj):
        return obj.tasks.filter(deleted_at__isnull=True).count()

# ===================================
# VALIDATION SERIALIZERS
# ===================================

class TaskValidationSerializer(serializers.Serializer):
    """Serializer for task validation"""
    name = serializers.CharField(max_length=255, required=True)
    deadline = serializers.DateTimeField(required=False)
    priority = serializers.IntegerField(min_value=1, max_value=5, required=False)
    
    def validate_name(self, value):
        """Validate task name"""
        if len(value.strip()) < 3:
            raise serializers.ValidationError("Task name must be at least 3 characters long")
        return value.strip()
    
    def validate_deadline(self, value):
        """Validate deadline"""
        if value and value <= timezone.now():
            raise serializers.ValidationError("Deadline must be in the future")
        return value

class CategoryValidationSerializer(serializers.Serializer):
    """Serializer for category validation"""
    name = serializers.CharField(max_length=100, required=True)
    color_hex = serializers.CharField(max_length=7, required=False)
    
    def validate_name(self, value):
        """Validate category name"""
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Category name must be at least 2 characters long")
        return value.strip()
    
    def validate_color_hex(self, value):
        """Validate hex color"""
        if value and not re.match(r'^#[0-9A-Fa-f]{6}$', value):
            raise serializers.ValidationError("Color must be a valid hex color (e.g., #FF0000)")
        return value
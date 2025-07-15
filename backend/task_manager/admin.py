from django.contrib import admin
from .models import (
    Task, TaskCategory, UserPreferences, TaskDependency, 
    TaskLog, Reminder, Schedule, TimeBlock
)

@admin.register(TaskCategory)
class TaskCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'color_hex', 'icon', 'is_system_category', 'created_at']
    list_filter = ['is_system_category', 'created_at']
    search_fields = ['name', 'user__user__email']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'status', 'priority', 'deadline', 'category', 'ai_suggested', 'created_at']
    list_filter = ['status', 'priority', 'ai_suggested', 'category', 'created_at']
    search_fields = ['name', 'description', 'user__user__email']
    readonly_fields = ['created_at', 'updated_at', 'completed_at', 'cancelled_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'user', 'category', 'tags')
        }),
        ('Timing', {
            'fields': ('deadline', 'duration_minutes', 'specific_time')
        }),
        ('Priority & Status', {
            'fields': ('priority', 'urgency', 'status', 'completion_percentage')
        }),
        ('AI Features', {
            'fields': ('ai_suggested', 'ai_confidence_score', 'user_satisfaction_rating'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'completed_at', 'cancelled_at'),
            'classes': ('collapse',)
        })
    )

@admin.register(UserPreferences)
class UserPreferencesAdmin(admin.ModelAdmin):
    list_display = ['user', 'work_start_time', 'work_end_time', 'default_task_duration', 'ai_suggestion_frequency']
    list_filter = ['ai_suggestion_frequency', 'auto_schedule_low_priority']
    search_fields = ['user__user__email']

@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ['task', 'scheduled_start_time', 'scheduled_end_time', 'status', 'schedule_type']
    list_filter = ['status', 'schedule_type', 'ai_optimized']
    search_fields = ['task__name', 'task__user__user__email']
    date_hierarchy = 'scheduled_start_time'

@admin.register(TaskDependency)
class TaskDependencyAdmin(admin.ModelAdmin):
    list_display = ['predecessor_task', 'successor_task', 'dependency_type', 'lag_time_minutes']
    list_filter = ['dependency_type']
    search_fields = ['predecessor_task__name', 'successor_task__name']

@admin.register(TaskLog)
class TaskLogAdmin(admin.ModelAdmin):
    list_display = ['task', 'action', 'triggered_by', 'user', 'created_at']
    list_filter = ['action', 'triggered_by', 'created_at']
    search_fields = ['task__name', 'user__user__email']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'

@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ['user', 'task', 'reminder_type', 'reminder_time', 'delivery_method', 'is_sent']
    list_filter = ['reminder_type', 'delivery_method', 'is_sent', 'delivery_status']
    search_fields = ['user__user__email', 'task__name', 'message']
    date_hierarchy = 'reminder_time'

@admin.register(TimeBlock)
class TimeBlockAdmin(admin.ModelAdmin):
    list_display = ['user', 'start_time', 'end_time', 'block_type', 'status', 'duration_minutes']
    list_filter = ['block_type', 'status', 'can_be_split']
    search_fields = ['user__user__email']
    date_hierarchy = 'start_time'
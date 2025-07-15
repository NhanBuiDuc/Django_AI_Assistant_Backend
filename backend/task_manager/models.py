from django.db import models
import uuid
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal

# Import DeepTalkUser from the correct location
try:
    from deeptalk.models import DeepTalkUser
except ImportError:
    # Fallback if deeptalk app is not available
    from django.contrib.auth.models import User as DeepTalkUser

def default_list():
    """Helper function to provide default empty list for JSONField"""
    return []

class TaskCategory(models.Model):
    """Categories for organizing tasks"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(DeepTalkUser, on_delete=models.CASCADE, related_name='task_categories', null=True, blank=True)
    
    name = models.CharField(max_length=100)
    color_hex = models.CharField(max_length=7, default='#3498db')  # Hex color code
    icon = models.CharField(max_length=50, blank=True)  # Icon identifier
    default_duration = models.IntegerField(null=True, blank=True)  # Minutes
    default_priority = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True, blank=True
    )
    is_system_category = models.BooleanField(default=False)  # Pre-defined categories
    
    # ADD THESE NEW FIELDS FOR EDF/HPF SUPPORT
    category_weight = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal('1.00'))  # HPF multiplier
    can_be_split_default = models.BooleanField(default=True)  # Default splitting behavior
    requires_focus_time = models.BooleanField(default=False)  # Needs uninterrupted time
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'task_categories'
        app_label = 'task_manager'
        
    def __str__(self):
        user_email = self.user.user.email if hasattr(self.user, 'user') else str(self.user) if self.user else 'System'
        return f"{self.name} ({user_email})"
    
class Task(models.Model):
    """Enhanced task entity with AI features"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('on_hold', 'On Hold'),
    ]
    
    REPEAT_PATTERNS = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
        ('custom', 'Custom'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(DeepTalkUser, on_delete=models.CASCADE, related_name='tasks')
    
    # Basic Information
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.ForeignKey(TaskCategory, on_delete=models.SET_NULL, null=True, blank=True)
    tags = models.JSONField(default=default_list, blank=True)
    
    # Timing Information
    deadline = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(null=True, blank=True)
    specific_time = models.DateTimeField(null=True, blank=True)
    
    # ADD THESE NEW DURATION FIELDS FOR EDF/HPF
    estimated_duration_minutes = models.IntegerField(default=60)  # Primary duration field
    minimum_duration_minutes = models.IntegerField(null=True, blank=True)  # Min acceptable time
    maximum_duration_minutes = models.IntegerField(null=True, blank=True)  # Max acceptable time
    
    # ADD THESE NEW PRIORITY FIELDS FOR HPF
    base_priority = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        default=3
    )
    urgency_multiplier = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal('1.00'))
    
    # ADD THESE NEW SCHEDULING CONSTRAINT FIELDS
    can_be_split = models.BooleanField(default=True)  # Can be broken into chunks
    requires_consecutive_time = models.BooleanField(default=False)  # Must be done in one block
    preferred_time_of_day = models.JSONField(default=default_list, blank=True)  # Preferred times
    avoid_time_of_day = models.JSONField(default=default_list, blank=True)  # Times to avoid
    
    # ADD THESE NEW DEADLINE FIELDS FOR EDF
    preferred_completion_time = models.DateTimeField(null=True, blank=True)  # Soft deadline
    deadline_flexibility_minutes = models.IntegerField(default=0)  # How much deadline can shift
    
    # Repetition Settings
    is_repeat = models.BooleanField(default=False)
    repeat_pattern = models.CharField(max_length=50, choices=REPEAT_PATTERNS, blank=True)
    repeat_frequency = models.IntegerField(default=1)  # Every N days/weeks/months
    repeat_days_of_week = models.JSONField(default=default_list, blank=True)
    repeat_end_date = models.DateTimeField(null=True, blank=True)
    parent_task = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='child_tasks')
    
    # Priority and Urgency (1-5 scale, 1 = highest) - KEEP FOR BACKWARD COMPATIBILITY
    priority = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        default=3
    )
    urgency = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        default=3
    )
    difficulty_level = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        default=3
    )
    
    # Progress Tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    completion_percentage = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=0
    )
    estimated_effort_hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    actual_time_spent_minutes = models.IntegerField(default=0)
    
    # Location and Context
    location = models.CharField(max_length=255, blank=True)
    required_tools = models.JSONField(default=default_list, blank=True)
    
    # Dependencies and Relationships
    prerequisite_tasks = models.JSONField(default=default_list, blank=True)
    blocking_tasks = models.JSONField(default=default_list, blank=True)
    
    # AI-Enhanced Fields
    ai_suggested = models.BooleanField(default=False)
    user_satisfaction_rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True, blank=True
    )
    ai_confidence_score = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    
    # Audit and Metadata
    typed_in = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)  # Soft delete
    
    class Meta:
        db_table = 'tasks'
        app_label = 'task_manager'
        ordering = ['-created_at']
        # ADD THESE INDEXES FOR EDF/HPF PERFORMANCE
        indexes = [
            models.Index(fields=['deadline', 'base_priority'], name='idx_tasks_deadline_priority'),
            models.Index(fields=['user', 'status'], name='idx_tasks_user_status'),
            models.Index(fields=['estimated_duration_minutes', 'can_be_split'], name='idx_tasks_duration_split'),
        ]
        
    def __str__(self):
        return f"{self.name} ({self.status})"
    
    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save()
    
    def mark_completed(self):
        self.status = 'completed'
        self.completion_percentage = 100
        self.completed_at = timezone.now()
        self.save()
    
    def is_overdue(self):
        if self.deadline and self.status == 'pending':
            return timezone.now() > self.deadline
        return False
    
    # ADD THIS NEW PROPERTY FOR HPF ALGORITHM
    @property
    def calculated_priority(self):
        """Calculate dynamic priority for HPF algorithm"""
        base = float(self.base_priority)
        urgency = float(self.urgency_multiplier)
        
        # Deadline proximity factor
        deadline_factor = 1.0
        if self.deadline:
            time_until_deadline = self.deadline - timezone.now()
            hours_until_deadline = time_until_deadline.total_seconds() / 3600
            
            if hours_until_deadline <= 0:
                deadline_factor = 5.0  # Overdue
            elif hours_until_deadline <= 24:
                deadline_factor = 3.0  # Due today
            elif hours_until_deadline <= 168:  # 1 week
                deadline_factor = 2.0
            else:
                deadline_factor = 1.0
        
        # Category weight
        category_weight = 1.0
        if self.category and hasattr(self.category, 'category_weight'):
            category_weight = float(self.category.category_weight)
        
        return base * urgency * deadline_factor * category_weight
    
class Schedule(models.Model):
    """Scheduling information for tasks"""
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('skipped', 'Skipped'),
        ('rescheduled', 'Rescheduled'),
    ]
    
    SCHEDULE_TYPES = [
        ('user_planned', 'User Planned'),
        ('ai_suggested', 'AI Suggested'),
        ('auto_generated', 'Auto Generated'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(DeepTalkUser, on_delete=models.CASCADE, related_name='schedules')
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='schedules')

    # Scheduling Details
    scheduled_start_time = models.DateTimeField()
    scheduled_end_time = models.DateTimeField()
    actual_start_time = models.DateTimeField(null=True, blank=True)
    actual_end_time = models.DateTimeField(null=True, blank=True)
    
    # Schedule Metadata
    schedule_type = models.CharField(max_length=20, choices=SCHEDULE_TYPES, default='user_planned')
    is_flexible = models.BooleanField(default=True)
    buffer_time_minutes = models.IntegerField(default=0)
    
    # Status and Tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    rescheduled_from = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='rescheduled_to')
    reschedule_reason = models.CharField(max_length=255, blank=True)
    
    # Location and Resources
    location = models.CharField(max_length=255, blank=True)
    resources_needed = models.JSONField(default=default_list, blank=True)
    calendar_event_id = models.CharField(max_length=255, blank=True)
    
    # AI and Optimization
    ai_optimized = models.BooleanField(default=False)
    optimization_score = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    conflict_resolution_applied = models.BooleanField(default=False)
    
    # Notifications
    reminder_sent = models.BooleanField(default=False)
    notification_times = models.JSONField(default=default_list, blank=True)
    
    # Audit Fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'schedules'
        app_label = 'task_manager'
        ordering = ['scheduled_start_time']
        
    def __str__(self):
        return f"{self.task.name} - {self.scheduled_start_time}"
    
class UserPreferences(models.Model):
    """User preferences for scheduling and AI behavior"""
    SUGGESTION_FREQUENCY_CHOICES = [
        ('low', 'Low'),
        ('moderate', 'Moderate'),
        ('high', 'High'),
    ]
    
    GROUPING_CHOICES = [
        ('by_category', 'By Category'),
        ('by_priority', 'By Priority'),
        ('mixed', 'Mixed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(DeepTalkUser, on_delete=models.CASCADE, related_name='preferences')
    
    # Working Hours and Schedule Preferences
    work_start_time = models.TimeField(default='09:00:00')
    work_end_time = models.TimeField(default='17:00:00')
    preferred_work_days = models.JSONField(default=default_list, blank=True)
    lunch_break_duration = models.IntegerField(default=60)  # minutes
    preferred_break_duration = models.IntegerField(default=15)  # minutes
    
    # Task and Scheduling Preferences
    default_task_duration = models.IntegerField(default=60)  # minutes
    max_daily_tasks = models.IntegerField(default=10)
    preferred_task_categories = models.JSONField(default=default_list, blank=True)
    avoid_back_to_back_meetings = models.BooleanField(default=True)
    
    # Notification Preferences
    enable_email_notifications = models.BooleanField(default=True)
    enable_push_notifications = models.BooleanField(default=True)
    enable_sms_notifications = models.BooleanField(default=False)
    reminder_lead_time = models.IntegerField(default=15)  # minutes before task
    
    # AI Behavior Preferences
    ai_suggestion_frequency = models.CharField(
        max_length=20, choices=SUGGESTION_FREQUENCY_CHOICES, default='moderate'
    )
    auto_schedule_low_priority = models.BooleanField(default=False)
    learning_from_behavior = models.BooleanField(default=True)
    
    # Personal Productivity Patterns
    most_productive_hours = models.JSONField(default=default_list, blank=True)
    least_productive_hours = models.JSONField(default=default_list, blank=True)
    preferred_task_grouping = models.CharField(max_length=20, choices=GROUPING_CHOICES, default='by_category')
    
    # Health and Wellness
    exercise_reminder = models.BooleanField(default=True)
    hydration_reminder = models.BooleanField(default=False)
    screen_break_reminder = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_preferences'
        app_label = 'task_manager'
        
    def __str__(self):
        user_email = self.user.user.email if hasattr(self.user, 'user') else str(self.user)
        return f"Preferences for {user_email}"

class TaskDependency(models.Model):
    """Dependencies between tasks"""
    DEPENDENCY_TYPES = [
        ('finish_to_start', 'Finish to Start'),
        ('start_to_start', 'Start to Start'),
        ('finish_to_finish', 'Finish to Finish'),
        ('start_to_finish', 'Start to Finish'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    predecessor_task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='successor_dependencies')
    successor_task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='predecessor_dependencies')
    dependency_type = models.CharField(max_length=20, choices=DEPENDENCY_TYPES, default='finish_to_start')
    lag_time_minutes = models.IntegerField(default=0)  # Minimum time between tasks
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'task_dependencies'
        app_label = 'task_manager'
        unique_together = ['predecessor_task', 'successor_task']
        
    def __str__(self):
        return f"{self.predecessor_task.name} -> {self.successor_task.name}"

class TaskLog(models.Model):
    """Audit log for task changes"""
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('updated', 'Updated'),
        ('started', 'Started'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('deleted', 'Deleted'),
    ]
    
    TRIGGERED_BY_CHOICES = [
        ('user', 'User'),
        ('system', 'System'),
        ('ai', 'AI'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey('Task', on_delete=models.CASCADE, related_name='logs')
    user = models.ForeignKey(DeepTalkUser, on_delete=models.CASCADE, related_name='task_logs', null=True, blank=True)

    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    previous_values = models.JSONField(null=True, blank=True)  # Store previous state
    new_values = models.JSONField(null=True, blank=True)  # Store new state
    action_reason = models.CharField(max_length=255, blank=True)
    
    # Context
    triggered_by = models.CharField(max_length=20, choices=TRIGGERED_BY_CHOICES, default='user')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'task_logs'
        app_label = 'task_manager'
        ordering = ['-created_at']
        
    def __str__(self):
        user_email = self.user.user.email if hasattr(self.user, 'user') else str(self.user) if self.user else 'System'
        return f"{self.task.name} - {self.action} by {user_email}"

class Reminder(models.Model):
    """Reminders for tasks and schedules"""
    REMINDER_TYPES = [
        ('task_deadline', 'Task Deadline'),
        ('schedule_start', 'Schedule Start'),
        ('custom', 'Custom'),
    ]
    
    DELIVERY_METHODS = [
        ('email', 'Email'),
        ('push', 'Push Notification'),
        ('sms', 'SMS'),
        ('in_app', 'In App'),
    ]
    
    DELIVERY_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(DeepTalkUser, on_delete=models.CASCADE, related_name='reminders')
    task = models.ForeignKey('Task', on_delete=models.CASCADE, null=True, blank=True, related_name='reminders')
    schedule = models.ForeignKey('Schedule', on_delete=models.CASCADE, null=True, blank=True, related_name='reminders')
    
    # Reminder Details
    reminder_type = models.CharField(max_length=20, choices=REMINDER_TYPES)
    message = models.TextField()
    reminder_time = models.DateTimeField()
    
    # Delivery Settings
    delivery_method = models.CharField(max_length=20, choices=DELIVERY_METHODS)
    is_sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivery_status = models.CharField(max_length=20, choices=DELIVERY_STATUS_CHOICES, default='pending')
    
    # Recurring Reminders
    is_recurring = models.BooleanField(default=False)
    recurrence_pattern = models.CharField(max_length=50, blank=True)
    next_reminder_time = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'reminders'
        app_label = 'task_manager'
        ordering = ['reminder_time']
        
    def __str__(self):
        user_email = self.user.user.email if hasattr(self.user, 'user') else str(self.user)
        return f"Reminder for {user_email} at {self.reminder_time}"
    
# ADD THIS NEW MODEL FOR TIME BLOCK MANAGEMENT
class TimeBlock(models.Model):
    """Time blocks for scheduling algorithms"""
    BLOCK_TYPES = [
        ('available', 'Available'),
        ('busy', 'Busy'),
        ('break', 'Break'),
        ('blocked', 'Blocked'),
    ]
    
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('reserved', 'Reserved'),
        ('occupied', 'Occupied'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(DeepTalkUser, on_delete=models.CASCADE, related_name='time_blocks')
    
    # Time Block Definition
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    
    # Block Type and Status
    block_type = models.CharField(max_length=20, choices=BLOCK_TYPES, default='available')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    
    # Scheduling Constraints
    can_be_split = models.BooleanField(default=True)
    min_task_duration_minutes = models.IntegerField(null=True, blank=True)
    max_task_duration_minutes = models.IntegerField(null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'time_blocks'
        app_label = 'task_manager'
        ordering = ['start_time']
        indexes = [
            models.Index(fields=['user', 'start_time', 'end_time'], name='idx_timeblocks_user_time'),
            models.Index(fields=['status', 'block_type'], name='idx_timeblocks_status_type'),
        ]
        
    def __str__(self):
        return f"{self.block_type} block: {self.start_time} - {self.end_time}"
    
    @property
    def duration_minutes(self):
        """Calculate duration in minutes"""
        if self.start_time and self.end_time:
            return int((self.end_time - self.start_time).total_seconds() / 60)
        return 0
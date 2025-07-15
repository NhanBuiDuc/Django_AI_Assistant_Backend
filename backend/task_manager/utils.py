# task_manager/utils.py - Alternative if you want complete separation

import logging
from django.utils import timezone

logger = logging.getLogger(__name__)

def create_task_log(task, user, action, **kwargs):
    """
    Create a task log entry for audit purposes - LOCAL VERSION
    """
    try:
        from .models import TaskLog
        
        # Extract optional parameters
        previous_values = kwargs.get('previous_values')
        new_values = kwargs.get('new_values')
        action_reason = kwargs.get('action_reason', '')
        triggered_by = kwargs.get('triggered_by', 'user')
        ip_address = kwargs.get('ip_address')
        user_agent = kwargs.get('user_agent', '')
        
        # Create the log entry
        log_entry = TaskLog.objects.create(
            task=task,
            user=user,
            action=action,
            previous_values=previous_values,
            new_values=new_values,
            action_reason=action_reason,
            triggered_by=triggered_by,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        logger.debug(f"Created task log: {task.name} - {action} by {user}")
        return log_entry
        
    except Exception as e:
        logger.error(f"Error creating task log for task {task.id if task else 'unknown'}: {type(e).__name__}: {e}")
        return None


def extract_ip_address(request):
    """
    Extract IP address from request, handling proxies
    """
    try:
        # Try to get real IP from common proxy headers
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
            return ip
        
        # Fallback to standard remote address
        return request.META.get('REMOTE_ADDR', 'unknown')
    
    except Exception as e:
        logger.error(f"Error extracting IP address: {type(e).__name__}: {e}")
        return 'unknown'


def extract_user_agent(request):
    """
    Extract user agent from request
    """
    try:
        return request.META.get('HTTP_USER_AGENT', 'unknown')
    except Exception as e:
        logger.error(f"Error extracting user agent: {type(e).__name__}: {e}")
        return 'unknown'
from deeptalk.utils import get_deeptalk_user_from_request
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from .models import (
    Task,
    TaskCategory, UserPreferences, TaskDependency, TaskLog, Reminder
)
from .serializers import (
    TaskSerializer, TaskCategorySerializer, 
    UserPreferencesSerializer
)
from django.utils import timezone
from django.db.models import Q, Count
from datetime import timedelta
from .utils import create_task_log
# ===================================
import logging
logger = logging.getLogger(__name__)
@csrf_exempt
@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def tasks_list_create(request):
    """List tasks or create new task - SIMPLIFIED"""
    
    deeptalk_user = get_deeptalk_user_from_request(request)
    
    if not deeptalk_user:
        return Response({
            'error': 'Authentication required',
            'message': 'Please sign in to manage your tasks'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    if request.method == 'GET':
        # List tasks with optional filtering
        try:
            # Get query parameters
            status_filter = request.GET.get('status')
            search_query = request.GET.get('search')
            
            # Base queryset - exclude soft deleted
            tasks = Task.objects.filter(
                user=deeptalk_user, 
                deleted_at__isnull=True
            ).order_by('-created_at')
            
            # Apply filters
            if status_filter:
                tasks = tasks.filter(status=status_filter)
            
            if search_query:
                from django.db.models import Q
                tasks = tasks.filter(
                    Q(name__icontains=search_query) |
                    Q(description__icontains=search_query)
                )
            
            # Serialize and return
            serializer = TaskSerializer(tasks, many=True)
            return Response({
                'tasks': serializer.data,
                'total_count': tasks.count(),
                'status': 'success'
            })
            
        except Exception as e:
            logger.error(f"Error loading tasks: {e}")
            return Response({
                'error': 'Failed to load tasks',
                'tasks': [],
                'total_count': 0
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    elif request.method == 'POST':
        # Create new task
        try:
            serializer = TaskSerializer(data=request.data)
            if serializer.is_valid():
                task = serializer.save(user=deeptalk_user)
                
                return Response({
                    'message': 'Task created successfully',
                    'task': TaskSerializer(task).data,
                    'status': 'success'
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'error': 'Invalid task data',
                    'details': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Error creating task: {e}")
            return Response({
                'error': 'Failed to create task',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ===================================
# TASK MANAGEMENT ENDPOINTS
# ===================================


@csrf_exempt
@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([AllowAny])
def task_detail(request, task_id):
    """Get, update, or delete a specific task - CLEANED UP"""
    
    deeptalk_user = get_deeptalk_user_from_request(request)
    if not deeptalk_user:
        return Response({
            'error': 'Authentication required'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    # Get the task
    try:
        task = Task.objects.get(
            id=task_id, 
            user=deeptalk_user, 
            deleted_at__isnull=True
        )
    except Task.DoesNotExist:
        return Response({
            'error': 'Task not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error finding task {task_id}: {e}")
        return Response({
            'error': 'Invalid task ID'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if request.method == 'GET':
        # Return task details
        serializer = TaskSerializer(task)
        return Response({
            'task': serializer.data,
            'status': 'success'
        })
    
    elif request.method == 'PUT':
        # Update task
        try:
            serializer = TaskSerializer(task, data=request.data, partial=True)
            if serializer.is_valid():
                # Handle status changes
                if 'status' in request.data:
                    new_status = request.data['status']
                    if new_status == 'completed' and task.status != 'completed':
                        task.completed_at = timezone.now()
                        task.completion_percentage = 100
                    elif new_status != 'completed' and task.status == 'completed':
                        task.completed_at = None
                        task.completion_percentage = 0
                
                updated_task = serializer.save()
                
                return Response({
                    'message': 'Task updated successfully',
                    'task': TaskSerializer(updated_task).data,
                    'status': 'success'
                })
            else:
                return Response({
                    'error': 'Invalid data',
                    'details': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Error updating task {task_id}: {e}")
            return Response({
                'error': 'Failed to update task'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    elif request.method == 'DELETE':
        # Soft delete task
        try:
            task.deleted_at = timezone.now()
            task.save()
            
            return Response({
                'message': 'Task deleted successfully',
                'status': 'success'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error deleting task {task_id}: {e}")
            return Response({
                'error': 'Failed to delete task'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def task_toggle_status(request, task_id):
    """Toggle task between pending and completed - FIXED"""
    
    deeptalk_user = get_deeptalk_user_from_request(request)
    if not deeptalk_user:
        return Response({
            'error': 'Authentication required'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        task = Task.objects.get(
            id=task_id, 
            user=deeptalk_user, 
            deleted_at__isnull=True
        )
    except Task.DoesNotExist:
        return Response({
            'error': 'Task not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error finding task {task_id}: {e}")
        return Response({
            'error': 'Invalid task ID'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Toggle status
        if task.status == 'completed':
            task.status = 'pending'
            task.completed_at = None
            task.completion_percentage = 0
            action = 'reopened'
        else:
            task.status = 'completed'
            task.completed_at = timezone.now()
            task.completion_percentage = 100
            action = 'completed'
        
        task.save()
        
        return Response({
            'message': f'Task {action} successfully',
            'task': TaskSerializer(task).data,
            'action': action,
            'status': 'success'
        })
        
    except Exception as e:
        logger.error(f"Error toggling task {task_id}: {e}")
        return Response({
            'error': 'Failed to toggle task status'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def task_stats(request):
    """Get task statistics for the user - SIMPLIFIED"""
    
    deeptalk_user = get_deeptalk_user_from_request(request)
    if not deeptalk_user:
        return Response({
            'error': 'Authentication required'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        # Base queryset
        tasks = Task.objects.filter(
            user=deeptalk_user, 
            deleted_at__isnull=True
        )
        
        # Basic counts
        total = tasks.count()
        pending = tasks.filter(status='pending').count()
        completed = tasks.filter(status='completed').count()
        in_progress = tasks.filter(status='in_progress').count()
        
        # Overdue tasks
        overdue = tasks.filter(
            status='pending',
            deadline__lt=timezone.now(),
            deadline__isnull=False
        ).count()
        
        # Completion rate
        completion_rate = round((completed / total * 100) if total > 0 else 0, 2)
        
        # Recent activity (last 7 days)
        last_week = timezone.now() - timedelta(days=7)
        recent_completed = tasks.filter(
            status='completed',
            completed_at__gte=last_week
        ).count()
        recent_created = tasks.filter(created_at__gte=last_week).count()
        
        # Category breakdown (simplified)
        category_stats = []
        try:
            category_data = tasks.values('category__name').annotate(
                total=Count('id'),
                completed_count=Count('id', filter=Q(status='completed'))
            ).order_by('-total')[:5]  # Top 5 categories only
            
            for item in category_data:
                if item['category__name']:  # Skip None categories
                    category_stats.append({
                        'category': item['category__name'],
                        'total': item['total'],
                        'completed': item['completed_count']
                    })
        except Exception as e:
            logger.error(f"Error calculating category stats: {e}")
            # Continue without category stats
        
        return Response({
            'total': total,
            'pending': pending,
            'completed': completed,
            'in_progress': in_progress,
            'overdue': overdue,
            'completion_rate': completion_rate,
            'recent_activity': {
                'completed_last_week': recent_completed,
                'created_last_week': recent_created
            },
            'category_breakdown': category_stats,
            'status': 'success'
        })
        
    except Exception as e:
        logger.error(f"Error calculating task stats: {e}")
        return Response({
            'error': 'Failed to calculate statistics',
            'total': 0,
            'pending': 0,
            'completed': 0,
            'in_progress': 0,
            'overdue': 0,
            'completion_rate': 0,
            'status': 'error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def productivity_insights(request):
    """Get productivity insights for the user"""
    deeptalk_user = get_deeptalk_user_from_request(request)
    if not deeptalk_user:
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    days = int(request.GET.get('days', 7))
    start_date = timezone.now() - timedelta(days=days)
    
    tasks = Task.objects.filter(
        user=deeptalk_user, 
        deleted_at__isnull=True,
        created_at__gte=start_date
    )
    
    completed_tasks = tasks.filter(
        status='completed',
        completed_at__gte=start_date
    )
    
    insights = {
        'period_days': days,
        'tasks_created': tasks.count(),
        'tasks_completed': completed_tasks.count(),
        'completion_rate': round((completed_tasks.count() / tasks.count() * 100) if tasks.count() > 0 else 0, 2),
        'average_completion_time': None,
        'most_productive_day': None,
        'preferred_categories': [],
        'daily_completion_trend': {}
    }
    
    # Calculate average completion time
    if completed_tasks.exists():
        completion_times = []
        for task in completed_tasks:
            if task.completed_at and task.created_at:
                time_diff = (task.completed_at - task.created_at).total_seconds() / 3600  # hours
                completion_times.append(time_diff)
        
        if completion_times:
            insights['average_completion_time'] = round(sum(completion_times) / len(completion_times), 2)
    
    # Find most productive day
    daily_completion = {}
    for task in completed_tasks:
        if task.completed_at:
            day = task.completed_at.strftime('%A')
            daily_completion[day] = daily_completion.get(day, 0) + 1
    
    if daily_completion:
        insights['most_productive_day'] = max(daily_completion, key=daily_completion.get)
        insights['daily_completion_trend'] = daily_completion
    
    # Find preferred categories
    category_count = {}
    for task in tasks:
        if task.category:
            cat_name = task.category.name
            category_count[cat_name] = category_count.get(cat_name, 0) + 1
    
    insights['preferred_categories'] = [
        {'category': cat, 'count': count} 
        for cat, count in sorted(category_count.items(), key=lambda x: x[1], reverse=True)[:3]
    ]
    
    return Response(insights)


# ===================================
# TASK CATEGORY ENDPOINTS
# ===================================

@csrf_exempt
@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def categories_list_create(request):
    """List categories or create new category"""
    deeptalk_user = get_deeptalk_user_from_request(request)
    if not deeptalk_user:
        return Response({
            'error': 'Authentication required'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    if request.method == 'GET':
        try:
            # Get user's categories and system categories
            categories = TaskCategory.objects.filter(
                Q(user=deeptalk_user) | Q(is_system_category=True)
            ).distinct()
            
            serializer = TaskCategorySerializer(categories, many=True)
            return Response({
                'categories': serializer.data,
                'status': 'success'
            })
        except Exception as e:
            logger.error(f"Error loading categories: {e}")
            return Response({
                'categories': [],
                'error': 'Failed to load categories'
            })
    
    elif request.method == 'POST':
        try:
            data = request.data.copy()
            data['user'] = deeptalk_user.id
            data['is_system_category'] = False
            
            serializer = TaskCategorySerializer(data=data)
            if serializer.is_valid():
                category = serializer.save()
                return Response({
                    'category': TaskCategorySerializer(category).data,
                    'message': 'Category created successfully',
                    'status': 'success'
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'error': 'Invalid category data',
                    'details': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error creating category: {e}")
            return Response({
                'error': 'Failed to create category'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@csrf_exempt
@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([AllowAny])
def category_detail(request, category_id):
    """Get, update, or delete a specific category"""
    deeptalk_user = get_deeptalk_user_from_request(request)
    if not deeptalk_user:
        return Response({
            'error': 'Authentication required'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        category = TaskCategory.objects.get(
            id=category_id, 
            user=deeptalk_user,
            is_system_category=False  # Only allow editing user categories
        )
    except TaskCategory.DoesNotExist:
        return Response({
            'error': 'Category not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        serializer = TaskCategorySerializer(category)
        return Response({
            'category': serializer.data,
            'status': 'success'
        })
    
    elif request.method == 'PUT':
        try:
            serializer = TaskCategorySerializer(category, data=request.data, partial=True)
            if serializer.is_valid():
                updated_category = serializer.save()
                return Response({
                    'category': TaskCategorySerializer(updated_category).data,
                    'message': 'Category updated successfully',
                    'status': 'success'
                })
            else:
                return Response({
                    'error': 'Invalid data',
                    'details': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error updating category: {e}")
            return Response({
                'error': 'Failed to update category'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    elif request.method == 'DELETE':
        try:
            # Check if category is in use
            if Task.objects.filter(category=category, deleted_at__isnull=True).exists():
                return Response({
                    'error': 'Cannot delete category that is in use by tasks'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            category.delete()
            return Response({
                'message': 'Category deleted successfully',
                'status': 'success'
            })
        except Exception as e:
            logger.error(f"Error deleting category: {e}")
            return Response({
                'error': 'Failed to delete category'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ===================================
# USER PREFERENCES ENDPOINTS
# ===================================

@csrf_exempt
@api_view(['GET', 'PUT'])
@permission_classes([AllowAny])
def user_preferences(request):
    """Get or update user preferences"""
    deeptalk_user = get_deeptalk_user_from_request(request)
    if not deeptalk_user:
        return Response({
            'error': 'Authentication required'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    # Get or create preferences
    try:
        preferences, created = UserPreferences.objects.get_or_create(
            user=deeptalk_user,
            defaults={
                'work_start_time': '09:00:00',
                'work_end_time': '17:00:00',
                'default_task_duration': 60,
                'max_daily_tasks': 10
            }
        )
    except Exception as e:
        logger.error(f"Error getting preferences: {e}")
        return Response({
            'error': 'Failed to load preferences'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    if request.method == 'GET':
        try:
            serializer = UserPreferencesSerializer(preferences)
            return Response({
                'preferences': serializer.data,
                'status': 'success'
            })
        except Exception as e:
            logger.error(f"Error serializing preferences: {e}")
            return Response({
                'error': 'Failed to load preferences'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    elif request.method == 'PUT':
        try:
            serializer = UserPreferencesSerializer(preferences, data=request.data, partial=True)
            if serializer.is_valid():
                updated_preferences = serializer.save()
                return Response({
                    'preferences': UserPreferencesSerializer(updated_preferences).data,
                    'message': 'Preferences updated successfully',
                    'status': 'success'
                })
            else:
                return Response({
                    'error': 'Invalid preference data',
                    'details': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error updating preferences: {e}")
            return Response({
                'error': 'Failed to update preferences'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===================================
# BULK OPERATIONS
# ===================================

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def bulk_update_tasks(request):
    """Bulk update multiple tasks"""
    deeptalk_user = get_deeptalk_user_from_request(request)
    if not deeptalk_user:
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    task_ids = request.data.get('task_ids', [])
    updates = request.data.get('updates', {})
    
    if not task_ids or not updates:
        return Response({
            'error': 'task_ids and updates are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Get tasks
    tasks = Task.objects.filter(
        id__in=task_ids,
        user=deeptalk_user,
        deleted_at__isnull=True
    )
    
    updated_tasks = []
    for task in tasks:
        previous_values = TaskSerializer(task).data
        
        # Apply updates
        for field, value in updates.items():
            if hasattr(task, field):
                setattr(task, field, value)
        
        # Handle status changes
        if 'status' in updates:
            if updates['status'] == 'completed' and task.status != 'completed':
                task.completed_at = timezone.now()
                task.completion_percentage = 100
        
        task.save()
        
        # Create task log
        create_task_log(task, deeptalk_user, 'updated', 
                      previous_values=previous_values, 
                      new_values=TaskSerializer(task).data,
                      triggered_by='user')
        
        updated_tasks.append(TaskSerializer(task).data)
    
    return Response({
        'message': f'Updated {len(updated_tasks)} tasks',
        'updated_tasks': updated_tasks
    })


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def bulk_delete_tasks(request):
    """Bulk delete multiple tasks"""
    deeptalk_user = get_deeptalk_user_from_request(request)
    if not deeptalk_user:
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    task_ids = request.data.get('task_ids', [])
    
    if not task_ids:
        return Response({
            'error': 'task_ids is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Get tasks
    tasks = Task.objects.filter(
        id__in=task_ids,
        user=deeptalk_user,
        deleted_at__isnull=True
    )
    
    deleted_count = 0
    for task in tasks:
        previous_values = TaskSerializer(task).data
        task.soft_delete()
        
        # Create task log
        create_task_log(task, deeptalk_user, 'deleted', 
                      previous_values=previous_values,
                      triggered_by='user')
        
        deleted_count += 1
    
    return Response({
        'message': f'Deleted {deleted_count} tasks'
    })


# ===================================
# SEARCH ENDPOINT
# ===================================

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def search_tasks(request):
    """Advanced task search"""
    deeptalk_user = get_deeptalk_user_from_request(request)
    if not deeptalk_user:
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    query = request.GET.get('q', '')
    if not query:
        return Response({'error': 'Search query is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Search in multiple fields
    tasks = Task.objects.filter(
        user=deeptalk_user,
        deleted_at__isnull=True
    ).filter(
        Q(name__icontains=query) |
        Q(description__icontains=query) |
        Q(tags__contains=[query]) |
        Q(location__icontains=query) |
        Q(category__name__icontains=query)
    ).distinct()
    
    # Apply additional filters
    status_filter = request.GET.get('status')
    if status_filter:
        tasks = tasks.filter(status=status_filter)
    
    priority_filter = request.GET.get('priority')
    if priority_filter:
        tasks = tasks.filter(priority=int(priority_filter))
    
    # Order by created date for SQLite compatibility
    tasks = tasks.order_by('-created_at')
    
    serializer = TaskSerializer(tasks, many=True)
    return Response({
        'tasks': serializer.data,
        'total_count': tasks.count(),
        'query': query
    })
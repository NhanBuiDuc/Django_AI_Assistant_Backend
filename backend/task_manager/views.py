from deeptalk.utils import get_deeptalk_user_from_request
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from django.db.models import Q, Count
from django.db import transaction
from datetime import timedelta
import logging

from .models import (
    Task, TaskCategory, UserPreferences, TaskDependency, TaskLog, Reminder
)
from .serializers import (
    TaskSerializer, TaskCategorySerializer, UserPreferencesSerializer
)
from .utils import create_task_log

logger = logging.getLogger(__name__)

# ===================================
# CUSTOM AUTHENTICATION & PERMISSIONS
# ===================================

def get_authenticated_deeptalk_user(request):
    """Get authenticated DeepTalkUser from request"""
    # First ensure the user is authenticated via DRF
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return None
    
    # Then get the corresponding DeepTalkUser
    return get_deeptalk_user_from_request(request)

class IsOwnerOrReadOnly(permissions.BasePermission):
    """Custom permission: owners can edit, others can read"""
    
    def has_object_permission(self, request, view, obj):
        # Read permissions for any request
        if request.method in permissions.SAFE_METHODS:
            return True
        # Write permissions only to the owner
        return obj.user == request.user

# ===================================
# TASK MANAGEMENT ENDPOINTS
# ===================================

@api_view(['GET', 'POST'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def tasks_list_create(request):
    """List tasks or create new task with proper authentication"""
    
    deeptalk_user = get_authenticated_deeptalk_user(request)
    if not deeptalk_user:
        return Response({
            'error': 'Authentication required',
            'message': 'Please sign in to manage your tasks'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    if request.method == 'GET':
        try:
            # Get query parameters
            status_filter = request.GET.get('status')
            search_query = request.GET.get('search')
            category_filter = request.GET.get('category')
            
            # Optimized queryset - prevent N+1 queries
            tasks = Task.objects.select_related('category').filter(
                user=deeptalk_user, 
                deleted_at__isnull=True
            ).order_by('-created_at')
            
            # Apply filters
            if status_filter:
                tasks = tasks.filter(status=status_filter)
            
            if category_filter:
                tasks = tasks.filter(category_id=category_filter)
            
            if search_query:
                tasks = tasks.filter(
                    Q(name__icontains=search_query) |
                    Q(description__icontains=search_query) |
                    Q(tags__contains=[search_query])
                )
            
            # Pagination
            paginator = PageNumberPagination()
            paginator.page_size = 20
            page = paginator.paginate_queryset(tasks, request)
            
            if page is not None:
                serializer = TaskSerializer(page, many=True)
                return paginator.get_paginated_response({
                    'tasks': serializer.data,
                    'status': 'success'
                })
            
            # Fallback without pagination
            serializer = TaskSerializer(tasks, many=True)
            return Response({
                'tasks': serializer.data,
                'total_count': tasks.count(),
                'status': 'success'
            })
            
        except Exception as e:
            logger.error(f"Error loading tasks for user {deeptalk_user.id}: {e}")
            return Response({
                'error': 'Failed to load tasks',
                'tasks': [],
                'total_count': 0
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    elif request.method == 'POST':
        try:
            with transaction.atomic():
                serializer = TaskSerializer(data=request.data)
                if serializer.is_valid():
                    task = serializer.save(user=deeptalk_user)
                    
                    # Create task log
                    create_task_log(
                        task=task, 
                        user=deeptalk_user, 
                        action='created',
                        triggered_by='user'
                    )
                    
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
            logger.error(f"Error creating task for user {deeptalk_user.id}: {e}")
            return Response({
                'error': 'Failed to create task',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def task_detail(request, task_id):
    """Get, update, or delete a specific task with ownership validation"""
    
    deeptalk_user = get_authenticated_deeptalk_user(request)
    if not deeptalk_user:
        return Response({
            'error': 'Authentication required'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    # Get the task with ownership validation
    try:
        task = Task.objects.select_related('category').get(
            id=task_id, 
            user=deeptalk_user, 
            deleted_at__isnull=True
        )
    except Task.DoesNotExist:
        return Response({
            'error': 'Task not found or access denied'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error finding task {task_id} for user {deeptalk_user.id}: {e}")
        return Response({
            'error': 'Invalid task ID'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if request.method == 'GET':
        serializer = TaskSerializer(task)
        return Response({
            'task': serializer.data,
            'status': 'success'
        })
    
    elif request.method == 'PUT':
        try:
            with transaction.atomic():
                previous_values = TaskSerializer(task).data
                
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
                            if 'completion_percentage' not in request.data:
                                task.completion_percentage = 0
                    
                    updated_task = serializer.save()
                    
                    # Create task log
                    create_task_log(
                        task=updated_task, 
                        user=deeptalk_user, 
                        action='updated',
                        previous_values=previous_values,
                        new_values=TaskSerializer(updated_task).data,
                        triggered_by='user'
                    )
                    
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
            logger.error(f"Error updating task {task_id} for user {deeptalk_user.id}: {e}")
            return Response({
                'error': 'Failed to update task'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    elif request.method == 'DELETE':
        try:
            with transaction.atomic():
                previous_values = TaskSerializer(task).data
                
                task.deleted_at = timezone.now()
                task.save()
                
                # Create task log
                create_task_log(
                    task=task, 
                    user=deeptalk_user, 
                    action='deleted',
                    previous_values=previous_values,
                    triggered_by='user'
                )
                
                return Response({
                    'message': 'Task deleted successfully',
                    'status': 'success'
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error deleting task {task_id} for user {deeptalk_user.id}: {e}")
            return Response({
                'error': 'Failed to delete task'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def task_toggle_status(request, task_id):
    """Toggle task between pending and completed with ownership validation"""
    
    deeptalk_user = get_authenticated_deeptalk_user(request)
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
            'error': 'Task not found or access denied'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error finding task {task_id} for user {deeptalk_user.id}: {e}")
        return Response({
            'error': 'Invalid task ID'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        with transaction.atomic():
            previous_values = TaskSerializer(task).data
            
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
            
            # Create task log
            create_task_log(
                task=task, 
                user=deeptalk_user, 
                action=action,
                previous_values=previous_values,
                new_values=TaskSerializer(task).data,
                triggered_by='user'
            )
            
            return Response({
                'message': f'Task {action} successfully',
                'task': TaskSerializer(task).data,
                'action': action,
                'status': 'success'
            })
            
    except Exception as e:
        logger.error(f"Error toggling task {task_id} for user {deeptalk_user.id}: {e}")
        return Response({
            'error': 'Failed to toggle task status'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def task_stats(request):
    """Get task statistics for the authenticated user"""
    
    deeptalk_user = get_authenticated_deeptalk_user(request)
    if not deeptalk_user:
        return Response({
            'error': 'Authentication required'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        # Optimized queryset with select_related
        tasks = Task.objects.select_related('category').filter(
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
        
        # Category breakdown (optimized query)
        category_stats = []
        try:
            category_data = tasks.exclude(category__isnull=True).values(
                'category__name'
            ).annotate(
                total=Count('id'),
                completed_count=Count('id', filter=Q(status='completed'))
            ).order_by('-total')[:5]
            
            category_stats = [
                {
                    'category': item['category__name'],
                    'total': item['total'],
                    'completed': item['completed_count']
                }
                for item in category_data
            ]
        except Exception as e:
            logger.error(f"Error calculating category stats for user {user.id}: {e}")
        
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
        logger.error(f"Error calculating task stats for user {user.id}: {e}")
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

@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def productivity_insights(request):
    """Get productivity insights for the authenticated user"""
    
    user = request.user
    days = int(request.GET.get('days', 7))
    start_date = timezone.now() - timedelta(days=days)
    
    try:
        tasks = Task.objects.filter(
            user=user, 
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
                    time_diff = (task.completed_at - task.created_at).total_seconds() / 3600
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
        for task in tasks.select_related('category'):
            if task.category:
                cat_name = task.category.name
                category_count[cat_name] = category_count.get(cat_name, 0) + 1
        
        insights['preferred_categories'] = [
            {'category': cat, 'count': count} 
            for cat, count in sorted(category_count.items(), key=lambda x: x[1], reverse=True)[:3]
        ]
        
        return Response(insights)
        
    except Exception as e:
        logger.error(f"Error calculating productivity insights for user {user.id}: {e}")
        return Response({
            'error': 'Failed to calculate insights'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ===================================
# TASK CATEGORY ENDPOINTS
# ===================================

@api_view(['GET', 'POST'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def categories_list_create(request):
    """List categories or create new category with proper authentication"""
    
    user = request.user
    
    if request.method == 'GET':
        try:
            # Get user's categories and system categories
            categories = TaskCategory.objects.filter(
                Q(user=user) | Q(is_system_category=True)
            ).distinct().order_by('name')
            
            serializer = TaskCategorySerializer(categories, many=True)
            return Response({
                'categories': serializer.data,
                'status': 'success'
            })
        except Exception as e:
            logger.error(f"Error loading categories for user {user.id}: {e}")
            return Response({
                'categories': [],
                'error': 'Failed to load categories'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    elif request.method == 'POST':
        try:
            data = request.data.copy()
            data['user'] = user.id
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
            logger.error(f"Error creating category for user {user.id}: {e}")
            return Response({
                'error': 'Failed to create category'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def category_detail(request, category_id):
    """Get, update, or delete a specific category with ownership validation"""
    
    user = request.user
    
    try:
        category = TaskCategory.objects.get(
            id=category_id, 
            user=user,
            is_system_category=False
        )
    except TaskCategory.DoesNotExist:
        return Response({
            'error': 'Category not found or access denied'
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
            logger.error(f"Error updating category {category_id} for user {user.id}: {e}")
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
            logger.error(f"Error deleting category {category_id} for user {user.id}: {e}")
            return Response({
                'error': 'Failed to delete category'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ===================================
# USER PREFERENCES ENDPOINTS
# ===================================

@api_view(['GET', 'PUT'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def user_preferences(request):
    """Get or update user preferences with proper authentication"""
    
    user = request.user
    
    try:
        preferences, created = UserPreferences.objects.get_or_create(
            user=user,
            defaults={
                'work_start_time': '09:00:00',
                'work_end_time': '17:00:00',
                'default_task_duration': 60,
                'max_daily_tasks': 10
            }
        )
    except Exception as e:
        logger.error(f"Error getting preferences for user {user.id}: {e}")
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
            logger.error(f"Error serializing preferences for user {user.id}: {e}")
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
            logger.error(f"Error updating preferences for user {user.id}: {e}")
            return Response({
                'error': 'Failed to update preferences'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ===================================
# BULK OPERATIONS
# ===================================

@api_view(['POST'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def bulk_update_tasks(request):
    """Bulk update multiple tasks with ownership validation"""
    
    user = request.user
    task_ids = request.data.get('task_ids', [])
    updates = request.data.get('updates', {})
    
    if not task_ids or not updates:
        return Response({
            'error': 'task_ids and updates are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        with transaction.atomic():
            # Get tasks with ownership validation
            tasks = Task.objects.filter(
                id__in=task_ids,
                user=user,
                deleted_at__isnull=True
            )
            
            if not tasks.exists():
                return Response({
                    'error': 'No accessible tasks found'
                }, status=status.HTTP_404_NOT_FOUND)
            
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
                create_task_log(
                    task=task, 
                    user=user, 
                    action='updated', 
                    previous_values=previous_values, 
                    new_values=TaskSerializer(task).data,
                    triggered_by='user'
                )
                
                updated_tasks.append(TaskSerializer(task).data)
            
            return Response({
                'message': f'Updated {len(updated_tasks)} tasks',
                'updated_tasks': updated_tasks,
                'status': 'success'
            })
            
    except Exception as e:
        logger.error(f"Error bulk updating tasks for user {user.id}: {e}")
        return Response({
            'error': 'Failed to update tasks'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def bulk_delete_tasks(request):
    """Bulk delete multiple tasks with ownership validation"""
    
    user = request.user
    task_ids = request.data.get('task_ids', [])
    
    if not task_ids:
        return Response({
            'error': 'task_ids is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        with transaction.atomic():
            # Get tasks with ownership validation
            tasks = Task.objects.filter(
                id__in=task_ids,
                user=user,
                deleted_at__isnull=True
            )
            
            if not tasks.exists():
                return Response({
                    'error': 'No accessible tasks found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            deleted_count = 0
            for task in tasks:
                previous_values = TaskSerializer(task).data
                task.deleted_at = timezone.now()
                task.save()
                
                # Create task log
                create_task_log(
                    task=task, 
                    user=user, 
                    action='deleted', 
                    previous_values=previous_values,
                    triggered_by='user'
                )
                
                deleted_count += 1
            
            return Response({
                'message': f'Deleted {deleted_count} tasks',
                'status': 'success'
            })
            
    except Exception as e:
        logger.error(f"Error bulk deleting tasks for user {user.id}: {e}")
        return Response({
            'error': 'Failed to delete tasks'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ===================================
# SEARCH ENDPOINT
# ===================================

@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def search_tasks(request):
    """Advanced task search with proper authentication"""
    
    user = request.user
    query = request.GET.get('q', '')
    
    if not query:
        return Response({
            'error': 'Search query is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Optimized search query with select_related
        tasks = Task.objects.select_related('category').filter(
            user=user,
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
        
        category_filter = request.GET.get('category')
        if category_filter:
            tasks = tasks.filter(category_id=category_filter)
        
        # Order by relevance (created date for now)
        tasks = tasks.order_by('-created_at')
        
        # Pagination
        paginator = PageNumberPagination()
        paginator.page_size = 20
        page = paginator.paginate_queryset(tasks, request)
        
        if page is not None:
            serializer = TaskSerializer(page, many=True)
            return paginator.get_paginated_response({
                'tasks': serializer.data,
                'query': query,
                'status': 'success'
            })
        
        # Fallback without pagination
        serializer = TaskSerializer(tasks, many=True)
        return Response({
            'tasks': serializer.data,
            'total_count': tasks.count(),
            'query': query,
            'status': 'success'
        })
        
    except Exception as e:
        logger.error(f"Error searching tasks for user {user.id}: {e}")
        return Response({
            'error': 'Search failed',
            'tasks': [],
            'total_count': 0,
            'query': query
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
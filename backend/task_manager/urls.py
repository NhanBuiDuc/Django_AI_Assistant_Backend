from django.urls import path
from . import views

app_name = 'task_manager'

urlpatterns = [
    # Task CRUD operations
    path('tasks/', views.tasks_list_create, name='tasks_list_create'),
    path('tasks/<uuid:task_id>/', views.task_detail, name='task_detail'),
    path('tasks/<uuid:task_id>/toggle/', views.task_toggle_status, name='task_toggle_status'),
    
    # Task statistics and insights
    path('tasks/stats/', views.task_stats, name='task_stats'),
    path('tasks/insights/', views.productivity_insights, name='productivity_insights'),
    
    # Task search and bulk operations
    path('tasks/search/', views.search_tasks, name='search_tasks'),
    path('tasks/bulk/update/', views.bulk_update_tasks, name='bulk_update_tasks'),
    path('tasks/bulk/delete/', views.bulk_delete_tasks, name='bulk_delete_tasks'),
    
    # Categories
    path('categories/', views.categories_list_create, name='categories_list_create'),
    path('categories/<uuid:category_id>/', views.category_detail, name='category_detail'),
    
    # User preferences
    path('preferences/', views.user_preferences, name='user_preferences'),
]
# deeptalk/views.py - FIXED VERSION with better error handling

from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db.models import Q
import logging
import json
import requests
from django.conf import settings

# Import only what we need for AI functionality
from .utils import get_deeptalk_user_from_request

# Import task manager models with error handling
try:
    from task_manager.models import Task, TaskCategory
    from task_manager.serializers import TaskSerializer
except ImportError as e:
    logger.error(f"Failed to import task_manager models: {e}")
    # Create dummy classes to prevent crashes
    class Task:
        pass
    class TaskCategory:
        pass
    class TaskSerializer:
        def __init__(self, *args, **kwargs):
            pass
        @property
        def data(self):
            return {}

logger = logging.getLogger(__name__)

# ===================================
# JARVIS AI ENDPOINTS
# ===================================

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def jarvis_process_task(request):
    """
    Main AI endpoint for processing natural language task creation
    """
    logger.debug(f"Jarvis process task called with method: {request.method}")
    logger.debug(f"Request data: {request.data}")
    
    # Step 1: Authenticate user
    deeptalk_user = get_deeptalk_user_from_request(request)
    if not deeptalk_user:
        logger.error("Authentication failed in jarvis_process_task")
        return Response({
            'error': 'Authentication required',
            'message': 'Please sign in to use Jarvis AI'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    logger.debug(f"Authenticated user: {deeptalk_user}")
    
    # Step 2: Validate request data
    try:
        # Try different keys to get the message
        user_message = None
        
        # Method 1: From request.data - try multiple keys
        if hasattr(request, 'data') and request.data:
            # Try 'message' first, then 'input', then 'text'
            user_message = (
                request.data.get('message', '') or 
                request.data.get('input', '') or 
                request.data.get('text', '')
            ).strip()
            logger.debug(f"Message from request.data: '{user_message}'")
        
        # Method 2: From POST data if still empty
        if not user_message:
            user_message = (
                request.POST.get('message', '') or 
                request.POST.get('input', '') or 
                request.POST.get('text', '')
            ).strip()
            logger.debug(f"Message from POST data: '{user_message}'")
        
        if not user_message:
            logger.error("No message found in request")
            logger.debug(f"Available keys in request.data: {list(request.data.keys()) if request.data else 'None'}")
            return Response({
                'error': 'Message is required',
                'message': 'Please provide a message for Jarvis to process',
                'debug': {
                    'request_data_keys': list(request.data.keys()) if request.data else [],
                    'request_data': dict(request.data) if hasattr(request, 'data') else None,
                    'content_type': request.content_type,
                    'expected_keys': ['message', 'input', 'text']
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        logger.info(f"Processing message from {deeptalk_user}: '{user_message}'")
        
    except Exception as e:
        logger.error(f"Error validating request data: {type(e).__name__}: {e}")
        return Response({
            'error': 'Invalid request format',
            'message': f'Failed to process request: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Step 3: Process with AI
    try:
        ai_response = process_with_ollama(user_message, deeptalk_user)
        logger.debug(f"AI response: {ai_response}")
        
    except Exception as e:
        logger.error(f"Error in AI processing: {type(e).__name__}: {e}")
        return Response({
            'success': False,
            'message': 'AI processing failed',
            'ai_response': 'I encountered an error while processing your request. Please try again.',
            'tasks_created': [],
            'tasks_count': 0,
            'error_details': str(e)
        }, status=status.HTTP_200_OK)  # Return 200 but with error in response
    
    # Step 4: Create tasks if AI extracted any
    if ai_response.get('success'):
        created_tasks = []
        tasks_data = ai_response.get('tasks', [])
        
        logger.debug(f"AI extracted {len(tasks_data)} tasks")
        
        for i, task_data in enumerate(tasks_data):
            try:
                logger.debug(f"Creating task {i+1}: {task_data}")
                
                # Create task using task_manager models
                task = Task.objects.create(
                    user=deeptalk_user,
                    name=task_data.get('name', f'Task from AI {i+1}'),
                    description=task_data.get('description', ''),
                    priority=task_data.get('priority', 3),
                    deadline=task_data.get('deadline'),
                    ai_suggested=True,
                    ai_confidence_score=task_data.get('confidence', 0.8)
                )
                
                created_tasks.append(TaskSerializer(task).data)
                logger.info(f"AI created task: {task.name} for user {deeptalk_user}")
                
            except Exception as e:
                logger.error(f"Failed to create AI task {i+1}: {type(e).__name__}: {e}")
                continue
        
        return Response({
            'success': True,
            'message': ai_response.get('message', 'Tasks processed successfully'),
            'ai_response': ai_response.get('response', ''),
            'tasks_created': created_tasks,
            'tasks_count': len(created_tasks)
        })
    else:
        # AI processing failed but we can still return a response
        return Response({
            'success': False,
            'message': ai_response.get('message', 'Failed to process with AI'),
            'ai_response': ai_response.get('response', 'I had trouble understanding your request. Could you please rephrase it?'),
            'tasks_created': [],
            'tasks_count': 0
        })

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def jarvis_health_check(request):
    """
    Health check for the AI system
    """
    try:
        # Check Ollama connection
        ollama_status = check_ollama_health()
        
        # Check database connection
        db_status = check_database_health()
        
        # Overall health
        is_healthy = ollama_status['healthy'] and db_status['healthy']
        
        return Response({
            'status': 'healthy' if is_healthy else 'unhealthy',
            'timestamp': timezone.now().isoformat(),
            'services': {
                'ollama': ollama_status,
                'database': db_status
            },
            'version': '1.0.0'
        }, status=status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE)
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return Response({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

# ===================================
# AI HELPER FUNCTIONS
# ===================================

def get_available_ollama_model():
    """Get the first available Ollama model"""
    try:
        if not hasattr(settings, 'OLLAMA_BASE_URL'):
            return None
            
        response = requests.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            models_data = response.json()
            available_models = [m.get('name') for m in models_data.get('models', [])]
            
            # Check if configured model exists
            configured_model = getattr(settings, 'OLLAMA_MODEL', 'llama3.2:latest')
            if configured_model in available_models:
                return configured_model
            
            # Return first available model
            if available_models:
                logger.info(f"Configured model '{configured_model}' not found, using '{available_models[0]}'")
                return available_models[0]
        
        return None
    except Exception as e:
        logger.error(f"Failed to get available models: {e}")
        return None

def process_with_ollama(user_message, user):
    """
    Process user message with Ollama AI - FIXED VERSION
    """
    logger.debug(f"Starting Ollama processing for message: '{user_message}'")
    
    try:
        # Get user's existing categories for context
        try:
            categories = TaskCategory.objects.filter(
                Q(user=user) | Q(is_system_category=True)
            ).values_list('name', flat=True)
            categories_list = list(categories)
            logger.debug(f"Found {len(categories_list)} categories for context")
        except Exception as e:
            logger.error(f"Failed to get categories: {e}")
            categories_list = ['Work', 'Personal', 'Health', 'Education']
        
        # Create AI prompt
        system_prompt = f"""
You are Jarvis, an AI task management assistant. Extract actionable tasks from the user's message.

Available categories: {', '.join(categories_list)}

Respond with JSON format:
{{
    "response": "Your conversational response to the user",
    "tasks": [
        {{
            "name": "Task name",
            "description": "Task description",
            "priority": 1-5 (1=highest),
            "deadline": "YYYY-MM-DD HH:MM:SS" or null,
            "confidence": 0.0-1.0
        }}
    ]
}}

If no actionable tasks found, return empty tasks array but still provide a helpful response.
"""
        
        # Check Ollama configuration and get available model
        if not hasattr(settings, 'OLLAMA_BASE_URL'):
            logger.error("OLLAMA_BASE_URL missing in settings")
            return {
                'success': False,
                'message': 'AI configuration error',
                'response': 'AI is not properly configured. Please contact support.'
            }
        
        # Get available model (with fallback logic)
        model_to_use = get_available_ollama_model()
        if not model_to_use:
            logger.error("No Ollama models available")
            return {
                'success': False,
                'message': 'No AI models available',
                'response': 'No AI models are currently available. Please check that Ollama is running with models installed.'
            }
        
        # Call Ollama API with available model
        ollama_url = f"{settings.OLLAMA_BASE_URL}/api/generate"
        payload = {
            "model": model_to_use,
            "prompt": f"{system_prompt}\n\nUser message: {user_message}",
            "format": "json",
            "stream": False
        }
        
        logger.debug(f"Calling Ollama at {ollama_url} with model {model_to_use}")
        
        response = requests.post(ollama_url, json=payload, timeout=30)
        logger.debug(f"Ollama response status: {response.status_code}")
        
        if response.status_code == 200:
            ai_data = response.json()
            ai_response_text = ai_data.get('response', '')
            logger.debug(f"Raw AI response: {ai_response_text[:200]}...")
            
            try:
                # Parse AI response
                parsed_response = json.loads(ai_response_text)
                logger.debug(f"Parsed AI response: {parsed_response}")
                
                return {
                    'success': True,
                    'response': parsed_response.get('response', 'Task processed!'),
                    'tasks': parsed_response.get('tasks', []),
                    'message': 'AI processing successful'
                }
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse AI JSON response: {e}")
                # If JSON parsing fails, treat as conversational response
                return {
                    'success': True,
                    'response': ai_response_text,
                    'tasks': [],
                    'message': 'AI responded but no tasks extracted'
                }
        else:
            logger.error(f"Ollama API error: {response.status_code} - {response.text}")
            return {
                'success': False,
                'message': 'AI service error',
                'response': 'I apologize, but the AI service is currently experiencing issues. Please try again later.'
            }
    
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Ollama connection error: {e}")
        return {
            'success': False,
            'message': 'AI service unavailable',
            'response': 'I cannot connect to the AI service right now. Please check that Ollama is running and try again.'
        }
    except requests.exceptions.Timeout as e:
        logger.error(f"Ollama request timeout: {e}")
        return {
            'success': False,
            'message': 'AI request timeout',
            'response': 'The AI took too long to respond. Please try again with a shorter message.'
        }
    except Exception as e:
        logger.error(f"Unexpected error in Ollama processing: {type(e).__name__}: {e}")
        return {
            'success': False,
            'message': 'AI processing failed',
            'response': 'I encountered an unexpected error while processing your request. Please try again.'
        }

def check_ollama_health():
    """
    Check if Ollama service is running and responsive - FIXED VERSION
    """
    try:
        if not hasattr(settings, 'OLLAMA_BASE_URL'):
            return {
                'healthy': False,
                'status': 'configuration_missing',
                'models_available': 0,
                'required_model_loaded': False
            }
        
        health_url = f"{settings.OLLAMA_BASE_URL}/api/tags"
        response = requests.get(health_url, timeout=5)
        
        if response.status_code == 200:
            models = response.json().get('models', [])
            available_model_names = [m.get('name', 'unknown') for m in models]
            
            # Check if any model is available (not just the configured one)
            has_any_model = len(models) > 0
            configured_model = getattr(settings, 'OLLAMA_MODEL', 'llama3.2:latest')
            has_configured_model = configured_model in available_model_names
            
            return {
                'healthy': True,
                'status': 'connected',
                'models_available': len(models),
                'required_model_loaded': has_configured_model,
                'available_models': available_model_names[:3],  # First 3 models
                'configured_model': configured_model,
                'fallback_available': has_any_model
            }
        else:
            return {
                'healthy': False,
                'status': f'http_error_{response.status_code}',
                'models_available': 0,
                'required_model_loaded': False
            }
    
    except requests.exceptions.ConnectionError:
        return {
            'healthy': False,
            'status': 'connection_refused',
            'models_available': 0,
            'required_model_loaded': False
        }
    except requests.exceptions.Timeout:
        return {
            'healthy': False,
            'status': 'timeout',
            'models_available': 0,
            'required_model_loaded': False
        }
    except Exception as e:
        return {
            'healthy': False,
            'status': f'error: {str(e)}',
            'models_available': 0,
            'required_model_loaded': False
        }

def check_ollama_health():
    """
    Check if Ollama service is running and responsive
    """
    try:
        if not hasattr(settings, 'OLLAMA_BASE_URL'):
            return {
                'healthy': False,
                'status': 'configuration_missing',
                'models_available': 0,
                'required_model_loaded': False
            }
        
        health_url = f"{settings.OLLAMA_BASE_URL}/api/tags"
        response = requests.get(health_url, timeout=5)
        
        if response.status_code == 200:
            models = response.json().get('models', [])
            required_model = getattr(settings, 'OLLAMA_MODEL', 'llama3.2:latest')
            has_required_model = any(
                model.get('name', '').startswith(required_model) 
                for model in models
            )
            
            return {
                'healthy': True,
                'status': 'connected',
                'models_available': len(models),
                'required_model_loaded': has_required_model,
                'models': [m.get('name', 'unknown') for m in models[:3]]  # First 3 models
            }
        else:
            return {
                'healthy': False,
                'status': f'http_error_{response.status_code}',
                'models_available': 0,
                'required_model_loaded': False
            }
    
    except requests.exceptions.ConnectionError:
        return {
            'healthy': False,
            'status': 'connection_refused',
            'models_available': 0,
            'required_model_loaded': False
        }
    except requests.exceptions.Timeout:
        return {
            'healthy': False,
            'status': 'timeout',
            'models_available': 0,
            'required_model_loaded': False
        }
    except Exception as e:
        return {
            'healthy': False,
            'status': f'error: {str(e)}',
            'models_available': 0,
            'required_model_loaded': False
        }

def check_database_health():
    """
    Check database connectivity
    """
    try:
        # Simple database query to check connectivity
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
        
        # Count some basic stats
        try:
            total_tasks = Task.objects.count()
            total_categories = TaskCategory.objects.count()
        except:
            total_tasks = 0
            total_categories = 0
        
        return {
            'healthy': True,
            'status': 'connected',
            'total_tasks': total_tasks,
            'total_categories': total_categories
        }
    
    except Exception as e:
        return {
            'healthy': False,
            'status': f'error: {str(e)}',
            'total_tasks': 0,
            'total_categories': 0
        }

# ===================================
# DEBUG ENDPOINTS
# ===================================

@csrf_exempt
@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def debug_auth(request):
    """
    Debug endpoint to check authentication status and request data
    """
    deeptalk_user = get_deeptalk_user_from_request(request)
    
    debug_info = {
        'timestamp': timezone.now().isoformat(),
        'method': request.method,
        'authenticated': deeptalk_user is not None,
        'user_info': None,
        'headers': dict(request.headers),
        'session_data': dict(request.session) if hasattr(request, 'session') else None,
        'request_data': dict(request.data) if hasattr(request, 'data') else None,
        'content_type': request.content_type,
    }
    
    if deeptalk_user:
        debug_info['user_info'] = {
            'id': str(deeptalk_user.id) if hasattr(deeptalk_user, 'id') else 'unknown',
            'email': getattr(deeptalk_user, 'email', 'unknown'),
            'user_type': type(deeptalk_user).__name__
        }
    
    logger.debug(f"Auth debug: {debug_info}")
    
    return Response(debug_info)
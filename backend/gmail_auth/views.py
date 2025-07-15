
# ===================================
# backend/gmail_auth/views.py - CORRECTED VERSION
# ===================================

import os
import json
import jwt
import time
import base64
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth import login, logout, get_user_model
from django.contrib.auth.models import User
from django.http import JsonResponse, HttpResponseRedirect, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from django.utils import timezone
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from rest_framework import status
from .models import GoogleToken, UserSession, AIConfiguration
# from .ai_agent import create_ai_agent
from langchain.schema import SystemMessage, HumanMessage
from django.db.models import Q, Count, Avg
from task_manager.models import (
    DeepTalkUser, TaskCategory,
)

# Import DeepTalk models from the correct app
from task_manager.models import (
    DeepTalkUser, Task, TaskCategory, Schedule, 
    UserPreferences, TaskDependency, TaskLog, Reminder
)
from task_manager.serializers import (
    TaskSerializer, TaskCategorySerializer, 
    UserPreferencesSerializer, ScheduleSerializer
)

# Allow HTTP for development only
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

User = get_user_model()

# Google OAuth Flow
flow = Flow.from_client_config(
    {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.GOOGLE_REDIRECT_URI]
        }
    },
    scopes=settings.GMAIL_SCOPES
)
flow.redirect_uri = settings.GOOGLE_REDIRECT_URI

# ===================================
# HELPER FUNCTIONS
# ===================================

def create_jwt_token(user):
    """Create JWT token with proper expiry handling"""
    try:
        # Check if user has valid Google token
        google_token = GoogleToken.objects.get(user=user, is_active=True)
        has_gmail_access = not google_token.is_expired()
    except GoogleToken.DoesNotExist:
        has_gmail_access = False
    
    payload = {
        'user_id': user.id,
        'email': user.email,
        'has_gmail_access': has_gmail_access,
        'exp': datetime.utcnow() + timedelta(hours=2),  # 2 hour expiry
        'iat': datetime.utcnow(),
        'type': 'access_token'
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')

def get_user_from_request(request):
    """Enhanced user extraction with better error handling"""
    # Try JWT token first
    auth_header = request.META.get('HTTP_AUTHORIZATION')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            
            # Check if token is expired
            if payload['exp'] < datetime.utcnow().timestamp():
                return None
            
            user = User.objects.get(id=payload['user_id'])
            
            # Verify user still has valid Google token if Gmail access is claimed
            if payload.get('has_gmail_access'):
                try:
                    google_token = GoogleToken.objects.get(user=user, is_active=True)
                    if google_token.is_expired():
                        return None
                except GoogleToken.DoesNotExist:
                    return None
            
            return user
            
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, User.DoesNotExist):
            return None
    
    # Fallback to session authentication
    if request.user.is_authenticated:
        return request.user
    
    return None

def await_refresh_google_token(google_token):
    """Refresh Google access token if possible"""
    try:
        credentials = Credentials(
            token=google_token.access_token,
            refresh_token=google_token.refresh_token,
            token_uri=google_token.token_uri,
            client_id=google_token.client_id,
            client_secret=google_token.client_secret,
            scopes=google_token.scopes
        )
        
        # Refresh the token
        credentials.refresh(Request())
        
        # Update stored token
        google_token.access_token = credentials.token
        google_token.expires_at = timezone.now() + timedelta(seconds=3600)  # 1 hour
        google_token.save()
        
        return True
    except Exception as e:
        print(f"Failed to refresh Google token: {e}")
        # Mark token as inactive if refresh fails
        google_token.is_active = False
        google_token.save()
        return False

def get_gmail_service(user):
    """Get Gmail service for authenticated user"""
    try:
        google_token = GoogleToken.objects.get(user=user, is_active=True)
        
        credentials = Credentials(
            token=google_token.access_token,
            refresh_token=google_token.refresh_token,
            token_uri=google_token.token_uri,
            client_id=google_token.client_id,
            client_secret=google_token.client_secret,
            scopes=google_token.scopes
        )
        
        # Refresh token if needed
        if credentials.expired:
            credentials.refresh(Request())
            google_token.access_token = credentials.token
            google_token.save()
        
        return build('gmail', 'v1', credentials=credentials)
        
    except GoogleToken.DoesNotExist:
        return None

def create_persistent_session(user, jwt_token, request):
    """Create a persistent session for the user"""
    # Generate unique session key
    session_key = str(uuid.uuid4())
    
    # Extract device info
    device_info = {
        'user_agent': request.META.get('HTTP_USER_AGENT', ''),
        'ip_address': request.META.get('REMOTE_ADDR', ''),
        'created_from': 'oauth_callback'
    }
    
    # Create session
    session = UserSession.objects.create(
        user=user,
        session_key=session_key,
        jwt_token=jwt_token,
        expires_at=timezone.now() + timedelta(days=30),  # 30 days persistence
        device_info=device_info
    )
    
    # Store session key in Django session
    request.session['persistent_session_key'] = session_key
    request.session['user_id'] = user.id
    
    return session

def get_user_from_persistent_session(request):
    """Get user from persistent session"""
    # First try regular session auth
    user = get_user_from_request(request)
    if user:
        return user
    
    # Try persistent session
    session_key = request.session.get('persistent_session_key')
    if session_key:
        try:
            user_session = UserSession.objects.get(
                session_key=session_key,
                is_active=True
            )
            
            if user_session.is_valid():
                # Update last accessed
                user_session.last_accessed = timezone.now()
                user_session.save()
                
                # Set current user
                request.user = user_session.user
                return user_session.user
            else:
                # Session expired, clean it up
                user_session.delete()
                if 'persistent_session_key' in request.session:
                    del request.session['persistent_session_key']
                    
        except UserSession.DoesNotExist:
            pass
    
    return None


def get_deeptalk_user_from_request(request):

    from deeptalk.models import DeepTalkUser  # Import here to avoid circular import
    # This assumes you have JWT authentication set up
    if hasattr(request, 'user') and request.user.is_authenticated:
        try:
            deeptalk_user, created = DeepTalkUser.objects.get_or_create(
                user=request.user,
                defaults={
                    'timezone': 'UTC',
                    'subscription_tier': 'free'
                }
            )
            return deeptalk_user
        except Exception as e:
            print(f"Error getting DeepTalk user: {e}")
    return None

def create_task_log(task, user, action, previous_values=None, new_values=None, triggered_by='user'):
    """Create a task log entry"""
    TaskLog.objects.create(
        task=task,
        user=user,
        action=action,
        previous_values=previous_values,
        new_values=new_values,
        triggered_by=triggered_by
    )


# ===================================
# OAUTH ENDPOINTS
# ===================================

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def google_auth_url(request):
    """Get Google OAuth authorization URL"""
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    return Response({'auth_url': auth_url})

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def google_callback_enhanced(request):
    """Enhanced Google OAuth callback with proper token handling"""
    try:
        authorization_code = request.GET.get('code')
        if not authorization_code:
            return JsonResponse({'error': 'Authorization code not found'}, status=400)
        
        # Exchange authorization code for tokens
        flow.fetch_token(authorization_response=request.build_absolute_uri())
        credentials = flow.credentials
        
        # Get user info from Google
        user_info_service = build('oauth2', 'v2', credentials=credentials)
        user_info = user_info_service.userinfo().get().execute()
        
        # Create or get user
        user, created = User.objects.get_or_create(
            email=user_info['email'],
            defaults={
                'username': user_info['email'],
                'first_name': user_info.get('given_name', ''),
                'last_name': user_info.get('family_name', ''),
            }
        )
        
        # Calculate token expiration
        expires_at = timezone.now() + timedelta(seconds=3600)  # 1 hour default
        if credentials.expiry:
            expires_at = credentials.expiry.replace(tzinfo=dt_timezone.utc)
        
        # Store or update Google tokens
        google_token, token_created = GoogleToken.objects.update_or_create(
            user=user,
            defaults={
                'access_token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes,
                'expires_at': expires_at,
                'is_active': True,
            }
        )
        
        # Create AI configuration if new user
        if created:
            AIConfiguration.objects.get_or_create(user=user)
        
        # Log the user in
        login(request, user)
        
        # Store session data
        request.session['user_email'] = user.email
        request.session['has_gmail_access'] = True
        request.session['login_time'] = datetime.now().isoformat()
        
        # Create JWT token
        jwt_token = create_jwt_token(user)
        
        # Create persistent session
        persistent_session = create_persistent_session(user, jwt_token, request)
        
        # Redirect with clean URL (no OAuth state)
        frontend_url = f"http://localhost:3000/?token={jwt_token}"
        return HttpResponseRedirect(frontend_url)
        
    except Exception as e:
        print(f"OAuth callback error: {e}")
        import traceback
        traceback.print_exc()
        
        # Redirect to frontend with error
        error_url = f"http://localhost:3000/?error={str(e)}"
        return HttpResponseRedirect(error_url)

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def verify_token(request):
    """Enhanced token verification with expiry handling"""
    
    if request.method == 'OPTIONS':
        response = JsonResponse({'status': 'ok'})
        response['Access-Control-Allow-Origin'] = 'http://localhost:3000'
        response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    try:
        token = None
        
        # Get token from request body or header
        if request.body:
            try:
                body_data = json.loads(request.body)
                token = body_data.get('token')
            except json.JSONDecodeError:
                pass
        
        if not token:
            auth_header = request.META.get('HTTP_AUTHORIZATION')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        # Try JWT token verification
        if token:
            try:
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
                
                # Check expiry
                if payload['exp'] < datetime.utcnow().timestamp():
                    response = JsonResponse({
                        'error': 'Token has expired',
                        'expired': True,
                        'exp_time': payload['exp']
                    }, status=401)
                    response['Access-Control-Allow-Origin'] = 'http://localhost:3000'
                    response['Access-Control-Allow-Credentials'] = 'true'
                    return response
                
                user = User.objects.get(id=payload['user_id'])
                
                # Check Google token validity
                gmail_access = False
                try:
                    google_token = GoogleToken.objects.get(user=user, is_active=True)
                    if not google_token.is_expired():
                        gmail_access = True
                    else:
                        # Try to refresh Google token
                        if await_refresh_google_token(google_token):
                            gmail_access = True
                except GoogleToken.DoesNotExist:
                    pass
                
                response_data = {
                    'user_id': user.id,
                    'email': user.email,
                    'has_gmail_access': gmail_access,
                    'login_method': 'jwt',
                    'token_exp': payload['exp'],
                    'time_until_exp': payload['exp'] - datetime.utcnow().timestamp()
                }
                
                response = JsonResponse(response_data)
                response['Access-Control-Allow-Origin'] = 'http://localhost:3000'
                response['Access-Control-Allow-Credentials'] = 'true'
                return response
                
            except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, User.DoesNotExist) as e:
                error_msg = 'Token has expired' if isinstance(e, jwt.ExpiredSignatureError) else 'Invalid token'
                response = JsonResponse({
                    'error': error_msg,
                    'expired': isinstance(e, jwt.ExpiredSignatureError)
                }, status=401)
                response['Access-Control-Allow-Origin'] = 'http://localhost:3000'
                response['Access-Control-Allow-Credentials'] = 'true'
                return response
        
        # Fallback to session authentication
        if request.user.is_authenticated:
            try:
                google_token = GoogleToken.objects.get(user=request.user, is_active=True)
                gmail_access = not google_token.is_expired()
                if google_token.is_expired():
                    # Try to refresh
                    gmail_access = await_refresh_google_token(google_token)
            except GoogleToken.DoesNotExist:
                gmail_access = False
            
            response_data = {
                'user_id': request.user.id,
                'email': request.user.email,
                'has_gmail_access': gmail_access,
                'login_method': 'session'
            }
            response = JsonResponse(response_data)
            response['Access-Control-Allow-Origin'] = 'http://localhost:3000'
            response['Access-Control-Allow-Credentials'] = 'true'
            return response
        
        response = JsonResponse({'error': 'Not authenticated'}, status=401)
        response['Access-Control-Allow-Origin'] = 'http://localhost:3000'
        response['Access-Control-Allow-Credentials'] = 'true'
        return response
        
    except Exception as e:
        response = JsonResponse({'error': f'Server error: {str(e)}'}, status=500)
        response['Access-Control-Allow-Origin'] = 'http://localhost:3000'
        response['Access-Control-Allow-Credentials'] = 'true'
        return response

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def refresh_token(request):
    """Enhanced token refresh with Google token validation"""
    user = get_user_from_request(request)
    if not user:
        # Try to get user from session if JWT fails
        if request.user.is_authenticated:
            user = request.user
        else:
            return Response({'error': 'Not authenticated'}, status=401)
    
    # Check if user has valid Google token and refresh if needed
    try:
        google_token = GoogleToken.objects.get(user=user, is_active=True)
        if google_token.is_expired():
            if not await_refresh_google_token(google_token):
                return Response({
                    'error': 'Google token expired and could not be refreshed. Please sign in again.',
                    'require_reauth': True
                }, status=401)
    except GoogleToken.DoesNotExist:
        pass
    
    # Create new JWT token
    jwt_token = create_jwt_token(user)
    return Response({
        'token': jwt_token,
        'expires_in': 7200  # 2 hours
    })

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def logout_user(request):
    """Logout user and clear session"""
    logout(request)
    return Response({'message': 'Logged out successfully'})

# ===================================
# GMAIL API ENDPOINTS
# ===================================

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def gmail_profile(request):
    """Enhanced Gmail profile with token refresh"""
    user = get_user_from_request(request)
    if not user:
        return Response({'error': 'Authentication required'}, status=401)
    
    try:
        google_token = GoogleToken.objects.get(user=user, is_active=True)
        
        # Check if token is expired and try to refresh
        if google_token.is_expired():
            if not await_refresh_google_token(google_token):
                return Response({
                    'error': 'Gmail access token expired. Please sign in again.',
                    'require_reauth': True
                }, status=401)
        
        service = get_gmail_service(user)
        if not service:
            return Response({'error': 'Gmail access not found'}, status=404)
        
        profile = service.users().getProfile(userId='me').execute()
        return Response({
            'email': profile['emailAddress'],
            'messages_total': profile['messagesTotal'],
            'threads_total': profile['threadsTotal'],
            'history_id': profile['historyId']
        })
        
    except GoogleToken.DoesNotExist:
        return Response({
            'error': 'No Gmail access found. Please sign in again.',
            'require_reauth': True
        }, status=401)
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def gmail_messages(request):
    """Enhanced Gmail messages with token refresh"""
    user = get_user_from_request(request)
    if not user:
        return Response({'error': 'Authentication required'}, status=401)
    
    try:
        google_token = GoogleToken.objects.get(user=user, is_active=True)
        
        # Check if token is expired and try to refresh
        if google_token.is_expired():
            if not await_refresh_google_token(google_token):
                return Response({
                    'error': 'Gmail access token expired. Please sign in again.',
                    'require_reauth': True
                }, status=401)
        
        service = get_gmail_service(user)
        if not service:
            return Response({'error': 'Gmail access not found'}, status=404)
        
        max_results = int(request.GET.get('max_results', 10))
        query = request.GET.get('query', '')
        
        # Get messages list
        kwargs = {'userId': 'me', 'maxResults': max_results}
        if query:
            kwargs['q'] = query
            
        results = service.users().messages().list(**kwargs).execute()
        messages = results.get('messages', [])
        
        # Get detailed message info
        detailed_messages = []
        for message in messages[:5]:  # Limit to 5 for basic endpoint
            try:
                msg = service.users().messages().get(
                    userId='me',
                    id=message['id']
                ).execute()
                
                headers = msg['payload'].get('headers', [])
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
                
                detailed_messages.append({
                    'id': msg['id'],
                    'subject': subject,
                    'from': from_email,
                    'date': date,
                    'snippet': msg.get('snippet', '')
                })
            except Exception as e:
                print(f"Error processing message {message['id']}: {str(e)}")
                continue
        
        return Response({
            'messages': detailed_messages,
            'total_count': len(messages)
        })
        
    except GoogleToken.DoesNotExist:
        return Response({
            'error': 'No Gmail access found. Please sign in again.',
            'require_reauth': True
        }, status=401)
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def gmail_all_messages(request):
    """Get all Gmail messages with pagination"""
    user = get_user_from_request(request)
    if not user:
        return Response({'error': 'Authentication required'}, status=401)
    
    service = get_gmail_service(user)
    if not service:
        return Response({'error': 'Gmail access not found'}, status=404)
    
    try:
        # Get parameters
        page_token = request.GET.get('page_token', None)
        max_results = int(request.GET.get('max_results', 50))
        query = request.GET.get('query', '')
        
        # Get messages list
        kwargs = {'userId': 'me', 'maxResults': max_results}
        if query:
            kwargs['q'] = query
        if page_token:
            kwargs['pageToken'] = page_token
            
        results = service.users().messages().list(**kwargs).execute()
        messages = results.get('messages', [])
        next_page_token = results.get('nextPageToken')
        
        # Get detailed message info
        detailed_messages = []
        for message in messages:
            try:
                msg = service.users().messages().get(
                    userId='me',
                    id=message['id']
                ).execute()
                
                headers = msg['payload'].get('headers', [])
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                to_email = next((h['value'] for h in headers if h['name'] == 'To'), 'Unknown')
                date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
                
                # Get message body
                body = extract_message_body(msg)
                
                detailed_messages.append({
                    'id': msg['id'],
                    'thread_id': msg['threadId'],
                    'subject': subject,
                    'from': from_email,
                    'to': to_email,
                    'date': date,
                    'snippet': msg.get('snippet', ''),
                    'body': body,
                    'labels': msg.get('labelIds', [])
                })
                
            except Exception as e:
                print(f"Error processing message {message['id']}: {str(e)}")
                continue
        
        return Response({
            'messages': detailed_messages,
            'next_page_token': next_page_token,
            'total_count': len(detailed_messages)
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def gmail_search_messages(request):
    """Search Gmail messages with advanced queries"""
    user = get_user_from_request(request)
    if not user:
        return Response({'error': 'Authentication required'}, status=401)
    
    service = get_gmail_service(user)
    if not service:
        return Response({'error': 'Gmail access not found'}, status=404)
    
    try:
        query = request.GET.get('query', '')
        max_results = int(request.GET.get('max_results', 50))
        
        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=max_results
        ).execute()
        
        messages = results.get('messages', [])
        
        detailed_messages = []
        for message in messages:
            try:
                msg = service.users().messages().get(
                    userId='me',
                    id=message['id']
                ).execute()
                
                headers = msg['payload'].get('headers', [])
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
                
                detailed_messages.append({
                    'id': msg['id'],
                    'subject': subject,
                    'from': from_email,
                    'date': date,
                    'snippet': msg.get('snippet', ''),
                    'labels': msg.get('labelIds', [])
                })
            except Exception as e:
                print(f"Error processing message {message['id']}: {str(e)}")
                continue
        
        return Response({
            'messages': detailed_messages,
            'query': query,
            'total_count': len(detailed_messages)
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def gmail_message_detail(request, message_id):
    """Get full details of a specific message"""
    user = get_user_from_request(request)
    if not user:
        return Response({'error': 'Authentication required'}, status=401)
    
    service = get_gmail_service(user)
    if not service:
        return Response({'error': 'Gmail access not found'}, status=404)
    
    try:
        # Get full message
        msg = service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()
        
        headers = msg['payload'].get('headers', [])
        
        # Extract all headers
        message_headers = {}
        for header in headers:
            message_headers[header['name']] = header['value']
        
        # Get message body and attachments
        body = extract_message_body(msg)
        attachments = extract_attachments_info(msg)
        
        return Response({
            'id': msg['id'],
            'thread_id': msg['threadId'],
            'headers': message_headers,
            'body': body,
            'snippet': msg.get('snippet', ''),
            'labels': msg.get('labelIds', []),
            'attachments': attachments,
            'size_estimate': msg.get('sizeEstimate', 0)
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def gmail_stream_all_messages(request):
    """Stream all Gmail messages for large mailboxes"""
    user = get_user_from_request(request)
    if not user:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    service = get_gmail_service(user)
    if not service:
        return JsonResponse({'error': 'Gmail access not found'}, status=404)
    
    def generate_messages():
        try:
            page_token = None
            total_processed = 0
            
            while True:
                # Get batch of message IDs
                kwargs = {'userId': 'me', 'maxResults': 100}
                if page_token:
                    kwargs['pageToken'] = page_token
                    
                results = service.users().messages().list(**kwargs).execute()
                messages = results.get('messages', [])
                
                if not messages:
                    break
                
                # Process each message in batch
                for message in messages:
                    try:
                        msg = service.users().messages().get(
                            userId='me',
                            id=message['id']
                        ).execute()
                        
                        headers = msg['payload'].get('headers', [])
                        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                        from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                        date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
                        
                        message_data = {
                            'id': msg['id'],
                            'subject': subject,
                            'from': from_email,
                            'date': date,
                            'snippet': msg.get('snippet', ''),
                            'processed': total_processed + 1
                        }
                        
                        yield f"data: {json.dumps(message_data)}\n\n"
                        total_processed += 1
                        
                        # Rate limiting
                        time.sleep(0.1)
                        
                    except Exception as e:
                        error_data = {
                            'error': f"Error processing message: {str(e)}",
                            'processed': total_processed
                        }
                        yield f"data: {json.dumps(error_data)}\n\n"
                
                page_token = results.get('nextPageToken')
                if not page_token:
                    break
            
            # Send completion message
            completion_data = {
                'completed': True,
                'total_processed': total_processed
            }
            yield f"data: {json.dumps(completion_data)}\n\n"
            
        except Exception as e:
            error_data = {'error': str(e)}
            yield f"data: {json.dumps(error_data)}\n\n"
    
    response = StreamingHttpResponse(
        generate_messages(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['Connection'] = 'keep-alive'
    response['Access-Control-Allow-Origin'] = 'http://localhost:3000'
    response['Access-Control-Allow-Credentials'] = 'true'
    return response

# ===================================
# HELPER FUNCTIONS
# ===================================

def extract_message_body(message):
    """Extract text body from Gmail message"""
    body = ""
    
    if 'parts' in message['payload']:
        for part in message['payload']['parts']:
            if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                break
            elif part['mimeType'] == 'text/html' and 'data' in part['body']:
                body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
    else:
        if (message['payload']['mimeType'] == 'text/plain' and 
            'data' in message['payload']['body']):
            body = base64.urlsafe_b64decode(
                message['payload']['body']['data']
            ).decode('utf-8')
    
    return body

def extract_attachments_info(message):
    """Extract attachment information from Gmail message"""
    attachments = []
    
    if 'parts' in message['payload']:
        for part in message['payload']['parts']:
            if part.get('filename'):
                attachment_info = {
                    'filename': part['filename'],
                    'mime_type': part['mimeType'],
                    'size': part['body'].get('size', 0),
                    'attachment_id': part['body'].get('attachmentId')
                }
                attachments.append(attachment_info)
    
    return attachments

# ===================================
# TEST AND TOKEN STATUS ENDPOINTS
# ===================================

@csrf_exempt
def test_csrf(request):
    """Simple test endpoint to verify CSRF bypass is working"""
    
    if request.method == 'OPTIONS':
        response = JsonResponse({'status': 'ok'})
        response['Access-Control-Allow-Origin'] = 'http://localhost:3000'
        response['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    return JsonResponse({
        'status': 'success',
        'message': 'CSRF bypass is working!',
        'method': request.method,
        'path': request.path,
        'user_authenticated': request.user.is_authenticated,
        'csrf_exempt': getattr(request, '_dont_enforce_csrf_checks', False)
    })

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def token_status(request):
    """Check current token status and expiry"""
    user = get_user_from_request(request)
    if not user:
        return Response({'error': 'Not authenticated'}, status=401)
    
    try:
        # Get JWT token info
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            jwt_exp = payload.get('exp')
            jwt_time_left = jwt_exp - datetime.utcnow().timestamp() if jwt_exp else 0
        else:
            jwt_exp = None
            jwt_time_left = 0
        
        # Get Google token info
        google_token_info = None
        try:
            google_token = GoogleToken.objects.get(user=user, is_active=True)
            google_token_info = {
                'expires_at': google_token.expires_at.isoformat() if google_token.expires_at else None,
                'is_expired': google_token.is_expired(),
                'time_until_expiry': (google_token.expires_at - timezone.now()).total_seconds() if google_token.expires_at else 0
            }
        except GoogleToken.DoesNotExist:
            pass
        
        return Response({
            'user_id': user.id,
            'email': user.email,
            'jwt_token': {
                'expires_at': datetime.utcfromtimestamp(jwt_exp).isoformat() if jwt_exp else None,
                'time_left_seconds': jwt_time_left
            },
            'google_token': google_token_info,
            'session_active': request.user.is_authenticated
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=500)

# ===================================
# AI AGENT ENDPOINTS
# ===================================

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def ai_summarize_emails(request):
    """AI-powered email summarization"""
    user = get_user_from_request(request)
    if not user:
        return Response({'error': 'Authentication required'}, status=401)
    
    try:
        # Get OpenAI API key from request or settings
        openai_key = request.data.get('openai_api_key') or getattr(settings, 'OPENAI_API_KEY', None)
        if not openai_key:
            return Response({'error': 'OpenAI API key required'}, status=400)
        
        # Get parameters
        query = request.data.get('query', '')
        num_emails = request.data.get('num_emails', 10)
        summary_type = request.data.get('type', 'recent')  # recent, unread, important, daily, custom
        
        # Create AI agent
        agent = create_ai_agent(user, openai_key)
        
        # Get summary based on type
        if summary_type == 'unread':
            summary = agent.get_unread_summary()
        elif summary_type == 'important':
            summary = agent.get_important_summary()
        elif summary_type == 'daily':
            summary = agent.get_daily_summary()
        elif summary_type == 'custom':
            summary = agent.summarize_emails(query=query, num_emails=num_emails)
        else:  # recent
            summary = agent.summarize_emails(num_emails=num_emails)
        
        return Response({
            'summary': summary,
            'type': summary_type,
            'query': query,
            'num_emails': num_emails
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def ai_analyze_email(request, email_id):
    """AI-powered individual email analysis"""
    user = get_user_from_request(request)
    if not user:
        return Response({'error': 'Authentication required'}, status=401)
    
    try:
        # Get OpenAI API key
        openai_key = request.data.get('openai_api_key') or getattr(settings, 'OPENAI_API_KEY', None)
        if not openai_key:
            return Response({'error': 'OpenAI API key required'}, status=400)
        
        # Create AI agent and analyze email
        agent = create_ai_agent(user, openai_key)
        analysis = agent.analyze_specific_email(email_id)
        
        return Response({
            'email_id': email_id,
            'analysis': analysis
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def ai_chat_about_emails(request):
    """Chat with AI about emails"""
    user = get_user_from_request(request)
    if not user:
        return Response({'error': 'Authentication required'}, status=401)
    
    try:
        # Get parameters
        openai_key = request.data.get('openai_api_key') or getattr(settings, 'OPENAI_API_KEY', None)
        if not openai_key:
            return Response({'error': 'OpenAI API key required'}, status=400)
        
        user_question = request.data.get('question', '')
        if not user_question:
            return Response({'error': 'Question is required'}, status=400)
        
        # Create AI agent
        agent = create_ai_agent(user, openai_key)
        
        # Create a conversational prompt
        system_template = """You are an AI assistant that helps users understand and manage their emails.
        You have access to the user's Gmail data through tools. You can search emails, get recent emails,
        and provide insights. Be helpful and conversational."""
        
        human_template = f"""User question: {user_question}
        
        Please help the user with their email-related question. You can use the available tools to
        search emails, get recent emails, or provide general email management advice."""
        
        system_message = SystemMessage(content=system_template)
        human_message = HumanMessage(content=human_template)
        
        response = agent.llm([system_message, human_message])
        
        return Response({
            'question': user_question,
            'response': response.content
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def ai_email_insights(request):
    """Get AI insights about email patterns"""
    user = get_user_from_request(request)
    if not user:
        return Response({'error': 'Authentication required'}, status=401)
    
    try:
        # Get OpenAI API key
        openai_key = request.GET.get('openai_api_key') or getattr(settings, 'OPENAI_API_KEY', None)
        if not openai_key:
            return Response({'error': 'OpenAI API key required'}, status=400)
        
        # Create AI agent
        agent = create_ai_agent(user, openai_key)
        
        # Get various insights
        insights = {
            'unread_summary': agent.get_unread_summary(),
            'daily_summary': agent.get_daily_summary(),
            'important_summary': agent.get_important_summary(),
        }
        
        return Response(insights)
        
    except Exception as e:
        return Response({'error': str(e)}, status=500)

# ===================================
# SESSION MANAGEMENT ENDPOINTS
# ===================================

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def check_persistent_session(request):
    """Check if user has a valid persistent session"""
    user = get_user_from_persistent_session(request)
    
    if user:
        # Get session info
        session_key = request.session.get('persistent_session_key')
        try:
            user_session = UserSession.objects.get(session_key=session_key)
            
            return Response({
                'authenticated': True,
                'user_id': user.id,
                'email': user.email,
                'session_expires': user_session.expires_at.isoformat(),
                'last_accessed': user_session.last_accessed.isoformat(),
                'has_gmail_access': GoogleToken.objects.filter(user=user, is_active=True).exists(),
                'session_key': session_key[:8] + '...',  # Partial key for debugging
            })
        except UserSession.DoesNotExist:
            pass
    
    return Response({'authenticated': False}, status=401)

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def extend_session(request):
    """Extend user session"""
    user = get_user_from_persistent_session(request)
    if not user:
        return Response({'error': 'Authentication required'}, status=401)
    
    try:
        session_key = request.session.get('persistent_session_key')
        user_session = UserSession.objects.get(session_key=session_key)
        
        # Extend session by 30 days
        user_session.extend_session(days=30)
        
        return Response({
            'message': 'Session extended successfully',
            'new_expiry': user_session.expires_at.isoformat()
        })
        
    except UserSession.DoesNotExist:
        return Response({'error': 'Session not found'}, status=404)

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def revoke_session(request):
    """Revoke current session"""
    session_key = request.session.get('persistent_session_key')
    if session_key:
        try:
            user_session = UserSession.objects.get(session_key=session_key)
            user_session.is_active = False
            user_session.save()
            
            # Clear Django session
            request.session.flush()
            
            return Response({'message': 'Session revoked successfully'})
        except UserSession.DoesNotExist:
            pass
    
    return Response({'message': 'No active session found'})

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def list_user_sessions(request):
    """List all active sessions for the user"""
    user = get_user_from_persistent_session(request)
    if not user:
        return Response({'error': 'Authentication required'}, status=401)
    
    sessions = UserSession.objects.filter(user=user, is_active=True)
    
    session_data = []
    for session in sessions:
        session_data.append({
            'session_key': session.session_key[:8] + '...',
            'created_at': session.created_at.isoformat(),
            'last_accessed': session.last_accessed.isoformat(),
            'expires_at': session.expires_at.isoformat(),
            'device_info': session.device_info,
            'is_current': session.session_key == request.session.get('persistent_session_key')
        })
    
    return Response({
        'sessions': session_data,
        'total_sessions': len(session_data)
    })

# ===================================
# TOKEN MANAGEMENT
# ===================================

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def refresh_google_token(request):
    """Refresh Google access token if needed"""
    user = get_user_from_persistent_session(request)
    if not user:
        return Response({'error': 'Authentication required'}, status=401)
    
    try:
        google_token = GoogleToken.objects.get(user=user, is_active=True)
        
        if google_token.is_expired():
            # Create credentials object
            credentials = Credentials(
                token=google_token.access_token,
                refresh_token=google_token.refresh_token,
                token_uri=google_token.token_uri,
                client_id=google_token.client_id,
                client_secret=google_token.client_secret,
                scopes=google_token.scopes
            )
            
            # Refresh the token
            credentials.refresh(Request())
            
            # Update stored token
            google_token.access_token = credentials.token
            google_token.expires_at = timezone.now() + timedelta(seconds=3600)  # 1 hour
            google_token.save()
            
            return Response({
                'message': 'Token refreshed successfully',
                'expires_at': google_token.expires_at.isoformat()
            })
        else:
            return Response({
                'message': 'Token is still valid',
                'expires_at': google_token.expires_at.isoformat()
            })
            
    except GoogleToken.DoesNotExist:
        return Response({'error': 'Google token not found'}, status=404)
    except Exception as e:
        return Response({'error': f'Token refresh failed: {str(e)}'}, status=500)

# ===================================
# LEGACY CALLBACK FOR COMPATIBILITY
# ===================================

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def google_callback(request):
    """Legacy callback - redirects to enhanced version"""
    return google_callback_enhanced(request)

# ===================================
# TASK MANAGEMENT ENDPOINTS
# ===================================

@csrf_exempt
@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def tasks_list_create(request):
    """List all tasks or create a new task"""
    deeptalk_user = get_deeptalk_user_from_request(request)
    if not deeptalk_user:
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    if request.method == 'GET':
        # Get query parameters
        status_filter = request.GET.get('status', None)
        category_filter = request.GET.get('category', None)
        priority_filter = request.GET.get('priority', None)
        search_query = request.GET.get('search', None)
        
        # Base queryset - exclude soft deleted
        tasks = Task.objects.filter(user=deeptalk_user, deleted_at__isnull=True)
        
        # Apply filters
        if status_filter:
            tasks = tasks.filter(status=status_filter)
        if category_filter:
            tasks = tasks.filter(category__name=category_filter)
        if priority_filter:
            tasks = tasks.filter(priority=int(priority_filter))
        if search_query:
            tasks = tasks.filter(
                Q(name__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(tags__contains=[search_query])
            )
        
        # Serialize and return
        serializer = TaskSerializer(tasks, many=True)
        return Response({
            'tasks': serializer.data,
            'total_count': tasks.count()
        })
    
    elif request.method == 'POST':
        # Create new task
        data = request.data.copy()
        data['user'] = deeptalk_user.id
        
        serializer = TaskSerializer(data=data)
        if serializer.is_valid():
            task = serializer.save()
            
            # Create task log
            create_task_log(task, deeptalk_user, 'created', 
                          new_values=serializer.data)
            
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@csrf_exempt
@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([AllowAny])
def task_detail(request, task_id):
    """Retrieve, update or delete a specific task"""
    deeptalk_user = get_deeptalk_user_from_request(request)
    if not deeptalk_user:
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        task = Task.objects.get(id=task_id, user=deeptalk_user, deleted_at__isnull=True)
    except Task.DoesNotExist:
        return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        serializer = TaskSerializer(task)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        # Store previous values for logging
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
            
            task = serializer.save()
            
            # Create task log
            create_task_log(task, deeptalk_user, 'updated', 
                          previous_values=previous_values, 
                          new_values=serializer.data)
            
            return Response(serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        # Soft delete
        previous_values = TaskSerializer(task).data
        task.soft_delete()
        
        # Create task log
        create_task_log(task, deeptalk_user, 'deleted', 
                      previous_values=previous_values)
        
        return Response({'message': 'Task deleted successfully'}, status=status.HTTP_204_NO_CONTENT)

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def task_toggle_status(request, task_id):
    """Toggle task between pending and completed"""
    deeptalk_user = get_deeptalk_user_from_request(request)
    if not deeptalk_user:
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        task = Task.objects.get(id=task_id, user=deeptalk_user, deleted_at__isnull=True)
    except Task.DoesNotExist:
        return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)
    
    previous_values = TaskSerializer(task).data
    
    # Toggle status
    if task.status == 'completed':
        task.status = 'pending'
        task.completed_at = None
        task.completion_percentage = 0
        action = 'started'
    else:
        task.status = 'completed'
        task.completed_at = timezone.now()
        task.completion_percentage = 100
        action = 'completed'
    
    task.save()
    
    # Create task log
    create_task_log(task, deeptalk_user, action, 
                  previous_values=previous_values, 
                  new_values=TaskSerializer(task).data)
    
    serializer = TaskSerializer(task)
    return Response(serializer.data)

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def task_stats(request):
    """Get task statistics for the user"""
    deeptalk_user = get_deeptalk_user_from_request(request)
    if not deeptalk_user:
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    # Base queryset
    tasks = Task.objects.filter(user=deeptalk_user, deleted_at__isnull=True)
    
    # Calculate stats
    total = tasks.count()
    pending = tasks.filter(status='pending').count()
    completed = tasks.filter(status='completed').count()
    in_progress = tasks.filter(status='in_progress').count()
    cancelled = tasks.filter(status='cancelled').count()
    
    # Calculate overdue tasks
    overdue = tasks.filter(
        status='pending',
        deadline__lt=timezone.now(),
        deadline__isnull=False
    ).count()
    
    # Category breakdown
    category_stats = tasks.values('category__name').annotate(
        total=Count('id'),
        completed=Count('id', filter=Q(status='completed')),
        pending=Count('id', filter=Q(status='pending'))
    ).order_by('-total')
    
    # Priority breakdown
    priority_stats = {}
    for i in range(1, 6):
        priority_tasks = tasks.filter(priority=i)
        priority_stats[f'priority_{i}'] = {
            'total': priority_tasks.count(),
            'completed': priority_tasks.filter(status='completed').count(),
            'pending': priority_tasks.filter(status='pending').count()
        }
    
    # Completion rate
    completion_rate = round((completed / total * 100) if total > 0 else 0, 2)
    
    # Recent activity (last 7 days)
    last_week = timezone.now() - timedelta(days=7)
    recent_completed = tasks.filter(
        status='completed',
        completed_at__gte=last_week
    ).count()
    recent_created = tasks.filter(created_at__gte=last_week).count()
    
    return Response({
        'total': total,
        'pending': pending,
        'completed': completed,
        'in_progress': in_progress,
        'cancelled': cancelled,
        'overdue': overdue,
        'completion_rate': completion_rate,
        'category_breakdown': list(category_stats),
        'priority_breakdown': priority_stats,
        'recent_activity': {
            'completed_last_week': recent_completed,
            'created_last_week': recent_created
        }
    })

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
    """List all categories or create a new category"""
    deeptalk_user = get_deeptalk_user_from_request(request)
    if not deeptalk_user:
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    if request.method == 'GET':
        # Get user's categories and system categories
        categories = TaskCategory.objects.filter(
            Q(user=deeptalk_user) | Q(is_system_category=True)
        ).distinct()
        
        serializer = TaskCategorySerializer(categories, many=True)
        return Response({'categories': serializer.data})
    
    elif request.method == 'POST':
        data = request.data.copy()
        data['user'] = deeptalk_user.id
        data['is_system_category'] = False  # User categories are never system categories
        
        serializer = TaskCategorySerializer(data=data)
        if serializer.is_valid():
            category = serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@csrf_exempt
@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([AllowAny])
def category_detail(request, category_id):
    """Retrieve, update or delete a specific category"""
    deeptalk_user = get_deeptalk_user_from_request(request)
    if not deeptalk_user:
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        category = TaskCategory.objects.get(
            id=category_id, 
            user=deeptalk_user,
            is_system_category=False  # Only allow editing user categories
        )
    except TaskCategory.DoesNotExist:
        return Response({'error': 'Category not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        serializer = TaskCategorySerializer(category)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = TaskCategorySerializer(category, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        # Check if category is in use
        if Task.objects.filter(category=category, deleted_at__isnull=True).exists():
            return Response({
                'error': 'Cannot delete category that is in use by tasks'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        category.delete()
        return Response({'message': 'Category deleted successfully'}, status=status.HTTP_204_NO_CONTENT)

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
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    # Get or create preferences
    preferences, created = UserPreferences.objects.get_or_create(user=deeptalk_user)
    
    if request.method == 'GET':
        serializer = UserPreferencesSerializer(preferences)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = UserPreferencesSerializer(preferences, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
    
    # Order by relevance (name matches first, then description, etc.)
    tasks = tasks.extra(
        select={
            'relevance': """
                CASE 
                    WHEN name ILIKE %s THEN 1
                    WHEN description ILIKE %s THEN 2
                    WHEN array_to_string(tags, ' ') ILIKE %s THEN 3
                    ELSE 4
                END
            """
        },
        select_params=[f'%{query}%', f'%{query}%', f'%{query}%']
    ).order_by('relevance', '-created_at')
    
    serializer = TaskSerializer(tasks, many=True)
    return Response({
        'tasks': serializer.data,
        'total_count': tasks.count(),
        'query': query
    })
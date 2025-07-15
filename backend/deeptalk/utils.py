import jwt
import logging
from datetime import datetime
from django.contrib.auth.models import User
from django.conf import settings
from .models import DeepTalkUser

logger = logging.getLogger(__name__)

def get_deeptalk_user_from_request(request):
    """Get DeepTalk user from request - FIXED WITH SPECIFIC ERROR HANDLING"""
    
    # Step 1: Try JWT authentication first
    django_user = None
    auth_header = request.META.get('HTTP_AUTHORIZATION')
    
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        logger.debug(f"Found Bearer token: {token[:20]}...")
        
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            logger.debug(f"JWT payload decoded successfully: user_id={payload.get('user_id')}")
        except jwt.ExpiredSignatureError:
            logger.error("JWT token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.error(f"JWT token is invalid: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error decoding JWT: {type(e).__name__}: {e}")
            return None
        
        # Check if token is expired (additional check)
        try:
            if payload['exp'] < datetime.utcnow().timestamp():
                logger.error("JWT token expiration check failed - token is expired")
                return None
        except KeyError:
            logger.error("JWT token missing 'exp' field")
            return None
        except Exception as e:
            logger.error(f"Error checking JWT expiration: {type(e).__name__}: {e}")
            return None
        
        # Get Django user from JWT payload
        try:
            user_id = payload['user_id']
            django_user = User.objects.get(id=user_id)
            logger.debug(f"Found Django user from JWT: {django_user.email}")
        except KeyError:
            logger.error("JWT token missing 'user_id' field")
            return None
        except User.DoesNotExist:
            logger.error(f"Django user with id {payload.get('user_id')} not found")
            return None
        except Exception as e:
            logger.error(f"Error getting Django user from JWT: {type(e).__name__}: {e}")
            return None
    
    # Step 2: Fallback to session authentication if JWT failed
    if not django_user:
        try:
            if hasattr(request, 'user') and request.user.is_authenticated:
                django_user = request.user
                logger.debug(f"Found Django user from session: {django_user.email}")
            else:
                logger.debug("No authenticated user found in session")
        except Exception as e:
            logger.error(f"Error checking session authentication: {type(e).__name__}: {e}")
            return None
    
    # Step 3: If no Django user found, return None
    if not django_user:
        logger.debug("No authenticated Django user found")
        return None
    
    # Step 4: Get or create DeepTalk user
    try:
        deeptalk_user, created = DeepTalkUser.objects.get_or_create(
            user=django_user,
            defaults={
                'timezone': 'UTC',
                'subscription_tier': 'free'
            }
        )
        
        if created:
            logger.info(f"Created new DeepTalk user for {django_user.email}")
        else:
            logger.debug(f"Found existing DeepTalk user for {django_user.email}")
        
        return deeptalk_user
        
    except Exception as e:
        logger.error(f"Error getting/creating DeepTalk user for {django_user.email}: {type(e).__name__}: {e}")
        return None


def get_deeptalk_user_from_request_simple(request):
    """
    Simplified version if you don't need JWT - just session auth
    """
    try:
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            logger.debug("No authenticated user in request")
            return None
        
        django_user = request.user
        logger.debug(f"Found authenticated Django user: {django_user.email}")
        
        # Get or create DeepTalk user
        deeptalk_user, created = DeepTalkUser.objects.get_or_create(
            user=django_user,
            defaults={
                'timezone': 'UTC',
                'subscription_tier': 'free'
            }
        )
        
        if created:
            logger.info(f"Created new DeepTalk user for {django_user.email}")
        
        return deeptalk_user
        
    except Exception as e:
        logger.error(f"Error in simple auth: {type(e).__name__}: {e}")
        return None


def debug_request_auth(request):
    """
    Debug function to see what authentication data is available
    """
    debug_info = {
        'has_user_attr': hasattr(request, 'user'),
        'user_authenticated': hasattr(request, 'user') and request.user.is_authenticated,
        'user_id': request.user.id if hasattr(request, 'user') and request.user.is_authenticated else None,
        'user_email': request.user.email if hasattr(request, 'user') and request.user.is_authenticated else None,
        'session_keys': list(request.session.keys()) if hasattr(request, 'session') else [],
        'auth_header': request.META.get('HTTP_AUTHORIZATION', 'None'),
        'content_type': request.META.get('CONTENT_TYPE', 'None'),
        'method': request.method,
    }
    
    logger.debug(f"Request auth debug: {debug_info}")
    return debug_info
# ===================================
# backend/gmail_auth/middleware.py - DEBUG AND CORS MIDDLEWARE
# ===================================

import logging

logger = logging.getLogger(__name__)

class DebugMiddleware:
    """Middleware for debugging requests and CORS issues"""
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Log request details for debugging
        if request.path.startswith('/auth/') or request.path.startswith('/gmail/'):
            logger.info(f"Request: {request.method} {request.path}")
            logger.info(f"Headers: {dict(request.META)}")
            if request.body:
                logger.info(f"Body: {request.body}")

        response = self.get_response(request)
        
        # Add CORS headers to all responses from our endpoints
        if request.path.startswith('/auth/') or request.path.startswith('/gmail/'):
            response['Access-Control-Allow-Origin'] = 'http://localhost:3000'
            response['Access-Control-Allow-Credentials'] = 'true'
            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-CSRFToken'
            
            logger.info(f"Response: {response.status_code}")

        return response
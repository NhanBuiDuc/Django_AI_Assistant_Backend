from django.utils.deprecation import MiddlewareMixin

class CSRFBypassMiddleware(MiddlewareMixin):
    """
    Middleware to completely bypass CSRF protection for API endpoints
    """
    
    def process_request(self, request):
        # List of paths that should bypass CSRF
        csrf_exempt_paths = [
            '/auth/',
            '/gmail/',
        ]
        
        # Check if the current path should bypass CSRF
        if any(request.path.startswith(path) for path in csrf_exempt_paths):
            # Mark this request as CSRF exempt
            setattr(request, '_dont_enforce_csrf_checks', True)
        
        return None
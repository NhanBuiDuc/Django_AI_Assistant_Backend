from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from . import views

urlpatterns = [
    # Test endpoint
    path('test-csrf/', csrf_exempt(views.test_csrf), name='test_csrf'),
    
    # OAuth endpoints - all CSRF exempt for API usage
    path('auth/google/', csrf_exempt(views.google_auth_url), name='google_auth_url'),
    path('auth/google/callback/', csrf_exempt(views.google_callback_enhanced), name='google_callback_enhanced'),
    path('auth/google/callback-legacy/', csrf_exempt(views.google_callback), name='google_callback_legacy'),  # Legacy support
    path('auth/verify-token/', csrf_exempt(views.verify_token), name='verify_token'),
    path('auth/refresh-token/', csrf_exempt(views.refresh_token), name='refresh_token'),
    path('auth/logout/', csrf_exempt(views.logout_user), name='logout_user'),
    path('auth/token-status/', csrf_exempt(views.token_status), name='token_status'),
    
    # Enhanced session management
    path('auth/check-session/', csrf_exempt(views.check_persistent_session), name='check_persistent_session'),
    path('auth/extend-session/', csrf_exempt(views.extend_session), name='extend_session'),
    path('auth/revoke-session/', csrf_exempt(views.revoke_session), name='revoke_session'),
    path('auth/list-sessions/', csrf_exempt(views.list_user_sessions), name='list_user_sessions'),
    path('auth/refresh-google-token/', csrf_exempt(views.refresh_google_token), name='refresh_google_token'),
    
    # Gmail API endpoints - all CSRF exempt for API usage
    path('gmail/profile/', csrf_exempt(views.gmail_profile), name='gmail_profile'),
    path('gmail/messages/', csrf_exempt(views.gmail_messages), name='gmail_messages'),
    path('gmail/all-messages/', csrf_exempt(views.gmail_all_messages), name='gmail_all_messages'),
    path('gmail/search/', csrf_exempt(views.gmail_search_messages), name='gmail_search_messages'),
    path('gmail/message/<str:message_id>/', csrf_exempt(views.gmail_message_detail), name='gmail_message_detail'),
    path('gmail/stream-messages/', csrf_exempt(views.gmail_stream_all_messages), name='gmail_stream_messages'),

    # AI Agent endpoints
    # path('ai/summarize-emails/', csrf_exempt(views.ai_summarize_emails), name='ai_summarize_emails'),
    # path('ai/analyze-email/<str:email_id>/', csrf_exempt(views.ai_analyze_email), name='ai_analyze_email'),
    # path('ai/chat-about-emails/', csrf_exempt(views.ai_chat_about_emails), name='ai_chat_about_emails'),
    # path('ai/email-insights/', csrf_exempt(views.ai_email_insights), name='ai_email_insights'),
]
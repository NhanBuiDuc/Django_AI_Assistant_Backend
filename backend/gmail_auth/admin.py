from django.contrib import admin
from .models import GoogleToken

@admin.register(GoogleToken)
class GoogleTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'updated_at')
    readonly_fields = ('access_token', 'refresh_token', 'client_secret')
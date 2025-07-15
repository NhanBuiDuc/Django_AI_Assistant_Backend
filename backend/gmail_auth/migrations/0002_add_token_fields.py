# backend/gmail_auth/migrations/0002_add_token_fields.py - CORRECTED VERSION

from django.db import migrations, models
import django.utils.timezone

class Migration(migrations.Migration):

    dependencies = [
        ('gmail_auth', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='googletoken',
            name='expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='googletoken',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        # More robust SQL update that handles both existing and new records
        migrations.RunSQL(
            """
            UPDATE gmail_auth_googletoken 
            SET is_active = true 
            WHERE is_active IS NULL OR is_active = false;
            """,
            reverse_sql="""
            UPDATE gmail_auth_googletoken 
            SET is_active = NULL;
            """
        ),
    ]
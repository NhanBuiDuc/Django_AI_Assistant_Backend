from django.core.management.base import BaseCommand
from deeptalk.models import TaskCategory, DeepTalkUser

class Command(BaseCommand):
    help = 'Create default system task categories'

    def handle(self, *args, **options):
        default_categories = [
            {
                'name': 'Work',
                'color_hex': '#3b82f6',
                'icon': '💼',
                'default_duration': 60,
                'default_priority': 2,
            },
            {
                'name': 'Personal',
                'color_hex': '#10b981',
                'icon': '🏠',
                'default_duration': 30,
                'default_priority': 3,
            },
            {
                'name': 'Health',
                'color_hex': '#f59e0b',
                'icon': '🏃‍♂️',
                'default_duration': 45,
                'default_priority': 2,
            },
            {
                'name': 'Education',
                'color_hex': '#8b5cf6',
                'icon': '📚',
                'default_duration': 90,
                'default_priority': 2,
            },
            {
                'name': 'Finance',
                'color_hex': '#ef4444',
                'icon': '💰',
                'default_duration': 30,
                'default_priority': 1,
            },
            {
                'name': 'Social',
                'color_hex': '#06b6d4',
                'icon': '👥',
                'default_duration': 60,
                'default_priority': 3,
            }
        ]

        created_count = 0
        for cat_data in default_categories:
            category, created = TaskCategory.objects.get_or_create(
                name=cat_data['name'],
                is_system_category=True,
                defaults={
                    'user_id': None,
                    'color_hex': cat_data['color_hex'],
                    'icon': cat_data['icon'],
                    'default_duration': cat_data['default_duration'],
                    'default_priority': cat_data['default_priority'],
                    'is_system_category': True,
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created category: {category.name}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Category already exists: {category.name}')
                )

        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {created_count} default categories')
        )
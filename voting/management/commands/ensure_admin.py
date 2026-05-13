import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Create the admin superuser if absent, or update the password if present. Idempotent.'

    def add_arguments(self, parser):
        parser.add_argument('--username', default=os.environ.get('DJANGO_ADMIN_USERNAME', 'admin'))
        parser.add_argument('--password', default=os.environ.get('DJANGO_ADMIN_PASSWORD'))
        parser.add_argument('--email', default=os.environ.get('DJANGO_ADMIN_EMAIL', ''))

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']
        email    = options['email']

        if not password:
            raise CommandError(
                'Password required: pass --password or set DJANGO_ADMIN_PASSWORD'
            )

        User = get_user_model()
        user, created = User.objects.get_or_create(username=username)
        user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(f'{action} admin user: {username}'))

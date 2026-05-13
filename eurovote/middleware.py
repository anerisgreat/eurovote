from django.contrib.auth import get_user_model, login


class RemoteUserMiddleware:
    """
    If the X-Remote-User header is present (set by Authelia reverse proxy),
    authenticate or create the corresponding Django user and log them in.

    All SSO-authenticated users are granted is_staff + is_superuser so that
    Django admin works without manual account setup. Authelia's group/policy
    configuration is the real gate — anyone who reaches this app via SSO is
    a trusted user; anyone who reaches /admin/ via SSO has been cleared by
    Authelia's admin-group policy.

    Falls back to normal Django session auth when the header is absent (dev mode).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        remote_user = request.META.get('HTTP_X_REMOTE_USER')
        if remote_user and not request.user.is_authenticated:
            User = get_user_model()
            user, created = User.objects.get_or_create(username=remote_user)
            if created or not (user.is_staff and user.is_superuser):
                user.is_staff = True
                user.is_superuser = True
                user.save(update_fields=['is_staff', 'is_superuser'])
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            login(request, user)
        return self.get_response(request)

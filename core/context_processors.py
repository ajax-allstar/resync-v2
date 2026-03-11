from django.conf import settings


def resync_settings(request):
    return {
        "GOOGLE_AUTH_ENABLED": settings.GOOGLE_AUTH_ENABLED,
        "RESYNC_BRAND": settings.RESYNC_BRAND,
    }

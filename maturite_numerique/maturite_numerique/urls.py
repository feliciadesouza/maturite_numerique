"""URL configuration for maturite_numerique project."""
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path


def healthz(_request):
    """Sonde de santé pour la plateforme d'hébergement (pas d'authentification)."""
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path('healthz', healthz),
    path('', include('core.urls')),
    path('admin/', admin.site.urls),
]

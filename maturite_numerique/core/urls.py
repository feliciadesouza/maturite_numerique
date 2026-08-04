from django.urls import path

from .views import (
    administration_detail,
    dashboard,
    formulaire_a,
    formulaire_b,
    home,
    login_view,
    logout_view,
    profile,
    roles,
)

urlpatterns = [
    path('', home, name='home'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('dashboard/', dashboard, name='dashboard'),
    path('administration/<int:administration_id>/', administration_detail, name='administration_detail'),
    path('formulaire-a/', formulaire_a, name='formulaire_a'),
    path('formulaire-b/', formulaire_b, name='formulaire_b'),
    path('profile/', profile, name='profile'),
    path('roles/', roles, name='roles'),
]

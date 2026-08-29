from django.urls import path

from .views import (
    administration_detail,
    backoffice,
    dashboard,
    enqueteur_home,
    formulaire_a,
    formulaire_b,
    formulaire_b_public,
    home,
    login_view,
    logout_view,
    profile,
    roles,
)

urlpatterns = [
    path('', home, name='home'),
    path('connexion/', login_view, name='connexion'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('dashboard/', dashboard, name='dashboard'),
    path('back-office/', backoffice, name='backoffice'),
    path('enquetes/', enqueteur_home, name='enqueteur_home'),
    path('administration/<int:administration_id>/', administration_detail, name='administration_detail'),
    path('formulaire-a/', formulaire_a, name='formulaire_a'),
    path('formulaire-b/', formulaire_b, name='formulaire_b'),
    path('agent-enquete/', formulaire_b_public, name='formulaire_b_public'),
    path('profile/', profile, name='profile'),
    path('roles/', roles, name='roles'),
]

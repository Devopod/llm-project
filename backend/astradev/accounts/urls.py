from django.urls import path
from . import views

urlpatterns = [
    path('signup/', views.signup, name='signup'),
    path('login/', views.login, name='login'),
    path('refresh/', views.refresh_token, name='refresh'),
    path('logout/', views.logout, name='logout'),
    path('profile/', views.profile, name='profile'),
    path('stats/', views.user_stats, name='user-stats'),
]

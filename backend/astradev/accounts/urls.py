from django.urls import path
from . import views

urlpatterns = [
    path('signup/', views.signup, name='signup'),
    path('login/', views.login, name='login'),
    path('refresh/', views.refresh_token, name='refresh-token'),
    path('logout/', views.logout, name='logout'),
    path('profile/', views.profile, name='profile'),
    path('change-password/', views.change_password, name='change-password'),
    path('usage/', views.usage_stats, name='usage-stats'),
    path('plans/', views.plans_info, name='plans-info'),
    path('payments/submit/', views.submit_payment, name='submit-payment'),
    path('payments/history/', views.payment_history, name='payment-history'),
    # Admin endpoints
    path('admin/login/', views.admin_login, name='admin-login'),
    path('admin/dashboard/', views.admin_dashboard, name='admin-dashboard'),
    path('admin/users/', views.admin_users, name='admin-users'),
    path('admin/payments/', views.admin_payments, name='admin-payments'),
    path('admin/payments/<uuid:payment_id>/verify/', views.admin_verify_payment, name='admin-verify-payment'),
    path('admin/users/<uuid:user_id>/delete/', views.admin_delete_user, name='admin-delete-user'),
]

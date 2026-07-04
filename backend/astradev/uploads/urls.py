from django.urls import path
from . import views

urlpatterns = [
    path('', views.upload_file, name='upload-file'),
    path('<uuid:upload_id>/', views.upload_status, name='upload-status'),
]

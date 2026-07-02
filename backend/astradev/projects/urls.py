from django.urls import path
from . import views
from .apk_views import build_apk, download_apk

urlpatterns = [
    path('', views.project_list, name='project-list'),
    path('<uuid:project_id>/', views.project_detail, name='project-detail'),
    path('<uuid:project_id>/pause/', views.project_pause, name='project-pause'),
    path('<uuid:project_id>/resume/', views.project_resume, name='project-resume'),
    path('<uuid:project_id>/roadmap/', views.project_roadmap, name='project-roadmap'),
    path('<uuid:project_id>/messages/', views.project_messages, name='project-messages'),
    path('<uuid:project_id>/chat/', views.project_chat, name='project-chat'),
    path('<uuid:project_id>/files/', views.project_files, name='project-files'),
    path('<uuid:project_id>/apk/build/', build_apk, name='build-apk'),
    path('<uuid:project_id>/apk/download/', download_apk, name='download-apk'),
    path('<uuid:project_id>/deploy/', views.deploy_project, name='deploy-project'),
    path('<uuid:project_id>/file-content/<path:file_path>', views.project_file_content, name='project-file-content'),
    path('<uuid:project_id>/file-edit/<path:file_path>', views.project_file_edit, name='project-file-edit'),
]

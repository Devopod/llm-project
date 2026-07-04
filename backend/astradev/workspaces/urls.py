from django.urls import path
from . import views

urlpatterns = [
    path('<uuid:project_id>/files/', views.workspace_files, name='workspace-files'),
    path('<uuid:project_id>/files/<path:file_path>/', views.workspace_file_content, name='workspace-file-content'),
    path('<uuid:project_id>/download/', views.workspace_download, name='workspace-download'),
    path('<uuid:project_id>/execute/', views.workspace_execute, name='workspace-execute'),
]

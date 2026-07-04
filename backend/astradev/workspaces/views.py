import os
from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from astradev.projects.models import Project
from .manager import workspace_manager


@api_view(['GET'])
def workspace_files(request, project_id):
    try:
        project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return Response({'error': {'code': 'NOT_FOUND', 'message': 'Project not found'}},
                        status=status.HTTP_404_NOT_FOUND)

    files = workspace_manager.list_files(str(project_id))
    return Response({
        'files': [{'path': f.path, 'is_dir': f.is_dir, 'size': f.size} for f in files]
    })


@api_view(['GET'])
def workspace_file_content(request, project_id, file_path):
    try:
        project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return Response({'error': {'code': 'NOT_FOUND', 'message': 'Project not found'}},
                        status=status.HTTP_404_NOT_FOUND)

    content = workspace_manager.read_file(str(project_id), file_path)
    if content is None:
        return Response({'error': {'code': 'FILE_NOT_FOUND', 'message': 'File not found'}},
                        status=status.HTTP_404_NOT_FOUND)

    return Response({'path': file_path, 'content': content})


@api_view(['POST'])
def workspace_download(request, project_id):
    try:
        project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return Response({'error': {'code': 'NOT_FOUND', 'message': 'Project not found'}},
                        status=status.HTTP_404_NOT_FOUND)

    zip_path = workspace_manager.download_workspace_zip(str(project_id))
    if not zip_path or not os.path.exists(zip_path):
        return Response({'error': {'code': 'NO_WORKSPACE', 'message': 'No workspace files'}},
                        status=status.HTTP_404_NOT_FOUND)

    return FileResponse(open(zip_path, 'rb'), as_attachment=True,
                        filename=f"{project.name}.zip", content_type='application/zip')


@api_view(['POST'])
def workspace_execute(request, project_id):
    try:
        project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return Response({'error': {'code': 'NOT_FOUND', 'message': 'Project not found'}},
                        status=status.HTTP_404_NOT_FOUND)

    command = request.data.get('command', '')
    if not command:
        return Response({'error': {'code': 'NO_COMMAND', 'message': 'Command required'}},
                        status=status.HTTP_400_BAD_REQUEST)

    result = workspace_manager.execute_command(str(project_id), command)
    return Response({
        'stdout': result.stdout,
        'stderr': result.stderr,
        'exit_code': result.exit_code,
    })

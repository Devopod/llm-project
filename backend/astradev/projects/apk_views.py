import os
from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Project
from astradev.agents.apk_builder import APKBuilderAgent
from astradev.workspaces.manager import workspace_manager


@api_view(['POST'])
def build_apk(request, project_id):
    try:
        project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return Response({'error': {'code': 'NOT_FOUND', 'message': 'Project not found'}},
                        status=status.HTTP_404_NOT_FOUND)

    agent = APKBuilderAgent(project)
    description = request.data.get('description', f'Build an Android APK for the project: {project.name}')

    # Generate Android project
    result = agent.execute(description, {'project_state': project.project_state})

    # Write files to workspace
    workspace_path = f"/tmp/astradev_workspaces/{project.id}"
    os.makedirs(workspace_path, exist_ok=True)

    for file_info in result.get('files', []):
        full_path = os.path.join(workspace_path, file_info['path'])
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w') as f:
            f.write(file_info.get('content', ''))

    # Try to build
    build_result = agent.build_apk(str(project.id), workspace_path)

    if build_result.get('status') == 'success' and build_result.get('apk_path'):
        return Response({
            'status': 'success',
            'message': 'APK built successfully',
            'download_url': f'/api/projects/{project.id}/apk/download/',
        })

    return Response({
        'status': 'project_ready',
        'message': build_result.get('message', 'Android project generated. Download as ZIP to build locally.'),
        'files_generated': len(result.get('files', [])),
    })


@api_view(['GET'])
def download_apk(request, project_id):
    try:
        project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return Response({'error': {'code': 'NOT_FOUND', 'message': 'Project not found'}},
                        status=status.HTTP_404_NOT_FOUND)

    workspace_path = f"/tmp/astradev_workspaces/{project.id}"

    # Look for APK file
    for root, dirs, files in os.walk(workspace_path):
        for f in files:
            if f.endswith('.apk'):
                apk_path = os.path.join(root, f)
                return FileResponse(
                    open(apk_path, 'rb'),
                    as_attachment=True,
                    filename=f"{project.name}.apk",
                    content_type='application/vnd.android.package-archive'
                )

    # If no APK, provide ZIP of the Android project
    zip_path = workspace_manager.download_workspace_zip(str(project.id))
    if zip_path and os.path.exists(zip_path):
        return FileResponse(
            open(zip_path, 'rb'),
            as_attachment=True,
            filename=f"{project.name}-android.zip",
            content_type='application/zip'
        )

    return Response({'error': {'code': 'NO_APK', 'message': 'No APK available'}},
                    status=status.HTTP_404_NOT_FOUND)

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Project, Task, Message
from .serializers import (
    ProjectSerializer, ProjectCreateSerializer,
    TaskSerializer, MessageSerializer
)


@api_view(['GET', 'POST'])
def project_list(request):
    if request.method == 'GET':
        projects = Project.objects.filter(user=request.user)
        return Response(ProjectSerializer(projects, many=True).data)

    # Check usage limits
    user = request.user
    if not user.can_send_message():
        return Response({
            'error': {
                'code': 'LIMIT_REACHED',
                'message': f'Daily message limit reached ({user.message_limit}). Upgrade your plan for more.',
            }
        }, status=status.HTTP_429_TOO_MANY_REQUESTS)

    serializer = ProjectCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    project = Project.objects.create(
        user=request.user,
        name=serializer.validated_data['name'],
        description=serializer.validated_data.get('description', ''),
    )
    prompt = serializer.validated_data.get('prompt', '')
    if prompt:
        Message.objects.create(
            project=project,
            role='user',
            content=prompt,
            message_type='message',
        )
        # Track usage
        user.messages_used_today += 1
        user.total_messages_sent += 1
        user.total_projects_created += 1
        user.save(update_fields=['messages_used_today', 'total_messages_sent', 'total_projects_created'])
        # Trigger agent execution asynchronously
        from astradev.agents.tasks import run_agent_pipeline
        run_agent_pipeline.delay(str(project.id), prompt)

    return Response(ProjectSerializer(project).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'DELETE'])
def project_detail(request, project_id):
    try:
        project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return Response({'error': {'code': 'NOT_FOUND', 'message': 'Project not found'}},
                        status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(ProjectSerializer(project).data)

    project.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
def project_pause(request, project_id):
    try:
        project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return Response({'error': {'code': 'NOT_FOUND', 'message': 'Project not found'}},
                        status=status.HTTP_404_NOT_FOUND)
    project.status = 'paused'
    project.save()
    return Response(ProjectSerializer(project).data)


@api_view(['POST'])
def project_resume(request, project_id):
    try:
        project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return Response({'error': {'code': 'NOT_FOUND', 'message': 'Project not found'}},
                        status=status.HTTP_404_NOT_FOUND)
    project.status = 'executing'
    project.save()
    return Response(ProjectSerializer(project).data)


@api_view(['GET'])
def project_roadmap(request, project_id):
    try:
        project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return Response({'error': {'code': 'NOT_FOUND', 'message': 'Project not found'}},
                        status=status.HTTP_404_NOT_FOUND)
    tasks = Task.objects.filter(project=project)
    return Response({
        'roadmap': project.roadmap,
        'tasks': TaskSerializer(tasks, many=True).data,
    })


@api_view(['GET'])
def project_messages(request, project_id):
    try:
        project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return Response({'error': {'code': 'NOT_FOUND', 'message': 'Project not found'}},
                        status=status.HTTP_404_NOT_FOUND)
    messages = Message.objects.filter(project=project)
    return Response(MessageSerializer(messages, many=True).data)


@api_view(['POST'])
def project_chat(request, project_id):
    try:
        project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return Response({'error': {'code': 'NOT_FOUND', 'message': 'Project not found'}},
                        status=status.HTTP_404_NOT_FOUND)

    content = request.data.get('message', '')
    if not content:
        return Response({'error': {'code': 'EMPTY_MESSAGE', 'message': 'Message content required'}},
                        status=status.HTTP_400_BAD_REQUEST)

    msg = Message.objects.create(
        project=project,
        role='user',
        content=content,
        message_type='message',
    )
    # Trigger agent
    from astradev.agents.tasks import run_agent_pipeline
    run_agent_pipeline.delay(str(project.id), content)

    return Response(MessageSerializer(msg).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
def project_files(request, project_id):
    try:
        project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return Response({'error': {'code': 'NOT_FOUND', 'message': 'Project not found'}},
                        status=status.HTTP_404_NOT_FOUND)
    return Response(project.project_state.get('file_tree', {}))


@api_view(['POST'])
def deploy_project(request, project_id):
    try:
        project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return Response({'error': {'code': 'NOT_FOUND', 'message': 'Project not found'}},
                        status=status.HTTP_404_NOT_FOUND)

    action = request.data.get('action')  # 'approve' or 'deny'
    if action == 'approve':
        project.status = 'deploying'
        project.save()
        # Trigger deployment
        from astradev.agents.tasks import deploy_project_task
        deploy_project_task.delay(str(project.id))
        return Response({
            'message': 'Deployment approved. Your app is being deployed...',
            'status': 'deploying',
        })
    elif action == 'deny':
        return Response({
            'message': 'Deployment cancelled.',
            'status': project.status,
        })
    else:
        return Response({'error': 'Action must be approve or deny'}, status=400)

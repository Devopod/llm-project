import os
import shutil
import zipfile
import tempfile
import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from .models import Project, Task, Message
from .serializers import (
    ProjectSerializer, ProjectCreateSerializer,
    TaskSerializer, MessageSerializer
)

logger = logging.getLogger('astradev.projects')


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


ARCHIVE_EXTENSIONS = {'.zip', '.7z', '.tar.gz', '.tgz'}
TEXT_CODE_EXTENSIONS = {
    '.py', '.js', '.ts', '.tsx', '.jsx', '.html', '.htm', '.css', '.scss', '.less',
    '.json', '.yaml', '.yml', '.xml', '.svg', '.md', '.txt', '.rst',
    '.java', '.kt', '.kts', '.swift', '.go', '.rs', '.rb', '.php',
    '.c', '.cpp', '.h', '.hpp', '.cs', '.sql', '.r',
    '.dart', '.lua', '.pl', '.pm', '.sh', '.bash', '.zsh', '.bat', '.ps1',
    '.toml', '.ini', '.cfg', '.conf', '.env', '.gitignore', '.dockerignore',
    '.dockerfile', '.makefile', '.gradle', '.properties',
    '.graphql', '.gql', '.proto', '.tf', '.hcl',
    '.vue', '.svelte', '.astro',
}


def _is_text_or_code_file(filename: str) -> bool:
    name_lower = filename.lower()
    base = os.path.basename(name_lower)
    if base in ('dockerfile', 'makefile', 'procfile', 'gemfile', 'rakefile', '.gitignore', '.dockerignore', '.env'):
        return True
    _, ext = os.path.splitext(name_lower)
    return ext in TEXT_CODE_EXTENSIONS


def _is_archive_file(filename: str) -> bool:
    name_lower = filename.lower()
    return any(name_lower.endswith(ext) for ext in ARCHIVE_EXTENSIONS)


def _build_file_tree(workspace: str) -> dict:
    file_tree = {}
    for root, dirs, fnames in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', 'node_modules', '.git', '.venv', 'venv')]
        for fname in fnames:
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, workspace)
            if rel.startswith('.') and '/' not in rel and rel not in ('.gitignore', '.dockerignore', '.env'):
                continue
            try:
                sz = os.path.getsize(full)
            except OSError:
                sz = 0
            file_tree[rel] = {'type': 'file', 'size': sz}
    return file_tree


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def project_upload(request):
    """Upload text/code files or ZIP/7z archives to create a project."""
    uploaded_files = request.FILES.getlist('file') or request.FILES.getlist('files')
    if not uploaded_files:
        uploaded_files = [v for v in request.FILES.values()]

    name = request.data.get('name', '')
    prompt = request.data.get('prompt', '')

    if not uploaded_files:
        return Response({'error': {'code': 'NO_FILE', 'message': 'No files uploaded'}},
                        status=status.HTTP_400_BAD_REQUEST)

    # Validate all files are text/code or archives
    for f in uploaded_files:
        if not _is_text_or_code_file(f.name) and not _is_archive_file(f.name):
            return Response({
                'error': {
                    'code': 'INVALID_FORMAT',
                    'message': f'Unsupported file type: {f.name}. Only text, code, ZIP, and 7z files are allowed.',
                }
            }, status=status.HTTP_400_BAD_REQUEST)

    if not name:
        if len(uploaded_files) == 1:
            name = os.path.splitext(uploaded_files[0].name)[0]
        else:
            name = 'Uploaded Project'

    project = Project.objects.create(
        user=request.user,
        name=name,
        description=f'Uploaded {len(uploaded_files)} file(s)',
    )

    workspace = f'/tmp/astradev_workspaces/{project.id}'
    os.makedirs(workspace, exist_ok=True)

    try:
        file_count = 0
        for uploaded in uploaded_files:
            fname = uploaded.name
            if _is_archive_file(fname):
                # Extract archive
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(fname)[1])
                for chunk in uploaded.chunks():
                    tmp.write(chunk)
                tmp.close()

                fname_lower = fname.lower()
                if fname_lower.endswith('.zip'):
                    with zipfile.ZipFile(tmp.name, 'r') as zf:
                        zf.extractall(workspace)
                elif fname_lower.endswith('.7z'):
                    import subprocess
                    subprocess.run(['7z', 'x', tmp.name, f'-o{workspace}', '-y'],
                                   capture_output=True, timeout=60)
                elif fname_lower.endswith('.tar.gz') or fname_lower.endswith('.tgz'):
                    import tarfile
                    with tarfile.open(tmp.name, 'r:gz') as tf:
                        tf.extractall(workspace)

                os.unlink(tmp.name)

                # If extraction created a single subdirectory, flatten it
                items = os.listdir(workspace)
                if len(items) == 1 and os.path.isdir(os.path.join(workspace, items[0])):
                    subdir = os.path.join(workspace, items[0])
                    for item in os.listdir(subdir):
                        src = os.path.join(subdir, item)
                        dst = os.path.join(workspace, item)
                        if not os.path.exists(dst):
                            shutil.move(src, dst)
                    try:
                        shutil.rmtree(subdir)
                    except OSError:
                        pass
            else:
                # Save text/code file directly
                dest = os.path.join(workspace, fname)
                dest_dir = os.path.dirname(dest)
                if dest_dir and not os.path.exists(dest_dir):
                    os.makedirs(dest_dir, exist_ok=True)
                with open(dest, 'wb') as out:
                    for chunk in uploaded.chunks():
                        out.write(chunk)
                file_count += 1

        file_tree = _build_file_tree(workspace)

        project.project_state = {
            'workspace_path': workspace,
            'file_tree': file_tree,
            'uploaded': True,
        }
        project.status = 'completed'
        project.save()

        Message.objects.create(
            project=project, role='system',
            content=f'Project created from {len(uploaded_files)} uploaded file(s). {len(file_tree)} files in workspace.',
            message_type='success',
        )

        user = request.user
        user.total_projects_created += 1
        user.save(update_fields=['total_projects_created'])

        if prompt:
            Message.objects.create(
                project=project, role='user',
                content=prompt, message_type='message',
            )
            project.status = 'executing'
            project.save(update_fields=['status'])
            from astradev.agents.tasks import run_agent_pipeline
            run_agent_pipeline.delay(str(project.id), prompt)

    except Exception as e:
        logger.exception('Upload failed')
        project.status = 'failed'
        project.save(update_fields=['status'])
        Message.objects.create(
            project=project, role='system',
            content=f'Failed to process uploaded files: {str(e)}',
            message_type='error',
        )

    return Response(ProjectSerializer(project).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
def project_file_content(request, project_id, file_path):
    """Get the full content of a specific file."""
    file_path = file_path.strip('/')
    try:
        project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return Response({'error': {'code': 'NOT_FOUND', 'message': 'Project not found'}},
                        status=status.HTTP_404_NOT_FOUND)

    workspace = project.project_state.get('workspace_path', f'/tmp/astradev_workspaces/{project_id}')
    full_path = os.path.join(workspace, file_path)

    # Security: prevent path traversal
    if not os.path.realpath(full_path).startswith(os.path.realpath(workspace)):
        return Response({'error': {'code': 'FORBIDDEN', 'message': 'Path traversal not allowed'}},
                        status=status.HTTP_403_FORBIDDEN)

    if not os.path.isfile(full_path):
        return Response({'error': {'code': 'NOT_FOUND', 'message': 'File not found'}},
                        status=status.HTTP_404_NOT_FOUND)

    try:
        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        return Response({'error': {'code': 'READ_ERROR', 'message': str(e)}},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({
        'path': file_path,
        'content': content,
        'size': len(content),
        'lines': content.count('\n') + 1,
    })


@api_view(['PUT'])
def project_file_edit(request, project_id, file_path):
    """Edit a file: full replace or line-range update."""
    import os
    file_path = file_path.strip('/')
    try:
        project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return Response({'error': {'code': 'NOT_FOUND', 'message': 'Project not found'}},
                        status=status.HTTP_404_NOT_FOUND)

    workspace = project.project_state.get('workspace_path', f'/tmp/astradev_workspaces/{project_id}')
    full_path = os.path.join(workspace, file_path)

    # Security: prevent path traversal
    if not os.path.realpath(full_path).startswith(os.path.realpath(workspace)):
        return Response({'error': {'code': 'FORBIDDEN', 'message': 'Path traversal not allowed'}},
                        status=status.HTTP_403_FORBIDDEN)

    content = request.data.get('content')
    start_line = request.data.get('start_line')
    end_line = request.data.get('end_line')
    new_lines_content = request.data.get('new_content')

    if content is not None:
        # Full file replace
        parent_dir = os.path.dirname(full_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
    elif start_line is not None and new_lines_content is not None:
        # Line-range edit
        if not os.path.isfile(full_path):
            return Response({'error': {'code': 'NOT_FOUND', 'message': 'File not found'}},
                            status=status.HTTP_404_NOT_FOUND)
        with open(full_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        start = int(start_line) - 1  # Convert to 0-indexed
        end = int(end_line) if end_line else start + 1

        # Replace the line range
        new_lines = new_lines_content.split('\n') if isinstance(new_lines_content, str) else new_lines_content
        new_lines = [l + '\n' if not l.endswith('\n') else l for l in new_lines]
        lines[start:end] = new_lines

        with open(full_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        content = ''.join(lines)
    else:
        return Response({'error': {'code': 'BAD_REQUEST', 'message': 'Provide content (full) or start_line + new_content (line edit)'}},
                        status=status.HTTP_400_BAD_REQUEST)

    # Update file tree in project state
    file_tree = project.project_state.get('file_tree', {})
    file_tree[file_path] = {'type': 'file', 'size': len(content)}
    project.project_state['file_tree'] = file_tree
    project.save(update_fields=['project_state'])

    return Response({
        'path': file_path,
        'content': content,
        'size': len(content),
        'lines': content.count('\n') + 1,
        'message': 'File updated successfully',
    })

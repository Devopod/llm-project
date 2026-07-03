import logging
import os
import uuid
from celery import shared_task
from astradev.projects.models import Project

logger = logging.getLogger('astradev.agents')


@shared_task(bind=True, max_retries=2)
def run_agent_pipeline(self, project_id: str, prompt: str):
    try:
        project = Project.objects.get(id=project_id)
        from .orchestrator import OrchestratorAgent
        orchestrator = OrchestratorAgent(project)
        result = orchestrator.execute(prompt)
        logger.info(f"Agent pipeline completed for project {project_id}: {result.get('status')}")
        return result
    except Project.DoesNotExist:
        logger.error(f"Project {project_id} not found")
        return {'status': 'error', 'message': 'Project not found'}
    except Exception as e:
        logger.error(f"Agent pipeline error: {e}")
        try:
            project = Project.objects.get(id=project_id)
            project.status = 'failed'
            project.save(update_fields=['status'])
        except Exception:
            pass
        raise self.retry(exc=e, countdown=10)


@shared_task(bind=True, max_retries=1)
def deploy_project_task(self, project_id: str):
    """Deploy project files via a local server + ngrok tunnel."""
    import subprocess
    import signal
    import time
    import socket

    def _find_free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    try:
        project = Project.objects.get(id=project_id)
        from astradev.projects.models import Message

        workspace = project.project_state.get('workspace_path', '')
        if not workspace or not os.path.isdir(workspace):
            workspace = f"/tmp/astradev_workspaces/{project_id}"

        if not os.path.isdir(workspace):
            project.status = 'failed'
            project.save(update_fields=['status'])
            Message.objects.create(
                project=project, role='deployer',
                content="Deployment failed: No workspace files found.",
                message_type='error',
            )
            return {'status': 'error', 'message': 'No workspace'}

        # Detect project type and choose server
        files = os.listdir(workspace)
        port = _find_free_port()
        server_process = None
        start_cmd = None

        # Check for web-servable content
        has_index_html = 'index.html' in files
        has_package_json = 'package.json' in files
        has_flask = any(
            'flask' in open(os.path.join(workspace, f)).read().lower()
            for f in files if f.endswith('.py')
            and os.path.isfile(os.path.join(workspace, f))
        )
        has_fastapi = any(
            'fastapi' in open(os.path.join(workspace, f)).read().lower()
            for f in files if f.endswith('.py')
            and os.path.isfile(os.path.join(workspace, f))
        )
        has_django = 'manage.py' in files

        # Determine start command
        if has_index_html:
            start_cmd = ['python3', '-m', 'http.server', str(port)]
        elif has_fastapi:
            # Find the main app file
            app_file = None
            for f in files:
                if f.endswith('.py') and os.path.isfile(os.path.join(workspace, f)):
                    content = open(os.path.join(workspace, f)).read()
                    if 'FastAPI' in content or 'fastapi' in content:
                        app_file = f
                        break
            if app_file:
                module = app_file.replace('.py', '')
                start_cmd = ['uvicorn', f'{module}:app', '--host', '0.0.0.0', '--port', str(port)]
            else:
                start_cmd = ['python3', '-m', 'http.server', str(port)]
        elif has_flask:
            app_file = None
            for f in files:
                if f.endswith('.py') and os.path.isfile(os.path.join(workspace, f)):
                    content = open(os.path.join(workspace, f)).read()
                    if 'Flask' in content:
                        app_file = f
                        break
            if app_file:
                # Install Flask if needed
                req_file = os.path.join(workspace, 'requirements.txt')
                if os.path.isfile(req_file):
                    subprocess.run(['pip3', 'install', '-r', req_file],
                                   cwd=workspace, capture_output=True, timeout=60)
                else:
                    subprocess.run(['pip3', 'install', 'flask'],
                                   capture_output=True, timeout=30)
                # Patch app.run() to use dynamic port
                app_content = open(os.path.join(workspace, app_file)).read()
                import re
                patched = re.sub(
                    r"app\.run\([^)]*\)",
                    f"app.run(host='0.0.0.0', port={port}, debug=False)",
                    app_content
                )
                if patched != app_content:
                    with open(os.path.join(workspace, app_file), 'w') as pf:
                        pf.write(patched)
                start_cmd = ['python3', app_file]
            else:
                start_cmd = ['python3', '-m', 'http.server', str(port)]
        elif has_django:
            start_cmd = ['python3', 'manage.py', 'runserver', f'0.0.0.0:{port}']
        elif has_package_json:
            # Install deps and start node app
            subprocess.run(['npm', 'install'], cwd=workspace, capture_output=True, timeout=60)
            start_cmd = ['npx', 'serve', '-l', str(port), '-s', '.']
        else:
            # Default: create a simple index.html from project files and serve
            index_path = os.path.join(workspace, 'index.html')
            if not os.path.exists(index_path):
                # Generate simple HTML showcase
                file_list = '\n'.join(f'<li>{f}</li>' for f in files)
                html = f"""<!DOCTYPE html>
<html>
<head><title>{project.name} - Deployed by AstraDev</title>
<style>body{{font-family:system-ui;max-width:800px;margin:50px auto;padding:20px;background:#0d1117;color:#c9d1d9}}
h1{{color:#58a6ff}}pre{{background:#161b22;padding:15px;border-radius:8px;overflow-x:auto}}
a{{color:#58a6ff}}li{{margin:5px 0}}</style></head>
<body>
<h1>{project.name}</h1>
<p>Deployed via AstraDev</p>
<h2>Project Files</h2>
<ul>{file_list}</ul>
<h2>Source Code</h2>
"""
                # Include first few source files
                for f in files[:5]:
                    fpath = os.path.join(workspace, f)
                    if os.path.isfile(fpath) and not f.startswith('.'):
                        try:
                            code = open(fpath).read()[:3000]
                            html += f'<h3>{f}</h3><pre><code>{code}</code></pre>\n'
                        except Exception:
                            pass
                html += "</body></html>"
                with open(index_path, 'w') as fh:
                    fh.write(html)
            start_cmd = ['python3', '-m', 'http.server', str(port)]

        # Start the server process
        logger.info(f"Starting server for project {project_id}: {start_cmd}")
        server_process = subprocess.Popen(
            start_cmd, cwd=workspace,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            preexec_fn=os.setsid,
        )

        # Wait for server to start
        time.sleep(2)
        if server_process.poll() is not None:
            stderr = server_process.stderr.read().decode()[:500]
            raise RuntimeError(f"Server failed to start: {stderr}")

        # Deploy URL is a path on the same base URL (proxied by Django)
        deploy_url = f"/projects/{project_id}/deployed/"

        # Save deployment info
        project.deployment_url = deploy_url
        project.status = 'completed'
        deploy_info = project.project_state.get('deploy_info', {})
        deploy_info.update({
            'port': port,
            'pid': server_process.pid,
            'deploy_path': deploy_url,
            'start_cmd': start_cmd,
        })
        project.project_state['deploy_info'] = deploy_info
        project.save(update_fields=['deployment_url', 'status', 'project_state'])

        Message.objects.create(
            project=project, role='deployer',
            content=f"Deployment successful! Your app is live at: {deploy_url}",
            message_type='deployment',
            metadata={'url': deploy_url, 'status': 'live', 'port': port},
        )
        logger.info(f"Project {project_id} deployed at {deploy_url} (port {port})")
        return {'status': 'deployed', 'url': deploy_url}

    except Exception as e:
        logger.error(f"Deploy error: {e}")
        try:
            project = Project.objects.get(id=project_id)
            project.status = 'failed'
            project.save(update_fields=['status'])
            from astradev.projects.models import Message
            Message.objects.create(
                project=project, role='deployer',
                content=f"Deployment failed: {str(e)[:200]}",
                message_type='error',
            )
        except Exception:
            pass
        raise

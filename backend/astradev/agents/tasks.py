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


def _find_flask_app(workspace):
    """Recursively find the Flask app file and return (app_file_relative, app_dir)."""
    import re as _re

    for root, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in ('node_modules', '.git', '__pycache__', 'venv', '.venv', 'tests', 'test')]
        for fname in files:
            if not fname.endswith('.py'):
                continue
            fpath = os.path.join(root, fname)
            try:
                content = open(fpath, 'r', errors='replace').read()
                # Look for Flask() instantiation or create_app pattern
                if 'Flask(' in content or 'Flask (' in content:
                    rel = os.path.relpath(fpath, workspace)
                    return rel, root
            except Exception:
                pass
    return None, None


def _find_main_app_file(workspace):
    """Find the main entry point for any Python web app."""
    # Priority 1: top-level app.py or main.py with Flask/FastAPI
    for name in ['app.py', 'main.py', 'server.py', 'run.py']:
        fpath = os.path.join(workspace, name)
        if os.path.isfile(fpath):
            try:
                content = open(fpath, 'r', errors='replace').read()
                if 'Flask' in content or 'FastAPI' in content or 'fastapi' in content:
                    return name, workspace, content
            except Exception:
                pass

    # Priority 2: app/__init__.py with Flask
    init_path = os.path.join(workspace, 'app', '__init__.py')
    if os.path.isfile(init_path):
        try:
            content = open(init_path, 'r', errors='replace').read()
            if 'Flask' in content:
                return 'app/__init__.py', workspace, content
        except Exception:
            pass

    # Priority 3: recursive search
    rel, app_dir = _find_flask_app(workspace)
    if rel:
        try:
            content = open(os.path.join(workspace, rel), 'r', errors='replace').read()
            return rel, app_dir, content
        except Exception:
            pass

    return None, None, None


@shared_task(bind=True, max_retries=1)
def deploy_project_task(self, project_id: str):
    """Deploy project files via a local server + Django reverse proxy."""
    import subprocess
    import signal
    import time
    import socket
    import re

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

        # Pre-deployment validation
        from .validators import validate_workspace, validate_runtime
        pre_report = validate_workspace(workspace)
        if not pre_report.passed:
            failed = [r.file_path for r in pre_report.failed_files]
            logger.warning(f"Pre-deploy validation: {len(failed)} files have issues: {failed[:5]}")
            Message.objects.create(
                project=project, role='deployer',
                content=f"Warning: {len(failed)} file(s) have validation issues: {', '.join(failed[:3])}",
                message_type='action',
            )

        # Kill any existing deployment for this project
        old_deploy = project.project_state.get('deploy_info', {})
        old_pid = old_deploy.get('pid')
        if old_pid:
            try:
                os.killpg(os.getpgid(old_pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass

        port = _find_free_port()
        start_cmd = None
        cwd = workspace

        # Detect project type
        all_files = []
        for root, dirs, files in os.walk(workspace):
            dirs[:] = [d for d in dirs if d not in ('node_modules', '.git', '__pycache__', 'venv', '.venv')]
            for f in files:
                all_files.append(os.path.relpath(os.path.join(root, f), workspace))

        top_files = os.listdir(workspace)
        has_index_html = 'index.html' in top_files
        has_package_json = 'package.json' in top_files
        has_django = 'manage.py' in top_files

        # Find Flask/FastAPI app
        app_rel, app_dir, app_content = _find_main_app_file(workspace)

        has_flask = app_content and ('Flask' in app_content)
        has_fastapi = app_content and ('FastAPI' in app_content or 'fastapi' in app_content)

        if has_flask and app_rel:
            # Install dependencies
            req_file = os.path.join(workspace, 'requirements.txt')
            if os.path.isfile(req_file):
                subprocess.run(['pip3', 'install', '-r', req_file],
                               cwd=workspace, capture_output=True, timeout=60)
            else:
                subprocess.run(['pip3', 'install', 'flask', 'pyyaml'],
                               capture_output=True, timeout=30)

            # Create a launcher script that handles app discovery
            launcher_content = _create_flask_launcher(workspace, app_rel, port)
            launcher_path = os.path.join(workspace, '_astradev_launcher.py')
            with open(launcher_path, 'w') as lf:
                lf.write(launcher_content)
            start_cmd = ['python3', '_astradev_launcher.py']

        elif has_fastapi and app_rel:
            req_file = os.path.join(workspace, 'requirements.txt')
            if os.path.isfile(req_file):
                subprocess.run(['pip3', 'install', '-r', req_file],
                               cwd=workspace, capture_output=True, timeout=60)
            else:
                subprocess.run(['pip3', 'install', 'fastapi', 'uvicorn'],
                               capture_output=True, timeout=30)
            module = app_rel.replace('.py', '').replace('/', '.')
            start_cmd = ['uvicorn', f'{module}:app', '--host', '0.0.0.0', '--port', str(port)]

        elif has_django:
            start_cmd = ['python3', 'manage.py', 'runserver', f'0.0.0.0:{port}']

        elif has_index_html:
            start_cmd = ['python3', '-m', 'http.server', str(port)]

        elif has_package_json:
            subprocess.run(['npm', 'install'], cwd=workspace, capture_output=True, timeout=60)
            start_cmd = ['npx', 'serve', '-l', str(port), '-s', '.']

        else:
            # Check for any .html files in subdirs
            html_files = [f for f in all_files if f.endswith('.html')]
            if html_files:
                # Find the directory with index.html
                for hf in html_files:
                    if os.path.basename(hf) == 'index.html':
                        cwd = os.path.dirname(os.path.join(workspace, hf)) or workspace
                        start_cmd = ['python3', '-m', 'http.server', str(port)]
                        break
                if not start_cmd:
                    start_cmd = ['python3', '-m', 'http.server', str(port)]
            else:
                # Generate an index page as last resort
                _generate_fallback_index(workspace, project.name, all_files)
                start_cmd = ['python3', '-m', 'http.server', str(port)]

        # Start the server process
        logger.info(f"Starting server for project {project_id}: {start_cmd} in {cwd}")
        server_process = subprocess.Popen(
            start_cmd, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            preexec_fn=os.setsid,
        )

        # Wait and verify server started
        time.sleep(3)
        if server_process.poll() is not None:
            stderr = server_process.stderr.read().decode()[:500]
            raise RuntimeError(f"Server failed to start: {stderr}")

        # Health check: verify the server responds with actual content
        deploy_verified = False
        ui_verified = False
        import urllib.request
        for check_attempt in range(4):
            try:
                req = urllib.request.Request(f'http://127.0.0.1:{port}/')
                req.add_header('User-Agent', 'AstraDev-HealthCheck')
                resp = urllib.request.urlopen(req, timeout=5)
                if resp.status < 500:
                    body = resp.read().decode('utf-8', errors='replace')[:2000]
                    deploy_verified = True

                    # UI Validation: check the response is actual rendered content
                    bad_indicators = [
                        'Traceback (most recent call last)',
                        'Internal Server Error',
                        'ModuleNotFoundError',
                        'ImportError',
                    ]
                    is_bad = any(ind in body for ind in bad_indicators)
                    if not is_bad and '<html' in body.lower():
                        ui_verified = True
                    elif not is_bad and len(body) > 50:
                        ui_verified = True
                    break
            except Exception as hc_err:
                logger.debug(f"Health check attempt {check_attempt+1} failed: {hc_err}")
                time.sleep(2)

        # Try /health endpoint
        health_ok = False
        try:
            req = urllib.request.Request(f'http://127.0.0.1:{port}/health')
            req.add_header('User-Agent', 'AstraDev-HealthCheck')
            resp = urllib.request.urlopen(req, timeout=3)
            if resp.status < 400:
                health_ok = True
        except Exception:
            pass

        if not deploy_verified:
            logger.warning(f"Health check failed for project {project_id} on port {port}")
        if not ui_verified:
            logger.warning(f"UI validation: response may not be rendering correctly for {project_id}")

        # Deploy URL
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
            'health_check': deploy_verified,
            'ui_verified': ui_verified,
            'health_endpoint': health_ok,
        })
        project.project_state['deploy_info'] = deploy_info
        project.save(update_fields=['deployment_url', 'status', 'project_state'])

        if deploy_verified and ui_verified:
            status_msg = "Deployment successful — app verified!"
        elif deploy_verified:
            status_msg = "Deployed — server running but UI not fully verified"
        else:
            status_msg = "Deployed (health check pending)"

        Message.objects.create(
            project=project, role='deployer',
            content=f"{status_msg} Your app is live at: {deploy_url}",
            message_type='deployment',
            metadata={
                'url': deploy_url, 'status': 'live', 'port': port,
                'verified': deploy_verified, 'ui_verified': ui_verified,
                'health_endpoint': health_ok,
            },
        )
        logger.info(f"Project {project_id} deployed at {deploy_url} (port {port}, verified={deploy_verified}, ui={ui_verified})")
        return {'status': 'deployed', 'url': deploy_url, 'verified': deploy_verified, 'ui_verified': ui_verified}

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


def _create_flask_launcher(workspace, app_rel, port):
    """Create a launcher script that properly imports and runs the Flask app."""
    # Determine if the app is in a package or a standalone file
    app_dir = os.path.dirname(app_rel)
    app_file = os.path.basename(app_rel)
    module_name = app_file.replace('.py', '')

    if app_dir:
        # App is inside a package (e.g., app/__init__.py)
        package_name = app_dir.replace('/', '.')
        if module_name == '__init__':
            import_line = f"from {package_name} import app"
            fallback = f"from {package_name} import create_app; app = create_app()"
        else:
            import_line = f"from {package_name}.{module_name} import app"
            fallback = f"import {package_name}.{module_name} as mod; app = getattr(mod, 'app', None) or getattr(mod, 'create_app', lambda: None)()"
    else:
        # Top-level file
        import_line = f"from {module_name} import app"
        fallback = f"import {module_name} as mod; app = getattr(mod, 'app', None) or getattr(mod, 'create_app', lambda: None)()"

    # Also register template and static folders
    return f'''import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = None
try:
    {import_line}
except ImportError:
    try:
        {fallback}
    except Exception as e2:
        print(f"Could not import app: {{e2}}")
        sys.exit(1)

if app is None:
    print("Could not find Flask app instance")
    sys.exit(1)

# Register template folder if exists
import os.path
for tmpl_dir in ['templates', 'chatbot/templates', 'app/templates']:
    full = os.path.join(os.path.dirname(os.path.abspath(__file__)), tmpl_dir)
    if os.path.isdir(full):
        app.template_folder = full
        break

# Register static folder if exists
for static_dir in ['static', 'chatbot/static', 'app/static']:
    full = os.path.join(os.path.dirname(os.path.abspath(__file__)), static_dir)
    if os.path.isdir(full):
        app.static_folder = full
        break

if __name__ == "__main__":
    app.run(host="0.0.0.0", port={port}, debug=False)
'''


def _generate_fallback_index(workspace, project_name, all_files):
    """Generate a fallback index.html that lists project files."""
    file_list = '\n'.join(f'<li>{f}</li>' for f in sorted(all_files) if not f.startswith('.'))
    html = f"""<!DOCTYPE html>
<html>
<head><title>{project_name} - Deployed by AstraDev</title>
<style>body{{font-family:system-ui;max-width:800px;margin:50px auto;padding:20px;background:#0d1117;color:#c9d1d9}}
h1{{color:#58a6ff}}pre{{background:#161b22;padding:15px;border-radius:8px;overflow-x:auto}}
a{{color:#58a6ff}}li{{margin:5px 0}}</style></head>
<body>
<h1>{project_name}</h1>
<p>Deployed via AstraDev</p>
<h2>Project Files</h2>
<ul>{file_list}</ul>
</body></html>"""
    with open(os.path.join(workspace, 'index.html'), 'w') as fh:
        fh.write(html)

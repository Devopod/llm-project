import json
import logging
import os
import hashlib
from datetime import datetime
from django.utils import timezone

from astradev.projects.models import Project, Task, FileRecord
from .base import BaseAgent
from .planner import PlannerAgent
from .writer import CodeWriterAgent
from .reader import CodeReaderAgent
from .reviewer import CodeReviewerAgent
from .tester import TestingAgent
from .debugger import DebugAgent
from .deployer import DeploymentAgent
from .documenter import DocumentationAgent
from .terminal import TerminalAgent
from .git_agent import GitAgent
from .security import SecurityAgent
from .browser_agent import BrowserAgent
from .refactor import RefactorAgent
from .memory import MemoryAgent

logger = logging.getLogger('astradev.agents')


class OrchestratorAgent(BaseAgent):
    role = 'orchestrator'
    system_prompt = """You are the Orchestrator Agent for AstraDev.
You coordinate the autonomous development process.
Analyze user requests, create plans, delegate to sub-agents, and ensure quality delivery."""

    def __init__(self, project: Project):
        super().__init__(project)
        self.planner = PlannerAgent(project)
        self.writer = CodeWriterAgent(project)
        self.reader = CodeReaderAgent(project)
        self.reviewer = CodeReviewerAgent(project)
        self.tester = TestingAgent(project)
        self.debugger = DebugAgent(project)
        self.deployer = DeploymentAgent(project)
        self.documenter = DocumentationAgent(project)
        self.terminal = TerminalAgent(project)
        self.git_agent = GitAgent(project)
        self.security = SecurityAgent(project)
        self.browser = BrowserAgent(project)
        self.refactor = RefactorAgent(project)
        self.memory = MemoryAgent(project)
        self.workspace_path = f"/tmp/astradev_workspaces/{project.id}"

    def execute(self, prompt: str, context: dict = None) -> dict:
        try:
            self.project.status = 'planning'
            self.project.save(update_fields=['status'])
            self.emit('thinking', f'Analyzing request: {prompt[:100]}...')

            # Phase 1: Planning
            plan = self.planner.execute(prompt, context)
            tasks = plan.get('tasks', [])
            self.project.roadmap = plan
            self.project.save(update_fields=['roadmap'])

            # Create Task records
            db_tasks = []
            for i, task_data in enumerate(tasks):
                db_task = Task.objects.create(
                    project=self.project,
                    task_type=task_data.get('type', 'write_code'),
                    title=task_data.get('title', f'Task {i+1}'),
                    description=task_data.get('description', ''),
                    status='pending',
                    assigned_agent=self._get_agent_for_type(task_data.get('type', 'write_code')),
                    order=i,
                    dependencies=task_data.get('dependencies', []),
                    input_data=task_data,
                )
                db_tasks.append(db_task)

            # Phase 2: Execution
            self.project.status = 'executing'
            self.project.save(update_fields=['status'])

            os.makedirs(self.workspace_path, exist_ok=True)

            for db_task in db_tasks:
                if self.project.status == 'paused':
                    self.emit('message', 'Execution paused by user')
                    return {'status': 'paused'}

                db_task.status = 'in_progress'
                db_task.started_at = timezone.now()
                db_task.save()

                self.emit('action', f'Working on: {db_task.title}')

                try:
                    result = self._execute_task(db_task, prompt)
                    db_task.status = 'completed'
                    db_task.output_data = result if isinstance(result, dict) else {'output': str(result)}
                    db_task.completed_at = timezone.now()
                    db_task.save()
                    self.emit('success', f'Completed: {db_task.title}')
                except Exception as e:
                    logger.error(f"Task failed: {db_task.title} - {e}")
                    db_task.retry_count += 1
                    if db_task.retry_count < db_task.max_retries:
                        db_task.status = 'pending'
                        db_task.error_log = str(e)
                        db_task.save()
                        self.emit('error', f'Task failed, retrying: {str(e)[:200]}')
                        # Retry with debug agent
                        try:
                            fix_result = self.debugger.execute(
                                f"Fix this error in task '{db_task.title}': {str(e)}",
                                {'error': str(e), 'code': json.dumps(db_task.input_data)}
                            )
                            db_task.status = 'completed'
                            db_task.output_data = fix_result
                            db_task.completed_at = timezone.now()
                            db_task.save()
                        except Exception as fix_error:
                            db_task.status = 'failed'
                            db_task.error_log = f"Original: {e}\nFix attempt: {fix_error}"
                            db_task.save()
                            self.emit('error', f'Task failed after retry: {db_task.title}')
                    else:
                        db_task.status = 'failed'
                        db_task.error_log = str(e)
                        db_task.save()
                        self.emit('error', f'Task failed: {db_task.title} - {str(e)[:200]}')

            # Phase 3: Finalize
            self._update_project_state()
            self.project.status = 'completed'
            self.project.completed_at = timezone.now()
            self.project.save()

            self.emit('success', f'Project completed! Files created in workspace.')
            return {'status': 'completed', 'project_state': self.project.project_state}

        except Exception as e:
            logger.error(f"Orchestrator error: {e}")
            self.project.status = 'failed'
            self.project.save(update_fields=['status'])
            self.emit('error', f'Project execution failed: {str(e)[:300]}')
            return {'status': 'failed', 'error': str(e)}

    def _execute_task(self, db_task: Task, original_prompt: str) -> dict:
        task_type = db_task.task_type
        description = db_task.description
        context = {
            'project_state': self.project.project_state,
            'original_prompt': original_prompt,
        }

        if task_type == 'write_code':
            result = self.writer.execute(description, context)
            # Write files to workspace
            for file_info in result.get('files', []):
                self._write_file(file_info['path'], file_info.get('content', ''))
            return result

        elif task_type == 'read_code':
            files_content = self._read_workspace_files()
            context['files_content'] = files_content
            return self.reader.execute(description, context)

        elif task_type == 'review':
            code = self._read_workspace_files()
            context['code'] = code
            return self.reviewer.execute(description, context)

        elif task_type == 'test':
            code = self._read_workspace_files()
            context['code'] = code
            result = self.tester.execute(description, context)
            for file_info in result.get('test_files', []):
                self._write_file(file_info['path'], file_info.get('content', ''))
            return result

        elif task_type == 'debug':
            return self.debugger.execute(description, context)

        elif task_type == 'deploy':
            return self.deployer.execute(description, context)

        elif task_type == 'document':
            result = self.documenter.execute(description, context)
            for file_info in result.get('files', []):
                self._write_file(file_info['path'], file_info.get('content', ''))
            return result

        elif task_type == 'terminal':
            context['workspace_path'] = self.workspace_path
            return self.terminal.execute(description, context)

        elif task_type == 'git':
            context['workspace_path'] = self.workspace_path
            return self.git_agent.execute(description, context)

        elif task_type == 'security':
            context['workspace_path'] = self.workspace_path
            code = self._read_workspace_files()
            context['code'] = code
            return self.security.execute(description, context)

        elif task_type == 'browser':
            return self.browser.execute(description, context)

        elif task_type == 'refactor':
            code = self._read_workspace_files()
            context['code'] = code
            result = self.refactor.execute(description, context)
            for file_info in result.get('files', []):
                self._write_file(file_info['path'], file_info.get('content', ''))
            return result

        else:
            return self.writer.execute(description, context)

    def _write_file(self, relative_path: str, content: str):
        full_path = os.path.join(self.workspace_path, relative_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w') as f:
            f.write(content)

        content_hash = hashlib.sha256(content.encode()).hexdigest()
        FileRecord.objects.update_or_create(
            project=self.project,
            path=relative_path,
            defaults={
                'action': 'created',
                'content_hash': content_hash,
                'size_bytes': len(content.encode()),
            }
        )

    def _read_workspace_files(self) -> str:
        result = []
        if not os.path.exists(self.workspace_path):
            return ''
        for root, dirs, files in os.walk(self.workspace_path):
            dirs[:] = [d for d in dirs if d not in ('node_modules', '.git', '__pycache__', 'venv', '.venv')]
            for fname in files[:50]:
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, self.workspace_path)
                try:
                    with open(fpath, 'r') as f:
                        content = f.read(2000)
                    result.append(f"--- {rel_path} ---\n{content}\n")
                except (UnicodeDecodeError, OSError):
                    pass
        return '\n'.join(result)[:5000]

    def _update_project_state(self):
        file_tree = {}
        if os.path.exists(self.workspace_path):
            for root, dirs, files in os.walk(self.workspace_path):
                dirs[:] = [d for d in dirs if d not in ('node_modules', '.git', '__pycache__')]
                for fname in files:
                    rel_path = os.path.relpath(os.path.join(root, fname), self.workspace_path)
                    file_tree[rel_path] = {'type': 'file', 'size': os.path.getsize(os.path.join(root, fname))}

        self.project.project_state = {
            'file_tree': file_tree,
            'workspace_path': self.workspace_path,
            'last_updated': datetime.utcnow().isoformat(),
        }
        self.project.save(update_fields=['project_state'])

    def _get_agent_for_type(self, task_type: str) -> str:
        mapping = {
            'plan': 'planner',
            'read_code': 'reader',
            'write_code': 'writer',
            'review': 'reviewer',
            'test': 'tester',
            'debug': 'debugger',
            'deploy': 'deployer',
            'document': 'documenter',
            'terminal': 'terminal',
            'git': 'git',
            'security': 'security',
            'browser': 'browser',
            'refactor': 'refactor',
        }
        return mapping.get(task_type, 'writer')

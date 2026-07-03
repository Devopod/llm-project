import json
import logging
import os
import hashlib
from datetime import datetime
from django.utils import timezone

from astradev.projects.models import Project, Task, FileRecord
from .base import BaseAgent
from .planner import PlannerAgent
from .validators import (
    validate_workspace, validate_file, validate_runtime,
    ValidationStatus, ProjectValidationReport,
)
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

    def _get_existing_files_context(self) -> str:
        """Build context about existing files in the workspace for uploaded projects."""
        if not os.path.isdir(self.workspace_path):
            return ''

        existing_files = []
        for root, dirs, fnames in os.walk(self.workspace_path):
            dirs[:] = [d for d in dirs if d not in ('__pycache__', 'node_modules', '.git', '.venv', 'venv')]
            for fname in fnames:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, self.workspace_path)
                if rel.startswith('_astradev'):
                    continue
                try:
                    size = os.path.getsize(full)
                except OSError:
                    size = 0
                existing_files.append(f"  {rel} ({size} bytes)")

        if not existing_files:
            return ''

        # Read first few lines of key files for context
        snippets = []
        for root, dirs, fnames in os.walk(self.workspace_path):
            dirs[:] = [d for d in dirs if d not in ('__pycache__', 'node_modules', '.git', '.venv')]
            for fname in fnames:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, self.workspace_path)
                if rel.startswith('_astradev'):
                    continue
                try:
                    with open(full, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read(500)
                    snippets.append(f"--- {rel} ---\n{content}")
                except Exception:
                    pass
                if len(snippets) >= 10:
                    break
            if len(snippets) >= 10:
                break

        ctx = f"\n\nEXISTING PROJECT FILES ({len(existing_files)} files):\n"
        ctx += "\n".join(existing_files[:50])
        if snippets:
            ctx += "\n\nFILE PREVIEWS:\n" + "\n\n".join(snippets)
        return ctx

    def execute(self, prompt: str, context: dict = None) -> dict:
        try:
            self.project.status = 'planning'
            self.project.save(update_fields=['status'])
            self.emit('thinking', f'Analyzing request: {prompt[:100]}...')

            # Detect if this is an existing project (uploaded or previously built)
            is_existing_project = bool(
                self.project.project_state.get('uploaded')
                or self.project.project_state.get('file_tree')
            )
            existing_context = self._get_existing_files_context() if is_existing_project else ''

            # Phase 1: Planning
            planning_context = context or {}
            if is_existing_project:
                planning_context['existing_project'] = True
                planning_context['existing_files_context'] = existing_context

            plan = self.planner.execute(prompt, planning_context)
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

            # Phase 3: Validation Pipeline
            self.emit('action', 'Running validation pipeline...')
            validation_passed = self._run_validation_pipeline()

            # Phase 4: Auto-fix errors from logs
            error_msgs = list(
                self.project.messages
                .filter(message_type='error')
                .order_by('-created_at')[:3]
            )
            fix_attempts = 0
            while error_msgs and fix_attempts < 3:
                fix_attempts += 1
                for err_msg in error_msgs:
                    self.emit('action', f'Auto-fix attempt {fix_attempts}: {err_msg.content[:100]}')
                    try:
                        files_content = self._read_workspace_files()
                        fix_result = self.debugger.execute(
                            f"Fix this error: {err_msg.content}",
                            {'error': err_msg.content, 'code': files_content}
                        )
                        for file_info in fix_result.get('files', []):
                            self._write_file(file_info['path'], file_info.get('content', ''))
                        self.emit('fix', f'Applied fix for: {err_msg.content[:100]}')
                    except Exception as fix_err:
                        self.emit('error', f'Auto-fix failed: {str(fix_err)[:200]}')
                error_msgs = list(
                    self.project.messages
                    .filter(message_type='error', created_at__gt=error_msgs[0].created_at)
                    .order_by('-created_at')[:3]
                )

            # Re-validate after fixes if there were problems
            if not validation_passed:
                self.emit('action', 'Re-validating after auto-fix...')
                validation_passed = self._run_validation_pipeline()

            # Phase 5: Multi-agent review
            self._run_multi_agent_review()

            # Phase 6: Store file hashes and metadata
            self._store_file_metadata()

            # Phase 7: Project completion gate
            self._update_project_state()
            if validation_passed:
                self.project.status = 'completed'
                self.project.completed_at = timezone.now()
                self.emit('success', 'Project completed — all validations passed!')
            else:
                self.project.status = 'completed'
                self.project.completed_at = timezone.now()
                self.emit('action', 'Project completed with warnings — some validations had issues')
            self.project.save()

            # Phase 8: Auto-deploy prompt
            self.emit('deploy_prompt', 'Project is ready for deployment. Would you like to deploy this app to a public URL?')

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
            # Pass full content of existing files so the writer can merge changes
            existing_file_contents = self._read_workspace_file_contents()
            if existing_file_contents:
                context['existing_file_contents'] = existing_file_contents
                context['existing_files'] = list(existing_file_contents.keys())
            result = self.writer.execute(description, context)
            for file_info in result.get('files', []):
                path = file_info.get('path', '')
                content = file_info.get('content', '')
                if path and content:
                    self._write_file(path, content)
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

    def _read_workspace_file_contents(self) -> dict:
        """Read full content of all workspace files for context-aware editing."""
        contents = {}
        if not os.path.exists(self.workspace_path):
            return contents
        skip_dirs = {'node_modules', '.git', '__pycache__', 'venv', '.venv'}
        skip_prefixes = ('_astradev',)
        for root, dirs, files in os.walk(self.workspace_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for fname in files:
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, self.workspace_path)
                if any(rel_path.startswith(p) for p in skip_prefixes):
                    continue
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read(4000)
                    contents[rel_path] = content
                except (UnicodeDecodeError, OSError):
                    pass
                if len(contents) >= 20:
                    break
            if len(contents) >= 20:
                break
        return contents

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

    def _run_validation_pipeline(self) -> bool:
        """Run the full validation pipeline on all workspace files.
        Returns True if all files pass, False otherwise."""
        if not os.path.exists(self.workspace_path):
            self.emit('action', 'No workspace to validate')
            return True

        report = validate_workspace(self.workspace_path)
        total = len(report.file_reports)
        passed = sum(1 for r in report.file_reports if r.passed)

        self.emit('action', f'Validation: {passed}/{total} files passed')

        if report.passed:
            return True

        # Auto-repair failed files
        for file_report in report.failed_files:
            path = file_report.file_path
            failures = file_report.failures
            fail_msgs = '; '.join(f.message for f in failures[:3])
            self.emit('action', f'Repairing {path}: {fail_msgs}')

            full_path = os.path.join(self.workspace_path, path)
            try:
                with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()

                repair_result = self.writer.execute(
                    f"Fix the validation errors in '{path}'. Errors: {fail_msgs}. "
                    f"Rewrite the COMPLETE corrected file. Current content:\n{content[:2000]}",
                    {}
                )
                for fi in repair_result.get('files', []):
                    new_content = fi.get('content', '')
                    if new_content and len(new_content.strip()) > 10:
                        new_report = validate_file(new_content, path)
                        if new_report.passed or len(new_report.failures) < len(failures):
                            self._write_file(fi.get('path', path), new_content)
                            if new_report.passed:
                                self.emit('fix', f'Repaired {path}')
                            break
            except Exception as e:
                logger.warning(f"Validation repair failed for {path}: {e}")

        # Re-check after repairs
        final_report = validate_workspace(self.workspace_path)
        final_passed = sum(1 for r in final_report.file_reports if r.passed)
        self.emit('action', f'Post-repair validation: {final_passed}/{len(final_report.file_reports)} files passed')

        # Store validation report in project state
        self.project.project_state['validation'] = {
            'total_files': len(final_report.file_reports),
            'passed': final_passed,
            'failed_files': [r.file_path for r in final_report.failed_files],
            'timestamp': datetime.utcnow().isoformat(),
        }
        self.project.save(update_fields=['project_state'])

        return final_report.passed

    def _run_multi_agent_review(self):
        """Run multi-agent review on generated files."""
        try:
            files_content = self._read_workspace_files()
            if not files_content:
                return

            # Reviewer pass
            self.emit('action', 'Running code review...')
            try:
                review_result = self.reviewer.execute(
                    f"Review the code quality and completeness of this project. "
                    f"Check for: missing error handling, security issues, incomplete logic.\n{files_content[:3000]}",
                    {}
                )
                if review_result.get('issues'):
                    for issue in review_result['issues'][:3]:
                        self.emit('action', f'Review: {issue.get("description", "")[:100]}')
            except Exception as e:
                logger.debug(f"Review pass error: {e}")

            # Security pass
            self.emit('action', 'Running security check...')
            try:
                security_result = self.security.execute(
                    f"Check for security vulnerabilities: hardcoded secrets, SQL injection, XSS, path traversal.\n{files_content[:3000]}",
                    {}
                )
                if security_result.get('vulnerabilities'):
                    for vuln in security_result['vulnerabilities'][:3]:
                        self.emit('action', f'Security: {vuln.get("description", "")[:100]}')
            except Exception as e:
                logger.debug(f"Security pass error: {e}")
        except Exception as e:
            logger.debug(f"Multi-agent review error: {e}")

    def _store_file_metadata(self):
        """Store SHA256, line count, byte count, validation status for every file."""
        if not os.path.exists(self.workspace_path):
            return

        skip_dirs = {'node_modules', '.git', '__pycache__', 'venv', '.venv'}
        for root, dirs, files in os.walk(self.workspace_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for fname in files:
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, self.workspace_path)
                try:
                    with open(fpath, 'rb') as f:
                        raw = f.read()
                    content = raw.decode('utf-8', errors='replace')
                    sha = hashlib.sha256(raw).hexdigest()

                    report = validate_file(content, rel)

                    FileRecord.objects.update_or_create(
                        project=self.project,
                        path=rel,
                        defaults={
                            'action': 'validated',
                            'content_hash': sha,
                            'size_bytes': len(raw),
                            'metadata': {
                                'line_count': content.count('\n') + 1,
                                'encoding': 'utf-8',
                                'syntax_ok': report.syntax_ok,
                                'eof_ok': report.eof_ok,
                                'validation_passed': report.passed,
                                'validators': [
                                    {'name': r.validator, 'status': r.status.value, 'message': r.message}
                                    for r in report.results
                                ],
                            },
                        }
                    )
                except Exception as e:
                    logger.debug(f"Metadata store error for {rel}: {e}")

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

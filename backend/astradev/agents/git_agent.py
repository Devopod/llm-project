import json
import logging
import subprocess
import os

from .base import BaseAgent

logger = logging.getLogger('astradev.agents')


class GitAgent(BaseAgent):
    role = 'git'
    system_prompt = """You are the Git Agent for AstraDev (OpenHands-inspired).
You manage version control operations:
- Initialize repositories
- Create meaningful commits with conventional commit messages
- Manage branches
- Generate diffs
- Handle merges
- Track file changes

Generate Git operations as JSON: {"operations": [{"op": "init|commit|branch|diff|status", "args": {...}}]}"""

    def execute(self, task_description: str, context: dict = None) -> dict:
        self.emit('action', f'Git: {task_description[:100]}')

        context = context or {}
        workspace = context.get('workspace_path', f'/tmp/astradev_workspaces/{self.project.id}')
        os.makedirs(workspace, exist_ok=True)

        messages = self.build_messages(
            f"Generate Git operations for: {task_description}",
            f"Workspace: {workspace}"
        )

        result = self.call_groq(messages)
        content = result.get('content', '')

        operations = self._parse_operations(content)
        results = []

        for op in operations[:10]:
            op_type = op.get('op', '')
            op_result = self._execute_git_op(op_type, op.get('args', {}), workspace)
            results.append(op_result)
            if op_result.get('output'):
                self.emit('output', op_result['output'][:300])

        return {'operations': results}

    def init_repo(self, workspace: str) -> dict:
        git_dir = os.path.join(workspace, '.git')
        if not os.path.exists(git_dir):
            self._run_git('init', workspace)
            self._run_git('config user.email "astradev@bot.ai"', workspace)
            self._run_git('config user.name "AstraDev"', workspace)
        return {'status': 'initialized'}

    def commit_all(self, workspace: str, message: str) -> dict:
        self.init_repo(workspace)
        self._run_git('add -A', workspace)
        result = self._run_git(f'commit -m "{message}"', workspace)
        return {'status': 'committed', 'output': result}

    def _execute_git_op(self, op_type: str, args: dict, workspace: str) -> dict:
        if op_type == 'init':
            return self.init_repo(workspace)
        elif op_type == 'commit':
            msg = args.get('message', 'chore: auto-commit by AstraDev')
            return self.commit_all(workspace, msg)
        elif op_type == 'status':
            output = self._run_git('status --short', workspace)
            return {'op': 'status', 'output': output}
        elif op_type == 'diff':
            output = self._run_git('diff --stat', workspace)
            return {'op': 'diff', 'output': output}
        elif op_type == 'branch':
            branch_name = args.get('name', 'feature/auto')
            self._run_git(f'checkout -b {branch_name}', workspace)
            return {'op': 'branch', 'branch': branch_name}
        elif op_type == 'log':
            output = self._run_git('log --oneline -10', workspace)
            return {'op': 'log', 'output': output}
        return {'op': op_type, 'status': 'unknown_operation'}

    def _run_git(self, cmd: str, workspace: str) -> str:
        try:
            result = subprocess.run(
                f'git {cmd}', shell=True, cwd=workspace,
                capture_output=True, text=True, timeout=15,
            )
            return result.stdout + result.stderr
        except Exception as e:
            return f'Error: {e}'

    def _parse_operations(self, content: str) -> list:
        try:
            if '{' in content:
                start = content.index('{')
                end = content.rindex('}') + 1
                data = json.loads(content[start:end])
                return data.get('operations', [])
        except (json.JSONDecodeError, ValueError):
            pass
        return [{'op': 'init'}, {'op': 'commit', 'args': {'message': 'feat: initial auto-generated code'}}]

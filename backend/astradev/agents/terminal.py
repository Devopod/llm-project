import json
import logging
import subprocess
import os

from .base import BaseAgent

logger = logging.getLogger('astradev.agents')


class TerminalAgent(BaseAgent):
    role = 'terminal'
    system_prompt = """You are the Terminal Agent for AstraDev (OpenHands-inspired).
You execute shell commands in isolated sandboxes to:
- Install dependencies (npm, pip, gradle, cargo)
- Run build commands
- Execute test suites
- Manage processes
- Run linting/formatting tools

You MUST validate commands before execution and never run destructive operations
on the host system. Only execute within the project workspace sandbox.

Output commands as JSON: {"commands": [{"cmd": "...", "description": "..."}]}"""

    def execute(self, task_description: str, context: dict = None) -> dict:
        self.emit('action', f'Terminal: Analyzing task - {task_description[:100]}')

        context = context or {}
        workspace = context.get('workspace_path', f'/tmp/astradev_workspaces/{self.project.id}')

        messages = self.build_messages(
            f"Generate shell commands to: {task_description}\nWorkspace: {workspace}",
            json.dumps(context.get('project_state', {}))[:400]
        )

        result = self.call_groq(messages)
        content = result.get('content', '')

        # Parse commands from LLM response
        commands = self._parse_commands(content)
        outputs = []

        for cmd_info in commands[:5]:  # Max 5 commands per invocation
            cmd = cmd_info.get('cmd', '')
            if not cmd or self._is_dangerous(cmd):
                outputs.append({'cmd': cmd, 'status': 'blocked', 'output': 'Command blocked for safety'})
                continue

            self.emit('action', f'$ {cmd}')
            output = self._safe_execute(cmd, workspace)
            outputs.append({'cmd': cmd, 'status': 'success' if output['returncode'] == 0 else 'failed', **output})
            self.emit('output', output.get('stdout', '')[:500] or output.get('stderr', '')[:500])

        return {'commands_executed': len(outputs), 'outputs': outputs}

    def _parse_commands(self, content: str) -> list:
        try:
            if '{' in content:
                start = content.index('{')
                end = content.rindex('}') + 1
                data = json.loads(content[start:end])
                return data.get('commands', [])
        except (json.JSONDecodeError, ValueError):
            pass
        # Fallback: treat each line starting with $ or common commands
        commands = []
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('$ '):
                commands.append({'cmd': line[2:], 'description': ''})
            elif any(line.startswith(pre) for pre in ['npm ', 'pip ', 'python ', 'gradle ', 'cargo ', 'make ']):
                commands.append({'cmd': line, 'description': ''})
        return commands

    def _is_dangerous(self, cmd: str) -> bool:
        dangerous = ['rm -rf /', 'sudo rm', 'mkfs', 'dd if=', ':(){', 'chmod 777 /',
                     'curl | bash', 'wget | sh', 'shutdown', 'reboot', 'init 0']
        return any(d in cmd.lower() for d in dangerous)

    def _safe_execute(self, cmd: str, workspace: str) -> dict:
        os.makedirs(workspace, exist_ok=True)
        try:
            result = subprocess.run(
                cmd, shell=True, cwd=workspace,
                capture_output=True, text=True, timeout=30,
                env={**os.environ, 'HOME': workspace}
            )
            return {
                'stdout': result.stdout[:2000],
                'stderr': result.stderr[:2000],
                'returncode': result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {'stdout': '', 'stderr': 'Command timed out (30s)', 'returncode': -1}
        except Exception as e:
            return {'stdout': '', 'stderr': str(e), 'returncode': -1}

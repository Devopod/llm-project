import os
import shutil
import subprocess
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger('astradev.workspaces')

WORKSPACE_BASE = '/tmp/astradev_workspaces'


@dataclass
class ExecuteResult:
    stdout: str
    stderr: str
    exit_code: int


@dataclass
class FileInfo:
    path: str
    is_dir: bool
    size: int


class WorkspaceManager:
    def __init__(self):
        os.makedirs(WORKSPACE_BASE, exist_ok=True)

    def create_workspace(self, project_id: str) -> str:
        workspace_path = os.path.join(WORKSPACE_BASE, project_id)
        os.makedirs(workspace_path, exist_ok=True)
        return workspace_path

    def destroy_workspace(self, project_id: str):
        workspace_path = os.path.join(WORKSPACE_BASE, project_id)
        if os.path.exists(workspace_path):
            shutil.rmtree(workspace_path)

    def execute_command(self, project_id: str, command: str, timeout: int = 120) -> ExecuteResult:
        workspace_path = os.path.join(WORKSPACE_BASE, project_id)
        if not os.path.exists(workspace_path):
            os.makedirs(workspace_path)
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return ExecuteResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return ExecuteResult(stdout='', stderr='Command timed out', exit_code=-1)
        except Exception as e:
            return ExecuteResult(stdout='', stderr=str(e), exit_code=-1)

    def write_file(self, project_id: str, file_path: str, content: str):
        workspace_path = os.path.join(WORKSPACE_BASE, project_id)
        full_path = os.path.join(workspace_path, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w') as f:
            f.write(content)

    def read_file(self, project_id: str, file_path: str) -> Optional[str]:
        workspace_path = os.path.join(WORKSPACE_BASE, project_id)
        full_path = os.path.join(workspace_path, file_path)
        if not os.path.exists(full_path):
            return None
        with open(full_path, 'r') as f:
            return f.read()

    def list_files(self, project_id: str, path: str = '.') -> list:
        workspace_path = os.path.join(WORKSPACE_BASE, project_id)
        target = os.path.join(workspace_path, path)
        if not os.path.exists(target):
            return []

        result = []
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if d not in ('node_modules', '.git', '__pycache__', 'venv')]
            for d in dirs:
                rel = os.path.relpath(os.path.join(root, d), workspace_path)
                result.append(FileInfo(path=rel, is_dir=True, size=0))
            for f in files:
                fpath = os.path.join(root, f)
                rel = os.path.relpath(fpath, workspace_path)
                result.append(FileInfo(path=rel, is_dir=False, size=os.path.getsize(fpath)))
        return result

    def download_workspace_zip(self, project_id: str) -> Optional[str]:
        workspace_path = os.path.join(WORKSPACE_BASE, project_id)
        if not os.path.exists(workspace_path):
            return None
        zip_path = f"/tmp/astradev_download_{project_id}"
        shutil.make_archive(zip_path, 'zip', workspace_path)
        return f"{zip_path}.zip"


workspace_manager = WorkspaceManager()

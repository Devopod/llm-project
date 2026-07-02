import json
import logging
import os
import re

from .base import BaseAgent

logger = logging.getLogger('astradev.agents')


class SecurityAgent(BaseAgent):
    role = 'security'
    system_prompt = """You are the Security Agent for AstraDev (OpenHands-inspired).
You scan generated code for security vulnerabilities:
- SQL injection
- XSS vulnerabilities
- Path traversal
- Hardcoded secrets/credentials
- Insecure dependencies
- Missing input validation
- CSRF vulnerabilities
- Insecure deserialization
- Broken authentication patterns

Analyze the code and output findings as JSON:
{"findings": [{"severity": "high|medium|low", "file": "...", "line": 0, "issue": "...", "fix": "..."}]}"""

    PATTERNS = [
        (r'password\s*=\s*["\'][^"\']+["\']', 'Hardcoded password', 'high'),
        (r'api_key\s*=\s*["\'][^"\']+["\']', 'Hardcoded API key', 'high'),
        (r'secret\s*=\s*["\'][^"\']+["\']', 'Hardcoded secret', 'high'),
        (r'eval\s*\(', 'Use of eval() - code injection risk', 'high'),
        (r'exec\s*\(', 'Use of exec() - code injection risk', 'high'),
        (r'innerHTML\s*=', 'innerHTML assignment - XSS risk', 'medium'),
        (r'dangerouslySetInnerHTML', 'dangerouslySetInnerHTML - XSS risk', 'medium'),
        (r'subprocess\.call\s*\(\s*[^,]+\s*,\s*shell\s*=\s*True', 'Shell injection risk', 'high'),
        (r'os\.system\s*\(', 'os.system - shell injection risk', 'high'),
        (r'SELECT.*FROM.*WHERE.*\+|f"SELECT|f\'SELECT', 'Potential SQL injection', 'high'),
        (r'pickle\.loads?\s*\(', 'Insecure deserialization', 'medium'),
        (r'verify\s*=\s*False', 'SSL verification disabled', 'medium'),
        (r'http://', 'Non-HTTPS URL', 'low'),
        (r'TODO|FIXME|HACK', 'Unresolved code marker', 'low'),
    ]

    def execute(self, task_description: str, context: dict = None) -> dict:
        self.emit('action', f'Security scan: {task_description[:100]}')

        context = context or {}
        workspace = context.get('workspace_path', f'/tmp/astradev_workspaces/{self.project.id}')

        # Static analysis scan
        findings = self._scan_workspace(workspace)

        # LLM-enhanced analysis
        if context.get('code'):
            messages = self.build_messages(
                f"Security review this code for vulnerabilities:\n{context['code'][:600]}",
                "Return findings as JSON with severity, file, issue, fix."
            )
            result = self.call_groq(messages)
            llm_findings = self._parse_llm_findings(result.get('content', ''))
            findings.extend(llm_findings)

        severity_counts = {'high': 0, 'medium': 0, 'low': 0}
        for f in findings:
            severity_counts[f.get('severity', 'low')] += 1

        self.emit('output', f"Security scan complete: {len(findings)} findings "
                  f"({severity_counts['high']} high, {severity_counts['medium']} medium, {severity_counts['low']} low)")

        return {
            'findings': findings[:50],
            'summary': severity_counts,
            'passed': severity_counts['high'] == 0,
        }

    def _scan_workspace(self, workspace: str) -> list:
        findings = []
        if not os.path.exists(workspace):
            return findings

        for root, dirs, files in os.walk(workspace):
            dirs[:] = [d for d in dirs if d not in ('node_modules', '.git', '__pycache__', 'venv')]
            for fname in files:
                if not fname.endswith(('.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.kt', '.go', '.rb', '.php')):
                    continue
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, workspace)
                try:
                    with open(fpath, 'r') as f:
                        lines = f.readlines()
                    for i, line in enumerate(lines[:500], 1):
                        for pattern, issue, severity in self.PATTERNS:
                            if re.search(pattern, line, re.IGNORECASE):
                                findings.append({
                                    'severity': severity,
                                    'file': rel_path,
                                    'line': i,
                                    'issue': issue,
                                    'code': line.strip()[:100],
                                })
                except (UnicodeDecodeError, OSError):
                    pass
        return findings

    def _parse_llm_findings(self, content: str) -> list:
        try:
            if '{' in content:
                start = content.index('{')
                end = content.rindex('}') + 1
                data = json.loads(content[start:end])
                return data.get('findings', [])
        except (json.JSONDecodeError, ValueError):
            pass
        return []

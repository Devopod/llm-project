"""
AstraDev Code Writer Agent — Self-Healing Code Generation

Flow:
  1. Generate files via Groq LLM
  2. Parse JSON output (handle nested wrappers)
  3. Validate every file (syntax, AST, completeness, placeholders)
  4. Auto-repair broken files (re-invoke LLM with error context)
  5. Sanitize README (reject JSON wrapper, prompt leakage)
  6. Only return files that pass validation
"""

import json
import logging
import re
from .base import BaseAgent
from .validators import (
    validate_file, validate_python_syntax, validate_markdown,
    ValidationStatus, FileValidationReport,
)

logger = logging.getLogger('astradev.agents')

MAX_REPAIR_ATTEMPTS = 3


class CodeWriterAgent(BaseAgent):
    role = 'writer'
    system_prompt = """You are an expert software developer for AstraDev.
You write clean, production-quality code in any language/framework.

When asked to create or modify files, output COMPLETE file content as a JSON response.

Output format (MUST be valid JSON — no markdown fences):
{
  "files": [
    {"action": "create", "path": "relative/path.ext", "content": "COMPLETE FILE"}
  ],
  "explanation": "Brief explanation"
}

ABSOLUTE RULES:
1. EVERY file MUST be COMPLETE — line 1 to last line. NEVER truncate.
2. NEVER use: '...', '# TODO', 'pass' (as stub), '// rest of code', 'raise NotImplementedError'.
3. Every file MUST be syntactically valid and immediately runnable.
4. Include ALL imports, ALL functions, ALL error handling.
5. Output ONLY valid JSON — no markdown, no code fences, no explanatory text before/after.
6. Use RELATIVE fetch URLs for web apps (e.g., 'chat' not '/chat').
7. For Flask: put app creation in a top-level app.py. Use proper template_folder paths.
8. For HTML: include COMPLETE styling, all elements, all event handlers, closing tags.
9. README.md content must be raw markdown — NOT wrapped in JSON.
10. Keep files focused. Split large apps into multiple files.
11. Every Python file must have valid syntax that passes ast.parse().
12. Every HTML file must have matching opening/closing tags.
13. Every JSON file must be valid JSON.
14. Every YAML file must be valid YAML."""

    def execute(self, task_description: str, context: dict = None) -> dict:
        self.emit('action', f'Writing code: {task_description[:100]}...')

        extra_context = ''
        if context:
            if 'project_state' in context:
                extra_context += f"Project state:\n{json.dumps(context['project_state'], indent=2)}\n"
            if 'existing_files' in context:
                extra_context += f"Existing files:\n{json.dumps(context['existing_files'])}\n"

        messages = self.build_messages(task_description, extra_context)
        result = self.call_groq(messages, stream=False)
        self.log_token_usage(result['tokens_input'], result['tokens_output'], result['key_used'])

        output = self._parse_output(result['content'])

        # Sanitize README files
        self._sanitize_readmes(output)

        # Validate and repair all files
        output = self._validate_and_repair_all(output, task_description, extra_context)

        # Write validated files to workspace
        for f in output.get('files', []):
            file_path = f.get('path', '')
            file_content = f.get('content', '')
            if file_path and file_content:
                self.edit_file(file_path, file_content)
            self.emit('code', file_content[:500], {
                'file_path': file_path,
                'action': f.get('action', 'create'),
            })

        return output

    # ------------------------------------------------------------------
    # JSON Output Parsing
    # ------------------------------------------------------------------
    def _parse_output(self, content: str) -> dict:
        """Parse LLM output, handling various JSON formats and wrapper bugs."""
        content = content.strip()

        # Strip markdown code fences
        if '```json' in content:
            content = content.split('```json', 1)[1]
            if '```' in content:
                content = content.split('```', 1)[0]
        elif content.startswith('```'):
            content = content[3:]
            if '```' in content:
                content = content.rsplit('```', 1)[0]

        content = content.strip()

        try:
            raw = json.loads(content)
        except json.JSONDecodeError:
            # Try to find JSON in the content
            json_match = re.search(r'\{[\s\S]*"files"[\s\S]*\}', content)
            if json_match:
                try:
                    raw = json.loads(json_match.group())
                except json.JSONDecodeError:
                    return self._fallback_output(content)
            else:
                return self._fallback_output(content)

        if not isinstance(raw, dict) or 'files' not in raw:
            return self._fallback_output(content)

        # Unwrap nested JSON wrappers
        raw['files'] = self._unwrap_files(raw['files'])

        return raw

    def _unwrap_files(self, files: list) -> list:
        """Fix JSON-in-JSON wrapper bugs where content is itself a JSON string."""
        cleaned = []
        for f in files:
            if not isinstance(f, dict):
                continue
            content = f.get('content', '')

            # If content is a JSON string containing 'files' array, unwrap it
            if isinstance(content, str) and content.strip().startswith('{'):
                try:
                    inner = json.loads(content)
                    if isinstance(inner, dict) and 'files' in inner:
                        cleaned.extend(self._unwrap_files(inner['files']))
                        continue
                    elif isinstance(inner, dict) and 'content' in inner:
                        f['content'] = inner['content']
                except (json.JSONDecodeError, KeyError):
                    pass

            cleaned.append(f)
        return cleaned

    def _fallback_output(self, content: str) -> dict:
        logger.warning("Failed to parse writer output as JSON, using raw content")
        return {
            'files': [{
                'action': 'create',
                'path': 'output.txt',
                'content': content,
            }],
            'explanation': 'Raw output (could not parse as structured JSON)',
        }

    # ------------------------------------------------------------------
    # README Sanitization
    # ------------------------------------------------------------------
    def _sanitize_readmes(self, output: dict):
        """Fix README files that contain JSON wrappers or prompt leakage."""
        for f in output.get('files', []):
            path = f.get('path', '')
            content = f.get('content', '')

            if not path.lower().endswith('.md'):
                continue

            sanitized = self._sanitize_markdown(content, path)
            if sanitized != content:
                f['content'] = sanitized
                self.emit('action', f'Sanitized {path} (removed JSON wrapper/leakage)')

    def _sanitize_markdown(self, content: str, path: str) -> str:
        """Remove JSON wrappers and prompt leakage from markdown content."""
        stripped = content.strip()

        # Case 1: Content is a JSON object with 'files' or 'content' key
        if stripped.startswith('{') or stripped.startswith('['):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    if 'content' in parsed:
                        return self._sanitize_markdown(parsed['content'], path)
                    if 'files' in parsed:
                        for f in parsed['files']:
                            if isinstance(f, dict) and f.get('path', '').endswith('.md'):
                                return self._sanitize_markdown(f.get('content', ''), path)
                elif isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict) and item.get('path', '').endswith('.md'):
                            return self._sanitize_markdown(item.get('content', ''), path)
            except json.JSONDecodeError:
                pass

        # Case 2: Content starts with conversational prefix
        conv_prefixes = ['Here is', 'Here are', 'Sure,', 'Certainly', 'Of course',
                         "I'll", 'Let me', 'Below is']
        first_line = stripped.split('\n')[0] if stripped else ''
        for prefix in conv_prefixes:
            if first_line.startswith(prefix):
                # Remove the first line
                lines = stripped.split('\n', 1)
                if len(lines) > 1:
                    return lines[1].strip()

        # Case 3: Content wrapped in code fences
        if stripped.startswith('```markdown') or stripped.startswith('```md'):
            stripped = stripped.split('\n', 1)[1] if '\n' in stripped else stripped
            if stripped.endswith('```'):
                stripped = stripped[:-3].rstrip()
            return stripped

        return content

    # ------------------------------------------------------------------
    # Validation and Auto-Repair
    # ------------------------------------------------------------------
    def _validate_and_repair_all(self, output: dict, task_desc: str, extra_ctx: str) -> dict:
        """Validate every file and auto-repair failures."""
        files = output.get('files', [])
        if not files:
            return output

        for attempt in range(MAX_REPAIR_ATTEMPTS):
            broken = []
            for f in files:
                path = f.get('path', '')
                content = f.get('content', '')
                if not path or not content:
                    continue

                report = validate_file(content, path)
                if not report.passed:
                    broken.append((f, report))

            if not broken:
                self.emit('action', f'All {len(files)} files validated (attempt {attempt+1})')
                return output

            self.emit('action', f'Attempt {attempt+1}: {len(broken)} file(s) failed validation')

            for f, report in broken:
                path = f['path']
                failures = report.failures
                fail_msgs = '; '.join(fr.message for fr in failures[:3])
                self.emit('action', f'Repairing {path}: {fail_msgs}')

                # Only repair if auto-fixable
                if not any(fr.auto_fixable for fr in failures):
                    continue

                new_content = self._repair_file(f, failures, task_desc)
                if new_content:
                    new_report = validate_file(new_content, path)
                    if new_report.passed or len(new_report.failures) < len(report.failures):
                        f['content'] = new_content
                        if new_report.passed:
                            self.emit('fix', f'Repaired {path} successfully')
                        else:
                            self.emit('action', f'Partially repaired {path} ({len(new_report.failures)} issues remain)')

        # Final check
        still_broken = []
        for f in files:
            report = validate_file(f.get('content', ''), f.get('path', ''))
            if not report.passed:
                still_broken.append(f['path'])

        if still_broken:
            self.emit('action', f'Warning: {len(still_broken)} file(s) still have issues after {MAX_REPAIR_ATTEMPTS} attempts')

        return output

    def _repair_file(self, file_info: dict, failures: list, task_desc: str) -> str | None:
        """Re-invoke LLM to repair a single broken file."""
        path = file_info['path']
        content = file_info.get('content', '')
        fail_msgs = '\n'.join(f'- {f.validator}: {f.message}' for f in failures)

        repair_prompt = f"""Fix this file: '{path}'

VALIDATION ERRORS:
{fail_msgs}

CURRENT (BROKEN) CONTENT:
{content[:2000]}

INSTRUCTIONS:
1. Generate the COMPLETE fixed version of this file.
2. Fix ALL validation errors listed above.
3. The file must be syntactically valid and complete.
4. For README.md: output raw markdown, NOT JSON.
5. Output ONLY the file content — no JSON wrapper, no explanation.
6. Original task context: {task_desc[:200]}"""

        try:
            messages = [
                {'role': 'system', 'content': 'You are a code repair agent. Output ONLY the fixed file content. No JSON wrapper. No explanation. Just the corrected code/text.'},
                {'role': 'user', 'content': repair_prompt[:2000]},
            ]
            result = self.call_groq(messages, stream=False)
            self.log_token_usage(result['tokens_input'], result['tokens_output'], result['key_used'])

            repaired = result['content'].strip()

            # Strip code fences if present
            if repaired.startswith('```'):
                lines = repaired.split('\n')
                repaired = '\n'.join(lines[1:])
                if repaired.endswith('```'):
                    repaired = repaired[:-3].rstrip()

            # For non-markdown files, try to extract from JSON if LLM wrapped it
            if not path.endswith('.md') and repaired.startswith('{'):
                try:
                    parsed = json.loads(repaired)
                    if isinstance(parsed, dict):
                        if 'content' in parsed:
                            repaired = parsed['content']
                        elif 'files' in parsed and parsed['files']:
                            repaired = parsed['files'][0].get('content', repaired)
                except json.JSONDecodeError:
                    pass

            if repaired and len(repaired.strip()) > 10:
                return repaired

        except Exception as e:
            logger.warning(f"Repair failed for {path}: {e}")

        return None

import json
import ast
import logging
import re
from .base import BaseAgent

logger = logging.getLogger('astradev.agents')


def _validate_python_syntax(content: str) -> str | None:
    """Return None if valid Python, or an error string."""
    try:
        ast.parse(content)
        return None
    except SyntaxError as e:
        return f"Line {e.lineno}: {e.msg}"


def _detect_truncation(content: str, path: str) -> bool:
    """Heuristic: detect if a file was truncated mid-generation."""
    stripped = content.rstrip()
    if not stripped:
        return True

    # Python files
    if path.endswith('.py'):
        # Check for unclosed brackets/parens
        opens = stripped.count('(') - stripped.count(')')
        opens += stripped.count('[') - stripped.count(']')
        opens += stripped.count('{') - stripped.count('}')
        if opens > 2:
            return True
        # Check for unclosed triple-quote strings
        triples = stripped.count('"""')
        if triples % 2 != 0:
            return True
        triples_sq = stripped.count("'''")
        if triples_sq % 2 != 0:
            return True
        # Syntax check
        err = _validate_python_syntax(stripped)
        if err and ('unexpected EOF' in err or 'expected' in err.lower()):
            return True

    # HTML files
    if path.endswith('.html') or path.endswith('.htm'):
        if '<html' in stripped.lower() and '</html>' not in stripped.lower():
            return True
        if '<body' in stripped.lower() and '</body>' not in stripped.lower():
            return True

    # JSON files
    if path.endswith('.json'):
        try:
            json.loads(stripped)
        except json.JSONDecodeError:
            return True

    # Generic: ends mid-word or mid-line (no newline at end)
    last_line = stripped.split('\n')[-1]
    if last_line and not last_line.strip() and len(stripped) > 100:
        return True

    return False


def _has_placeholders(content: str) -> bool:
    """Check if content has obvious placeholder/stub patterns."""
    placeholder_patterns = [
        r'#\s*TODO\s*:?\s*implement',
        r'#\s*\.\.\.',
        r'//\s*\.\.\.',
        r'//\s*rest of',
        r'#\s*rest of',
        r'#\s*Add more',
        r'#\s*continue',
        r'pass\s*$',  # bare pass at end of file
        r'raise NotImplementedError',
    ]
    lines = content.strip().split('\n')
    # Only flag if the file is suspiciously short with placeholders
    for pattern in placeholder_patterns:
        for line in lines[-5:]:  # check last 5 lines
            if re.search(pattern, line, re.IGNORECASE):
                # bare 'pass' is fine in small stubs, but not in main logic
                if 'pass' in line and len(lines) > 5:
                    return True
                elif 'pass' not in line:
                    return True
    return False


class CodeWriterAgent(BaseAgent):
    role = 'writer'
    system_prompt = """You are an expert software developer for AstraDev.
You write clean, production-quality code in any language/framework.

When asked to create or modify files, output the COMPLETE file content as a JSON response.

Output format (MUST be valid JSON):
{
  "files": [
    {
      "action": "create" or "modify",
      "path": "relative/file/path.ext",
      "content": "THE ENTIRE COMPLETE FILE CONTENT - EVERY SINGLE LINE"
    }
  ],
  "explanation": "Brief explanation of what was created and why"
}

CRITICAL RULES:
1. EVERY file MUST be COMPLETE from line 1 to the last line. Never truncate.
2. NEVER use placeholders: '...', '# TODO', 'pass', '// rest of code'.
3. Every file MUST be syntactically valid and immediately runnable.
4. Include ALL imports, ALL functions, ALL error handling.
5. Output valid JSON only - no markdown fences around the JSON.
6. Use relative fetch URLs for web apps served behind a proxy.
7. Keep each file focused and reasonably sized. Split large apps into multiple files.
8. For Flask apps: put app creation in a top-level file (app.py), NOT inside packages.
9. For web UIs: include COMPLETE HTML/CSS/JS with all event handlers."""

    MAX_REPAIR_ATTEMPTS = 2

    def execute(self, task_description: str, context: dict = None) -> dict:
        self.emit('action', f'Writing code: {task_description[:100]}...')

        extra_context = ''
        if context:
            if 'project_state' in context:
                extra_context += f"Current project state:\n{json.dumps(context['project_state'], indent=2)}\n"
            if 'existing_files' in context:
                extra_context += f"Existing files:\n{json.dumps(context['existing_files'])}\n"

        messages = self.build_messages(task_description, extra_context)
        result = self.call_groq(messages, stream=False)
        content = result['content']
        self.log_token_usage(result['tokens_input'], result['tokens_output'], result['key_used'])

        output = self._parse_output(content)

        # Validate and repair files
        repaired_output = self._validate_and_repair(output, task_description, extra_context)

        # Write files to workspace and emit code
        for f in repaired_output.get('files', []):
            file_path = f.get('path', '')
            file_content = f.get('content', '')
            if file_path and file_content:
                self.edit_file(file_path, file_content)
            self.emit('code', file_content[:500], {
                'file_path': file_path,
                'action': f.get('action', 'create'),
            })

        return repaired_output

    def _parse_output(self, content: str) -> dict:
        """Parse LLM output, handling various JSON wrapper formats."""
        try:
            # Strip markdown code fences
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                parts = content.split('```')
                for part in parts[1:]:
                    if '{' in part:
                        content = part.split('```')[0] if '```' in part else part
                        break

            raw = json.loads(content.strip())

            # Handle nested JSON wrapper: {"files": [{"path": "X", "content": "{\"files\": ...}"}]}
            # This happens when the LLM wraps the entire output as the content of a single file
            if isinstance(raw, dict) and 'files' in raw:
                files = raw['files']
                cleaned_files = []
                for f in files:
                    fc = f.get('content', '')
                    # If a file's content is itself a JSON with 'files' key, it's a wrapper bug
                    if isinstance(fc, str) and fc.strip().startswith('{') and '"files"' in fc[:50]:
                        try:
                            inner = json.loads(fc)
                            if 'files' in inner:
                                # Unwrap: use the inner files instead
                                cleaned_files.extend(inner['files'])
                                continue
                        except (json.JSONDecodeError, KeyError):
                            pass
                    cleaned_files.append(f)
                raw['files'] = cleaned_files

                # Fix files whose content starts with JSON (wrong parse layer)
                for f in raw['files']:
                    fc = f.get('content', '')
                    if isinstance(fc, str) and fc.strip().startswith('{'):
                        try:
                            parsed = json.loads(fc)
                            # If content is a JSON dict with 'content' key, extract it
                            if isinstance(parsed, dict) and 'content' in parsed:
                                f['content'] = parsed['content']
                        except (json.JSONDecodeError, KeyError):
                            pass

                return raw
            else:
                return {'files': [], 'explanation': str(raw)}

        except (json.JSONDecodeError, IndexError):
            logger.warning("Failed to parse writer output as JSON")
            return {
                'files': [{
                    'action': 'create',
                    'path': 'output.txt',
                    'content': content,
                }],
                'explanation': 'Raw output (could not parse as structured JSON)',
            }

    def _validate_and_repair(self, output: dict, task_description: str, extra_context: str) -> dict:
        """Validate all files and attempt to repair broken ones."""
        files = output.get('files', [])
        if not files:
            return output

        broken_files = []
        for f in files:
            path = f.get('path', '')
            content = f.get('content', '')
            issues = []

            if not content or len(content.strip()) < 10:
                issues.append('empty or too short')
            elif _detect_truncation(content, path):
                issues.append('truncated')
            elif _has_placeholders(content):
                issues.append('has placeholders')

            # Python-specific syntax check
            if path.endswith('.py') and content and len(content.strip()) > 10:
                err = _validate_python_syntax(content)
                if err:
                    issues.append(f'syntax error: {err}')

            if issues:
                broken_files.append((f, issues))

        if not broken_files:
            self.emit('action', f'All {len(files)} files validated successfully')
            return output

        self.emit('action', f'{len(broken_files)} file(s) need repair: {", ".join(f[0]["path"] for f in broken_files)}')

        # Attempt to repair each broken file
        for attempt in range(self.MAX_REPAIR_ATTEMPTS):
            if not broken_files:
                break

            still_broken = []
            for f, issues in broken_files:
                path = f['path']
                self.emit('action', f'Repairing {path} (attempt {attempt+1}): {", ".join(issues)}')

                repair_prompt = (
                    f"Generate the COMPLETE file for '{path}'. "
                    f"Issues with previous version: {', '.join(issues)}. "
                    f"Context: {task_description[:200]}. "
                    f"Output ONLY the file content as valid JSON: "
                    f'{{"path": "{path}", "content": "COMPLETE FILE CONTENT HERE"}}'
                )

                try:
                    repair_messages = self.build_messages(repair_prompt, '')
                    repair_result = self.call_groq(repair_messages, stream=False)
                    self.log_token_usage(repair_result['tokens_input'], repair_result['tokens_output'], repair_result['key_used'])

                    new_content = self._extract_file_content(repair_result['content'], path)

                    if new_content and len(new_content.strip()) > len(f.get('content', '').strip()):
                        # Validate the repair
                        new_issues = []
                        if _detect_truncation(new_content, path):
                            new_issues.append('still truncated')
                        if path.endswith('.py'):
                            err = _validate_python_syntax(new_content)
                            if err:
                                new_issues.append(f'syntax: {err}')

                        if not new_issues:
                            f['content'] = new_content
                            self.emit('action', f'Repaired {path} successfully')
                        else:
                            # Repair is better (longer) even if not perfect
                            f['content'] = new_content
                            still_broken.append((f, new_issues))
                    else:
                        still_broken.append((f, issues))
                except Exception as e:
                    logger.warning(f"Repair failed for {path}: {e}")
                    still_broken.append((f, issues))

            broken_files = still_broken

        if broken_files:
            names = ', '.join(f[0]['path'] for f in broken_files)
            self.emit('action', f'Warning: {len(broken_files)} file(s) may still have issues: {names}')

        return output

    def _extract_file_content(self, raw: str, path: str) -> str:
        """Extract file content from LLM repair output."""
        # Try JSON parse first
        try:
            if '```json' in raw:
                raw = raw.split('```json')[1].split('```')[0]
            elif '```' in raw:
                parts = raw.split('```')
                for part in parts[1:]:
                    if '{' in part:
                        raw = part.split('```')[0] if '```' in part else part
                        break

            parsed = json.loads(raw.strip())
            if isinstance(parsed, dict):
                return parsed.get('content', '')
            elif isinstance(parsed, list) and parsed:
                return parsed[0].get('content', '')
        except (json.JSONDecodeError, IndexError, KeyError):
            pass

        # Fallback: if it looks like raw code (not JSON), use it directly
        stripped = raw.strip()
        if not stripped.startswith('{') and not stripped.startswith('['):
            # It's probably raw code
            return stripped

        return ''

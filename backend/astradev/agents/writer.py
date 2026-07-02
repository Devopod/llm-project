import json
import logging
from .base import BaseAgent

logger = logging.getLogger('astradev.agents')


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
  "explanation": "Brief explanation of what was created and why",
  "next_steps": "What should be done next (optional)"
}

ABSOLUTE NON-NEGOTIABLE RULES:
1. EVERY file MUST contain the COMPLETE source code from line 1 to the LAST line.
2. NEVER abbreviate, truncate, or skip ANY section of code.
3. NEVER use placeholders like:
   - '...'
   - '// rest of code here'
   - '# TODO: implement'
   - 'pass'
   - '/* ... */'
   - '// ...'
   - 'etc.'
   - '# Add more as needed'
4. NEVER say "similar to above" or "repeat the pattern" — write out EVERY line explicitly.
5. Every file MUST be syntactically valid and immediately executable/runnable WITHOUT modification.
6. Include ALL necessary imports, dependencies, and boilerplate at the top.
7. Include proper error handling, edge cases, and input validation.
8. Include type annotations where applicable (TypeScript, Python type hints).
9. Follow language-specific best practices and conventions.
10. Use relative fetch URLs (not absolute) for web apps that may be served behind a proxy.
11. Output valid JSON only — no markdown, no code fences around the JSON.
12. File paths should be relative to project root.
13. If a file would be 500 lines, write all 500 lines — NEVER abbreviate.
14. For HTML/CSS: include COMPLETE styling, ALL elements, ALL event handlers.
15. For backends: include ALL routes, ALL models, ALL error responses.
16. The code MUST work when saved directly to disk and run — it is the FINAL product.

QUALITY STANDARDS:
- Professional UI with modern CSS (gradients, shadows, animations, responsive design)
- Proper folder structure (templates/, static/, src/, etc.)
- README.md with setup instructions
- requirements.txt or package.json with ALL dependencies
- Production-ready error handling (try/except, try/catch, HTTP error responses)
- Input validation and sanitization
- Clean variable/function naming"""

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

        try:
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                parts = content.split('```')
                for part in parts[1:]:
                    if '{' in part:
                        content = part.split('```')[0] if '```' in part else part
                        break

            output = json.loads(content.strip())
            if 'files' not in output:
                output = {'files': [], 'explanation': content}
        except (json.JSONDecodeError, IndexError):
            logger.warning("Failed to parse writer output as JSON")
            output = {
                'files': [{
                    'action': 'create',
                    'path': 'output.txt',
                    'content': result['content'],
                }],
                'explanation': 'Raw output (could not parse as structured JSON)',
            }

        # Validate: reject files with placeholder content and regenerate if needed
        placeholder_patterns = ['# TODO', '// TODO', '/* TODO', '...more', '// ...', '# ...', 'pass  #', '// rest of']
        for f in output.get('files', []):
            content = f.get('content', '')
            has_placeholder = any(p in content for p in placeholder_patterns)
            if has_placeholder and len(content) < 50:
                logger.warning(f"Placeholder detected in {f.get('path')}, content too short")
                f['content'] = f'# ERROR: Code generation incomplete for {f.get("path")}\n# Please regenerate this file\n'

        # Emit code for each file
        for f in output.get('files', []):
            self.emit('code', f.get('content', '')[:500], {
                'file_path': f.get('path', ''),
                'action': f.get('action', 'create'),
            })

        return output

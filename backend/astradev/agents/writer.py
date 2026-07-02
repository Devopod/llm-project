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
      "action": "create",
      "path": "relative/file/path.ext",
      "content": "full file content here"
    }
  ],
  "explanation": "Brief explanation of what was created and why",
  "next_steps": "What should be done next (optional)"
}

Rules:
- Write complete, runnable code — no placeholders or TODOs
- Include proper error handling
- Include type annotations where applicable
- Follow language-specific best practices (PEP 8, ESLint, etc.)
- Include all necessary imports
- Use existing project patterns if context is provided
- Output valid JSON only — no markdown, no code fences around the JSON itself
- File paths should be relative to project root"""

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

        # Emit code for each file
        for f in output.get('files', []):
            self.emit('code', f.get('content', '')[:500], {
                'file_path': f.get('path', ''),
                'action': f.get('action', 'create'),
            })

        return output

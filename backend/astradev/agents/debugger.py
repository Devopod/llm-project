import json
import logging
from .base import BaseAgent

logger = logging.getLogger('astradev.agents')


class DebugAgent(BaseAgent):
    role = 'debugger'
    system_prompt = """You are a debugging specialist for AstraDev.
You analyze errors and produce targeted fixes.

Given error messages, stack traces, or failed test output, produce fixes as JSON:
{
  "diagnosis": "Root cause analysis",
  "fixes": [
    {
      "file": "path/to/file",
      "action": "modify",
      "content": "full corrected file content",
      "explanation": "What was wrong and how this fixes it"
    }
  ],
  "verification": "How to verify the fix works"
}

Rules:
- Analyze the root cause, don't just patch symptoms
- Be precise — output complete corrected files
- Consider side effects of your fix
- If the test itself is wrong, say so and fix the test
- Always output valid JSON"""

    def execute(self, task_description: str, context: dict = None) -> dict:
        self.emit('fix', 'Analyzing error and applying fix...')

        extra_context = ''
        if context:
            if 'error' in context:
                extra_context += f"Error:\n{context['error'][:2000]}\n"
            if 'code' in context:
                extra_context += f"Relevant code:\n{context['code'][:2000]}\n"

        messages = self.build_messages(task_description, extra_context)
        result = self.call_groq(messages, stream=False)
        content = result['content']
        self.log_token_usage(result['tokens_input'], result['tokens_output'], result['key_used'])

        try:
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            output = json.loads(content.strip())
        except (json.JSONDecodeError, IndexError):
            output = {'diagnosis': content, 'fixes': [], 'verification': ''}

        # Apply fixes directly via edit_file
        files = []
        for fix in output.get('fixes', []):
            file_path = fix.get('file', '')
            file_content = fix.get('content', '')
            if file_path and file_content:
                self.edit_file(file_path, file_content)
                files.append({'path': file_path, 'content': file_content})

        self.emit('fix', f"Fix applied: {output.get('diagnosis', '')[:200]}")
        output['files'] = files
        return output

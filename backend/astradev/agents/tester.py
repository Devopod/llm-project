import json
import logging
from .base import BaseAgent

logger = logging.getLogger('astradev.agents')


class TestingAgent(BaseAgent):
    role = 'tester'
    system_prompt = """You are a testing engineer for AstraDev.
Write comprehensive tests for the specified code.

Output MUST be valid JSON:
{
  "test_files": [
    {
      "path": "tests/test_example.py",
      "content": "full test file content",
      "framework": "pytest"
    }
  ],
  "run_command": "pytest tests/ -v",
  "explanation": "What is being tested and why"
}

Rules:
- Use the appropriate testing framework for the language
- Include edge cases, error cases, and boundary conditions
- Write clear test names that describe what's being tested
- Include setup/teardown if needed
- Mock external dependencies
- Aim for at least 80% code coverage of the target code"""

    def execute(self, task_description: str, context: dict = None) -> dict:
        self.emit('action', 'Writing tests...')

        extra_context = ''
        if context and 'code' in context:
            extra_context = f"Code to test:\n{context['code'][:3000]}"

        messages = self.build_messages(task_description, extra_context)
        result = self.call_groq(messages, stream=False)
        content = result['content']
        self.log_token_usage(result['tokens_input'], result['tokens_output'], result['key_used'])

        try:
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            output = json.loads(content.strip())
        except (json.JSONDecodeError, IndexError):
            output = {'test_files': [], 'run_command': '', 'explanation': content}

        self.emit('success', f"Tests written: {len(output.get('test_files', []))} files")
        return output

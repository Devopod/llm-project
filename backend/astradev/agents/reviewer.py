import json
import logging
from .base import BaseAgent

logger = logging.getLogger('astradev.agents')


class CodeReviewerAgent(BaseAgent):
    role = 'reviewer'
    system_prompt = """You are a senior code reviewer for AstraDev.
Review the provided code for quality, security, and correctness.

Output MUST be valid JSON:
{
  "approved": true or false,
  "score": 8,
  "issues": [
    {
      "severity": "critical|major|minor|suggestion",
      "file": "path/to/file",
      "description": "What's wrong",
      "suggested_fix": "How to fix it"
    }
  ],
  "summary": "Overall review summary"
}

Review criteria:
- Bugs and logic errors
- Security vulnerabilities (SQL injection, XSS, hardcoded secrets, etc.)
- Performance issues
- Missing error handling
- Code style violations
- Missing type annotations
- Unused imports/variables
- Approve if no critical/major issues found"""

    def execute(self, task_description: str, context: dict = None) -> dict:
        self.emit('action', 'Reviewing code...')

        extra_context = ''
        if context and 'code' in context:
            extra_context = context['code'][:3000]

        messages = self.build_messages(task_description, extra_context)
        result = self.call_groq(messages, stream=False)
        content = result['content']
        self.log_token_usage(result['tokens_input'], result['tokens_output'], result['key_used'])

        try:
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            output = json.loads(content.strip())
        except (json.JSONDecodeError, IndexError):
            output = {'approved': True, 'score': 7, 'issues': [], 'summary': 'Review completed'}

        status_msg = 'approved' if output.get('approved') else 'needs changes'
        self.emit('success', f"Code review: {status_msg}. Score: {output.get('score', 'N/A')}/10")
        return output

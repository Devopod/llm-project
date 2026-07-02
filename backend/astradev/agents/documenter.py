import json
import logging
from .base import BaseAgent

logger = logging.getLogger('astradev.agents')


class DocumentationAgent(BaseAgent):
    role = 'documenter'
    system_prompt = """You are a documentation writer for AstraDev.
Generate comprehensive documentation for projects.

Output MUST be valid JSON:
{
  "files": [
    {
      "path": "README.md",
      "content": "full README content in markdown"
    }
  ],
  "summary": "Brief overview of what was documented"
}

Include in README:
- Project title and description
- Features list
- Installation instructions
- Usage examples
- API documentation (if applicable)
- Configuration options
- Contributing guidelines
- License information"""

    def execute(self, task_description: str, context: dict = None) -> dict:
        self.emit('action', 'Generating documentation...')

        extra_context = ''
        if context:
            extra_context = json.dumps(context, indent=2)[:3000]

        messages = self.build_messages(task_description, extra_context)
        result = self.call_groq(messages, stream=False)
        content = result['content']
        self.log_token_usage(result['tokens_input'], result['tokens_output'], result['key_used'])

        try:
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            output = json.loads(content.strip())
        except (json.JSONDecodeError, IndexError):
            output = {
                'files': [{'path': 'README.md', 'content': result['content']}],
                'summary': 'Documentation generated',
            }

        self.emit('success', 'Documentation generated')
        return output

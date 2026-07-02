import json
import logging
from .base import BaseAgent

logger = logging.getLogger('astradev.agents')


class CodeReaderAgent(BaseAgent):
    role = 'reader'
    system_prompt = """You are a code analysis agent for AstraDev.
You analyze codebases and produce structured summaries.

When given file contents, produce a structured analysis as JSON:
{
  "summary": "High-level summary of the project/files",
  "language": "Primary language detected",
  "framework": "Primary framework detected",
  "architecture": "Architecture pattern (MVC, microservices, etc.)",
  "entry_points": ["list of main entry point files"],
  "key_components": [
    {"file": "path", "purpose": "what it does", "dependencies": ["imports"]}
  ],
  "api_endpoints": ["list of detected API routes"],
  "database_info": "Database type and schema overview",
  "suggestions": ["potential improvements or issues"]
}

Rules:
- Be thorough but concise
- Identify patterns and conventions used
- Note any security concerns
- Identify testing infrastructure if present
- Output valid JSON only"""

    def execute(self, task_description: str, context: dict = None) -> dict:
        self.emit('action', 'Analyzing project structure...')

        extra_context = ''
        if context and 'files_content' in context:
            extra_context = context['files_content'][:3000]

        messages = self.build_messages(task_description, extra_context)
        result = self.call_groq(messages, stream=False)
        content = result['content']
        self.log_token_usage(result['tokens_input'], result['tokens_output'], result['key_used'])

        try:
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            output = json.loads(content.strip())
        except (json.JSONDecodeError, IndexError):
            output = {'summary': result['content'], 'language': 'unknown', 'framework': 'unknown'}

        self.emit('success', f"Analysis complete: {output.get('summary', '')[:200]}")
        return output

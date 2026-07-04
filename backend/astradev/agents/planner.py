import json
import logging
from .base import BaseAgent

logger = logging.getLogger('astradev.agents')


class PlannerAgent(BaseAgent):
    role = 'planner'
    system_prompt = """You are a software architecture planning agent for AstraDev.
Given a user request, produce a detailed development plan as a JSON array of tasks.

Output MUST be valid JSON with this exact structure:
{
  "tasks": [
    {
      "id": "task_1",
      "title": "Short task title",
      "description": "Detailed description of what to do",
      "type": "write_code",
      "dependencies": [],
      "estimated_complexity": "low"
    }
  ]
}

Task types: read_code, write_code, test, deploy, document
Complexity: low, medium, high

Rules:
- Break work into small, independently verifiable tasks
- Each task should be completable in a single agent call
- Consider dependencies between tasks carefully
- Include testing tasks after major code writing tasks
- Include a deployment task at the end if it's a web application
- Keep task count between 3-15 for manageable execution
- Always start with project setup/scaffolding
- End with documentation and deployment

IMPORTANT — Working with EXISTING projects:
- If context mentions "existing_project": true, the workspace already has files
- DO NOT recreate files that already exist — only modify or add what's needed
- Use action "edit" for modifying existing files, "create" only for NEW files
- Read existing files before planning changes
- Keep the existing project structure intact
- Only touch files relevant to the user's request
- DO NOT generate setup/scaffolding tasks if the project is already set up"""

    def execute(self, prompt: str, context: dict = None) -> dict:
        self.emit('thinking', 'Creating development plan...')

        extra_context = ''
        if context:
            extra_context = json.dumps(context, indent=2)

        messages = self.build_messages(
            f"Create a development plan for: {prompt}",
            extra_context
        )

        result = self.call_groq(messages, stream=False)
        content = result['content']
        self.log_token_usage(result['tokens_input'], result['tokens_output'], result['key_used'])

        # Parse the JSON response
        try:
            # Try to extract JSON from the response
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]

            plan = json.loads(content.strip())
            if 'tasks' not in plan:
                plan = {'tasks': plan if isinstance(plan, list) else []}
        except (json.JSONDecodeError, IndexError):
            logger.warning("Failed to parse planner output, creating default plan")
            plan = self._default_plan(prompt)

        self.emit('plan', json.dumps(plan, indent=2), {'task_count': len(plan.get('tasks', []))})
        return plan

    def _default_plan(self, prompt: str) -> dict:
        return {
            'tasks': [
                {
                    'id': 'task_1',
                    'title': 'Build complete application',
                    'description': (
                        f'Build a COMPLETE, production-ready application for: {prompt}. '
                        f'Generate ALL files needed: main application file (app.py), '
                        f'HTML templates with full styling and interactivity, '
                        f'requirements.txt, configuration files, and any helper modules. '
                        f'The app must be immediately runnable with all routes, '
                        f'error handling, and a polished UI. '
                        f'Put files in the project root (not in a subdirectory). '
                        f'For Flask apps: include templates/ folder with HTML files, '
                        f'use relative fetch URLs, and include proper CSS styling.'
                    ),
                    'type': 'write_code',
                    'dependencies': [],
                    'estimated_complexity': 'high',
                },
                {
                    'id': 'task_2',
                    'title': 'Generate documentation',
                    'description': f'Create a comprehensive README.md for: {prompt}',
                    'type': 'document',
                    'dependencies': ['task_1'],
                    'estimated_complexity': 'low',
                },
            ]
        }

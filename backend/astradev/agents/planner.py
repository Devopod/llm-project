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
- End with documentation and deployment"""

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
                    'title': 'Set up project structure',
                    'description': f'Create the initial project structure for: {prompt}',
                    'type': 'write_code',
                    'dependencies': [],
                    'estimated_complexity': 'medium',
                },
                {
                    'id': 'task_2',
                    'title': 'Implement core functionality',
                    'description': f'Implement the main features requested: {prompt}',
                    'type': 'write_code',
                    'dependencies': ['task_1'],
                    'estimated_complexity': 'high',
                },
                {
                    'id': 'task_3',
                    'title': 'Add configuration and dependencies',
                    'description': 'Add package manifests, config files, and dependency declarations',
                    'type': 'write_code',
                    'dependencies': ['task_2'],
                    'estimated_complexity': 'low',
                },
                {
                    'id': 'task_4',
                    'title': 'Write tests',
                    'description': 'Write unit and integration tests for the implemented code',
                    'type': 'test',
                    'dependencies': ['task_3'],
                    'estimated_complexity': 'medium',
                },
                {
                    'id': 'task_5',
                    'title': 'Generate documentation',
                    'description': 'Create README and API documentation',
                    'type': 'document',
                    'dependencies': ['task_4'],
                    'estimated_complexity': 'low',
                },
            ]
        }

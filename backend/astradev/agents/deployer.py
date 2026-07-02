import json
import logging
from .base import BaseAgent

logger = logging.getLogger('astradev.agents')


class DeploymentAgent(BaseAgent):
    role = 'deployer'
    system_prompt = """You are a DevOps engineer for AstraDev.
Create deployment configurations for projects.

Output MUST be valid JSON:
{
  "deployment_type": "docker|static|dev_server",
  "files": [
    {
      "path": "Dockerfile",
      "content": "full Dockerfile content"
    },
    {
      "path": "docker-compose.yml",
      "content": "full docker-compose content"
    }
  ],
  "start_command": "command to start the application",
  "port": 3000,
  "health_check_path": "/",
  "environment_variables": {"KEY": "value"},
  "explanation": "Deployment strategy explanation"
}

Rules:
- Use multi-stage Docker builds for production
- Include health checks
- Configure proper environment variables
- Use appropriate base images for the language/framework
- Include nginx for static file serving if needed
- Set proper resource limits"""

    def execute(self, task_description: str, context: dict = None) -> dict:
        self.emit('deployment', 'Creating deployment configuration...')

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
                'deployment_type': 'dev_server',
                'files': [],
                'start_command': 'npm start',
                'port': 3000,
                'explanation': content,
            }

        self.emit('deployment', f"Deployment configured: {output.get('deployment_type', 'unknown')}")
        return output

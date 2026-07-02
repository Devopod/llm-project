import json
import logging

from .base import BaseAgent

logger = logging.getLogger('astradev.agents')


class RefactorAgent(BaseAgent):
    role = 'refactor'
    system_prompt = """You are the Refactoring Agent for AstraDev (OpenHands-inspired).
You improve existing code quality through:
- Extracting repeated logic into functions
- Improving naming and readability
- Optimizing performance
- Reducing complexity
- Applying design patterns
- DRY principle enforcement
- Type safety improvements

Output refactored code as JSON: {"files": [{"path": "...", "content": "...", "changes": "..."}]}

IMPORTANT: Always output COMPLETE, FULL file content. Never use placeholders like '...' or '// rest of code'.
Every file must be syntactically valid and immediately runnable."""

    def execute(self, task_description: str, context: dict = None) -> dict:
        self.emit('action', f'Refactoring: {task_description[:100]}')

        context = context or {}
        code = context.get('code', '')

        messages = self.build_messages(
            f"Refactor the following code. Task: {task_description}\n\nCode:\n{code[:600]}",
            "Return complete refactored files as JSON."
        )

        result = self.call_groq(messages)
        content = result.get('content', '')
        parsed = self._parse_result(content)

        self.emit('output', f"Refactoring complete: {len(parsed.get('files', []))} files improved")
        return parsed

    def _parse_result(self, content: str) -> dict:
        try:
            if '{' in content:
                start = content.index('{')
                end = content.rindex('}') + 1
                return json.loads(content[start:end])
        except (json.JSONDecodeError, ValueError):
            pass
        return {'files': [], 'changes': content[:500]}

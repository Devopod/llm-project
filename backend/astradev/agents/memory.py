import json
import logging
from datetime import datetime

from .base import BaseAgent

logger = logging.getLogger('astradev.agents')


class MemoryAgent(BaseAgent):
    role = 'memory'
    system_prompt = """You are the Memory Agent for AstraDev (OpenHands-inspired).
You manage project context and knowledge:
- Track decisions made during development
- Remember code patterns used
- Maintain dependency information
- Store architecture decisions
- Track error patterns and solutions applied
- Provide context to other agents for continuity"""

    def __init__(self, project):
        super().__init__(project)
        self._memory_store = {}

    def execute(self, task_description: str, context: dict = None) -> dict:
        context = context or {}
        action = context.get('action', 'recall')

        if action == 'store':
            return self._store_memory(context)
        elif action == 'recall':
            return self._recall(task_description)
        elif action == 'summarize':
            return self._summarize()
        return {'status': 'unknown_action'}

    def store(self, key: str, value: str, category: str = 'general'):
        self._memory_store[key] = {
            'value': value,
            'category': category,
            'timestamp': datetime.utcnow().isoformat(),
        }
        # Also persist to project state
        memories = self.project.project_state.get('memories', {})
        memories[key] = {'value': value[:500], 'category': category}
        self.project.project_state['memories'] = memories
        self.project.save(update_fields=['project_state'])

    def recall(self, query: str) -> list:
        results = []
        memories = self.project.project_state.get('memories', {})
        query_lower = query.lower()
        for key, data in memories.items():
            if query_lower in key.lower() or query_lower in data.get('value', '').lower():
                results.append({'key': key, **data})
        return results

    def _store_memory(self, context: dict) -> dict:
        key = context.get('key', 'unknown')
        value = context.get('value', '')
        category = context.get('category', 'general')
        self.store(key, value, category)
        return {'status': 'stored', 'key': key}

    def _recall(self, query: str) -> dict:
        results = self.recall(query)
        return {'memories': results, 'count': len(results)}

    def _summarize(self) -> dict:
        memories = self.project.project_state.get('memories', {})
        categories = {}
        for key, data in memories.items():
            cat = data.get('category', 'general')
            categories.setdefault(cat, []).append(key)
        return {'summary': categories, 'total': len(memories)}

import json
import logging
import urllib.request
import urllib.error

from .base import BaseAgent

logger = logging.getLogger('astradev.agents')


class BrowserAgent(BaseAgent):
    role = 'browser'
    system_prompt = """You are the Browser Agent for AstraDev (OpenHands-inspired).
You navigate web resources to gather information for implementation:
- Read API documentation
- Check library usage examples
- Verify framework compatibility
- Research best practices
- Fetch package information from registries

Output research findings as structured JSON:
{"research": {"topic": "...", "findings": ["..."], "recommendations": ["..."], "urls": ["..."]}}"""

    def execute(self, task_description: str, context: dict = None) -> dict:
        self.emit('action', f'Browser: Researching - {task_description[:100]}')

        context = context or {}
        messages = self.build_messages(
            f"Research the following for implementation guidance:\n{task_description}\n\n"
            "Provide practical, actionable recommendations based on best practices.",
            json.dumps(context)[:300] if context else ''
        )

        result = self.call_groq(messages)
        content = result.get('content', '')
        research = self._parse_research(content)

        # Try to fetch relevant package info
        keywords = self._extract_keywords(task_description)
        for kw in keywords[:2]:
            pkg_info = self._check_npm_package(kw)
            if pkg_info:
                research.setdefault('packages', []).append(pkg_info)

        self.emit('output', f"Research complete: {len(research.get('findings', []))} findings")
        return research

    def _parse_research(self, content: str) -> dict:
        try:
            if '{' in content:
                start = content.index('{')
                end = content.rindex('}') + 1
                return json.loads(content[start:end])
        except (json.JSONDecodeError, ValueError):
            pass
        return {'research': {'topic': 'general', 'findings': [content[:500]], 'recommendations': []}}

    def _extract_keywords(self, text: str) -> list:
        keywords = []
        tech_terms = ['react', 'next', 'express', 'django', 'flask', 'fastapi',
                      'vue', 'angular', 'svelte', 'tailwind', 'prisma', 'drizzle']
        for term in tech_terms:
            if term in text.lower():
                keywords.append(term)
        return keywords

    def _check_npm_package(self, package_name: str) -> dict:
        try:
            url = f"https://registry.npmjs.org/{package_name}/latest"
            req = urllib.request.Request(url, headers={'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read())
                return {
                    'name': data.get('name'),
                    'version': data.get('version'),
                    'description': data.get('description', '')[:100],
                }
        except (urllib.error.URLError, json.JSONDecodeError, Exception):
            return None

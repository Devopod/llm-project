import json
import logging
from datetime import datetime
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from astradev.projects.models import Project, Message, TokenUsage
from .groq_client import groq_client

logger = logging.getLogger('astradev.agents')


class BaseAgent:
    role = 'base'
    system_prompt = "You are a helpful AI assistant."

    def __init__(self, project: Project):
        self.project = project
        self.channel_layer = get_channel_layer()

    def execute(self, task_description: str, context: dict = None) -> dict:
        raise NotImplementedError

    def emit(self, message_type: str, content: str, metadata: dict = None):
        msg = Message.objects.create(
            project=self.project,
            role=self.role,
            content=content,
            message_type=message_type,
            metadata=metadata or {},
        )
        data = {
            'type': message_type,
            'content': content,
            'metadata': metadata,
            'timestamp': datetime.utcnow().isoformat(),
            'agent': self.role,
            'message_id': str(msg.id),
        }
        try:
            async_to_sync(self.channel_layer.group_send)(
                f"project_{self.project.id}",
                {'type': 'agent_message', 'data': data}
            )
        except Exception as e:
            logger.debug(f"WebSocket emit failed (no listeners?): {e}")
        return msg

    def call_groq(self, messages: list, stream: bool = False) -> dict:
        if stream:
            full_content = ''
            result = {}
            for chunk in groq_client.call(messages, stream=True):
                if chunk['type'] == 'chunk':
                    full_content += chunk['content']
                    self.emit('thinking', chunk['content'])
                elif chunk['type'] == 'done':
                    result = chunk
            return {
                'content': full_content,
                'tokens_input': result.get('tokens_input', 0),
                'tokens_output': result.get('tokens_output', 0),
                'key_used': result.get('key_used', ''),
            }
        else:
            result = groq_client.call(messages, stream=False)
            return result

    def build_messages(self, task: str, extra_context: str = '') -> list:
        messages = [{'role': 'system', 'content': self.system_prompt[:3000]}]
        if extra_context:
            messages.append({'role': 'user', 'content': f"Context:\n{extra_context[:2000]}"})
            messages.append({'role': 'assistant', 'content': 'Understood. I have the context.'})
        messages.append({'role': 'user', 'content': task[:2000]})
        return messages

    def log_token_usage(self, tokens_input, tokens_output, key_used):
        TokenUsage.objects.create(
            api_key_label=key_used,
            tokens_used=tokens_input + tokens_output,
            request_type=self.role,
            project=self.project,
        )
        self.project.total_tokens_used += tokens_input + tokens_output
        self.project.save(update_fields=['total_tokens_used'])

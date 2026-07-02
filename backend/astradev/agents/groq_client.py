import time
import json
import logging
import redis
from groq import Groq
from django.conf import settings

logger = logging.getLogger('astradev.agents')

_redis = redis.Redis.from_url(settings.REDIS_URL if hasattr(settings, 'REDIS_URL') else 'redis://localhost:6379/0')

KEYS = [
    ('key_1', settings.GROQ_API_KEY_1),
    ('key_2', settings.GROQ_API_KEY_2),
]

TOKEN_LIMIT_PER_WINDOW = 7500
WINDOW_SECONDS = 60


class GroqClient:
    def __init__(self):
        self.model = settings.GROQ_MODEL
        self.disabled_keys = set()

    def _get_token_usage(self, key_label):
        now = time.time()
        redis_key = f"token_usage:{key_label}"
        try:
            _redis.zremrangebyscore(redis_key, '-inf', now - WINDOW_SECONDS)
            total = 0
            entries = _redis.zrangebyscore(redis_key, now - WINDOW_SECONDS, '+inf', withscores=True)
            for value, score in entries:
                total += int(value)
            return total
        except Exception:
            return 0

    def _record_token_usage(self, key_label, tokens):
        now = time.time()
        redis_key = f"token_usage:{key_label}"
        try:
            _redis.zadd(redis_key, {f"{tokens}:{now}": now})
            _redis.expire(redis_key, WINDOW_SECONDS * 2)
        except Exception:
            pass

    def get_available_key(self):
        for key_label, key_value in KEYS:
            if key_label in self.disabled_keys:
                continue
            usage = self._get_token_usage(key_label)
            if usage < TOKEN_LIMIT_PER_WINDOW:
                return key_label, key_value
        return None, None

    def call(self, messages, stream=True, max_retries=5):
        for attempt in range(max_retries):
            key_label, key_value = self.get_available_key()
            if not key_value:
                wait_time = min(2 ** attempt, 30)
                logger.warning(f"All keys exhausted, waiting {wait_time}s")
                time.sleep(wait_time)
                continue

            try:
                client = Groq(api_key=key_value)
                if stream:
                    return self._stream_call(client, messages, key_label)
                else:
                    return self._sync_call(client, messages, key_label)
            except Exception as e:
                error_str = str(e)
                if '401' in error_str:
                    logger.error(f"Key {key_label} is invalid, disabling")
                    self.disabled_keys.add(key_label)
                elif '429' in error_str:
                    logger.warning(f"Rate limited on {key_label}, trying next key")
                    self._record_token_usage(key_label, TOKEN_LIMIT_PER_WINDOW)
                else:
                    logger.error(f"Groq API error on attempt {attempt+1}: {error_str}")
                    time.sleep(min(2 ** attempt, 16))

        raise Exception("All Groq API retries exhausted")

    def _sync_call(self, client, messages, key_label):
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=1,
            max_tokens=2048,
            top_p=1,
            stream=False,
            stop=None,
        )
        content = response.choices[0].message.content or ''
        tokens_in = response.usage.prompt_tokens if response.usage else 0
        tokens_out = response.usage.completion_tokens if response.usage else 0
        self._record_token_usage(key_label, tokens_in + tokens_out)
        return {
            'content': content,
            'tokens_input': tokens_in,
            'tokens_output': tokens_out,
            'key_used': key_label,
        }

    def _stream_call(self, client, messages, key_label):
        stream = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=1,
            max_tokens=2048,
            top_p=1,
            stream=True,
            stop=None,
        )
        full_content = ''
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                delta = chunk.choices[0].delta.content
                full_content += delta
                yield {'type': 'chunk', 'content': delta}

        estimated_tokens = len(full_content) // 4 + sum(len(m.get('content', '')) for m in messages) // 4
        self._record_token_usage(key_label, estimated_tokens)

        yield {
            'type': 'done',
            'content': full_content,
            'tokens_input': sum(len(m.get('content', '')) for m in messages) // 4,
            'tokens_output': len(full_content) // 4,
            'key_used': key_label,
        }


groq_client = GroqClient()

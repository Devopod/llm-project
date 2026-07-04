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


class GroqClient:
    def __init__(self):
        self.model = settings.GROQ_MODEL

    def _is_key_disabled(self, key_label):
        try:
            disabled_until = _redis.get(f"groq_disabled:{key_label}")
            if disabled_until:
                return float(disabled_until) > time.time()
        except Exception:
            pass
        return False

    def _disable_key(self, key_label, seconds=300):
        try:
            _redis.setex(f"groq_disabled:{key_label}", seconds, str(time.time() + seconds))
        except Exception:
            pass

    def get_available_key(self):
        for key_label, key_value in KEYS:
            if not self._is_key_disabled(key_label):
                return key_label, key_value
        return None, None

    def call(self, messages, stream=False, max_retries=10):
        last_error = None
        for attempt in range(max_retries):
            key_label, key_value = self.get_available_key()
            if not key_value:
                wait_time = min(15 + attempt * 5, 60)
                logger.warning(f"All keys disabled, waiting {wait_time}s (attempt {attempt+1})")
                time.sleep(wait_time)
                continue

            try:
                client = Groq(api_key=key_value)
                if stream:
                    return self._stream_call(client, messages, key_label)
                else:
                    return self._sync_call(client, messages, key_label)
            except Exception as e:
                last_error = e
                error_str = str(e)
                if '401' in error_str or 'invalid' in error_str.lower():
                    logger.error(f"Key {key_label} is invalid, disabling permanently")
                    self._disable_key(key_label, 86400)
                elif '429' in error_str:
                    if 'tokens per day' in error_str or 'TPD' in error_str:
                        logger.warning(f"Key {key_label} hit daily limit, disabling for 1 hour")
                        self._disable_key(key_label, 3600)
                    else:
                        logger.warning(f"Key {key_label} rate limited, disabling for 60s")
                        self._disable_key(key_label, 60)
                    time.sleep(2)
                else:
                    logger.error(f"Groq API error on attempt {attempt+1}: {error_str[:200]}")
                    time.sleep(min(3 * (attempt + 1), 15))

        raise Exception(f"All Groq API retries exhausted: {last_error}")

    def _sync_call(self, client, messages, key_label):
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            max_tokens=8192,
            top_p=1,
            stream=False,
            stop=None,
        )
        content = response.choices[0].message.content or ''
        tokens_in = response.usage.prompt_tokens if response.usage else 0
        tokens_out = response.usage.completion_tokens if response.usage else 0
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
            temperature=0.7,
            max_tokens=8192,
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

        yield {
            'type': 'done',
            'content': full_content,
            'tokens_input': sum(len(m.get('content', '')) for m in messages) // 4,
            'tokens_output': len(full_content) // 4,
            'key_used': key_label,
        }


groq_client = GroqClient()

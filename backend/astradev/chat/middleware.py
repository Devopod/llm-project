from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from urllib.parse import parse_qs

from astradev.accounts.authentication import decode_token
from astradev.accounts.models import User


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query_string = scope.get('query_string', b'').decode()
        params = parse_qs(query_string)
        token = params.get('token', [None])[0]

        if token:
            try:
                payload = decode_token(token)
                user = await self._get_user(payload['user_id'])
                scope['user'] = user
            except Exception:
                scope['user'] = None
        else:
            scope['user'] = None

        return await super().__call__(scope, receive, send)

    @database_sync_to_async
    def _get_user(self, user_id):
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None

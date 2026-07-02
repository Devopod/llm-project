import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'astradev.settings')
django.setup()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application

from astradev.chat.routing import websocket_urlpatterns
from astradev.chat.middleware import JWTAuthMiddleware

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': JWTAuthMiddleware(
        URLRouter(websocket_urlpatterns)
    ),
})

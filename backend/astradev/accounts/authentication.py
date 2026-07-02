import jwt
import time
from django.conf import settings
from rest_framework import authentication, exceptions
from .models import User


def generate_access_token(user):
    payload = {
        'user_id': str(user.id),
        'email': user.email,
        'exp': int(time.time()) + settings.JWT_ACCESS_TOKEN_LIFETIME,
        'iat': int(time.time()),
        'type': 'access',
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


def generate_refresh_token(user):
    payload = {
        'user_id': str(user.id),
        'exp': int(time.time()) + settings.JWT_REFRESH_TOKEN_LIFETIME,
        'iat': int(time.time()),
        'type': 'refresh',
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


def decode_token(token):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        raise exceptions.AuthenticationFailed('Token expired')
    except jwt.InvalidTokenError:
        raise exceptions.AuthenticationFailed('Invalid token')


class JWTAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return None

        try:
            prefix, token = auth_header.split(' ')
            if prefix.lower() != 'bearer':
                return None
        except ValueError:
            return None

        payload = decode_token(token)
        if payload.get('type') != 'access':
            raise exceptions.AuthenticationFailed('Invalid token type')

        try:
            user = User.objects.get(id=payload['user_id'])
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed('User not found')

        if not user.is_active:
            raise exceptions.AuthenticationFailed('User inactive')

        return (user, token)

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import User
from .serializers import SignupSerializer, LoginSerializer, UserProfileSerializer
from .authentication import generate_access_token, generate_refresh_token, decode_token


@api_view(['POST'])
@permission_classes([AllowAny])
def signup(request):
    serializer = SignupSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.create(serializer.validated_data)
    user.is_verified = True  # Auto-verify for dev
    user.save()
    return Response({
        'user': UserProfileSerializer(user).data,
        'access_token': generate_access_token(user),
        'refresh_token': generate_refresh_token(user),
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data['email']
    password = serializer.validated_data['password']

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({'error': {'code': 'INVALID_CREDENTIALS', 'message': 'Invalid email or password'}},
                        status=status.HTTP_401_UNAUTHORIZED)

    if not user.check_password(password):
        return Response({'error': {'code': 'INVALID_CREDENTIALS', 'message': 'Invalid email or password'}},
                        status=status.HTTP_401_UNAUTHORIZED)

    user.last_login = timezone.now()
    user.save(update_fields=['last_login'])

    return Response({
        'user': UserProfileSerializer(user).data,
        'access_token': generate_access_token(user),
        'refresh_token': generate_refresh_token(user),
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def refresh_token(request):
    token = request.data.get('refresh_token')
    if not token:
        return Response({'error': {'code': 'MISSING_TOKEN', 'message': 'Refresh token required'}},
                        status=status.HTTP_400_BAD_REQUEST)

    payload = decode_token(token)
    if payload.get('type') != 'refresh':
        return Response({'error': {'code': 'INVALID_TOKEN', 'message': 'Invalid refresh token'}},
                        status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(id=payload['user_id'])
    except User.DoesNotExist:
        return Response({'error': {'code': 'USER_NOT_FOUND', 'message': 'User not found'}},
                        status=status.HTTP_404_NOT_FOUND)

    return Response({
        'access_token': generate_access_token(user),
        'refresh_token': generate_refresh_token(user),
    })


@api_view(['POST'])
def logout(request):
    return Response({'message': 'Logged out successfully'})


@api_view(['GET', 'PUT'])
def profile(request):
    if request.method == 'GET':
        return Response(UserProfileSerializer(request.user).data)
    serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(['GET'])
def user_stats(request):
    from astradev.projects.models import Project
    projects = Project.objects.filter(user=request.user)
    total_tokens = sum(p.total_tokens_used for p in projects)
    return Response({
        'total_projects': projects.count(),
        'total_tokens_used': total_tokens,
        'completed_projects': projects.filter(status='completed').count(),
    })

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import User, Payment
from .serializers import SignupSerializer, LoginSerializer, UserProfileSerializer
from .authentication import generate_access_token, generate_refresh_token, decode_token


@api_view(['POST'])
@permission_classes([AllowAny])
def signup(request):
    serializer = SignupSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.create(serializer.validated_data)
    user.is_verified = True
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


@api_view(['PUT'])
def change_password(request):
    user = request.user
    current_password = request.data.get('current_password')
    new_password = request.data.get('new_password')
    if not current_password or not new_password:
        return Response({'error': 'Both current_password and new_password required'}, status=400)
    if not user.check_password(current_password):
        return Response({'error': 'Current password is incorrect'}, status=400)
    if len(new_password) < 8:
        return Response({'error': 'New password must be at least 8 characters'}, status=400)
    user.set_password(new_password)
    user.save()
    return Response({'message': 'Password changed successfully'})


@api_view(['GET'])
def usage_stats(request):
    user = request.user
    user.check_and_reset_usage()
    from astradev.projects.models import Project
    projects = Project.objects.filter(user=user)
    return Response({
        'plan': user.plan,
        'plan_expires_at': user.plan_expires_at,
        'messages_used_today': user.messages_used_today,
        'message_limit': user.message_limit,
        'apk_builds_today': user.apk_builds_today,
        'apk_limit': user.apk_limit,
        'total_messages_sent': user.total_messages_sent,
        'total_projects_created': user.total_projects_created,
        'total_projects': projects.count(),
        'completed_projects': projects.filter(status='completed').count(),
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def plans_info(request):
    return Response({
        'plans': [
            {
                'id': 'free',
                'name': 'Free',
                'price_usd': 0,
                'price_bdt': 0,
                'features': [
                    '20 messages per day',
                    '3 APK builds per day',
                    'Basic agent support',
                    'Community support',
                ],
            },
            {
                'id': 'pro',
                'name': 'Pro',
                'price_usd': 8,
                'price_bdt': 976,
                'features': [
                    '500 messages per day',
                    '50 APK builds per day',
                    'All agents unlocked',
                    'Priority support',
                    'Advanced RAG',
                    'Custom deployments',
                ],
            },
            {
                'id': 'plus',
                'name': 'Plus',
                'price_usd': 20,
                'price_bdt': 2440,
                'features': [
                    'Unlimited messages',
                    'Unlimited APK builds',
                    'All agents unlocked',
                    'Priority support',
                    'Advanced RAG',
                    'Custom deployments',
                    'Dedicated workspace',
                    'API access',
                ],
            },
        ],
        'payment_info': {
            'method': 'bKash',
            'number': '01849691859',
            'rate': '1 USD = 122 BDT',
        },
    })


@api_view(['POST'])
def submit_payment(request):
    user = request.user
    plan = request.data.get('plan')
    transaction_id = request.data.get('transaction_id')
    sender_number = request.data.get('sender_number')

    if plan not in ['pro', 'plus']:
        return Response({'error': 'Invalid plan'}, status=400)
    if not transaction_id or not sender_number:
        return Response({'error': 'Transaction ID and sender number required'}, status=400)

    prices = {'pro': 8, 'plus': 20}
    amount_usd = prices[plan]
    amount_bdt = amount_usd * 122

    payment = Payment.objects.create(
        user=user,
        plan=plan,
        amount_usd=amount_usd,
        amount_bdt=amount_bdt,
        bkash_transaction_id=transaction_id,
        bkash_sender_number=sender_number,
    )

    return Response({
        'message': 'Payment submitted. Awaiting admin verification.',
        'payment_id': str(payment.id),
        'status': payment.status,
    })


@api_view(['GET'])
def payment_history(request):
    payments = Payment.objects.filter(user=request.user)
    data = [{
        'id': str(p.id),
        'plan': p.plan,
        'amount_usd': float(p.amount_usd),
        'amount_bdt': float(p.amount_bdt),
        'transaction_id': p.bkash_transaction_id,
        'status': p.status,
        'created_at': p.created_at.isoformat(),
        'verified_at': p.verified_at.isoformat() if p.verified_at else None,
    } for p in payments]
    return Response(data)


# ===== ADMIN ENDPOINTS =====

def _check_admin(request):
    """Check if request user is admin (staff)"""
    if not request.user.is_staff:
        return Response({'error': 'Admin access required'}, status=403)
    return None


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_login(request):
    username = request.data.get('username')
    password = request.data.get('password')

    if username == 'Admin123' and password == 'Admin123':
        admin_user, created = User.objects.get_or_create(
            email='admin@astradev.io',
            defaults={
                'display_name': 'Admin',
                'is_staff': True,
                'is_superuser': True,
                'is_verified': True,
            }
        )
        if created:
            admin_user.set_password('Admin123')
            admin_user.save()

        return Response({
            'access_token': generate_access_token(admin_user),
            'refresh_token': generate_refresh_token(admin_user),
            'user': UserProfileSerializer(admin_user).data,
        })

    return Response({'error': 'Invalid admin credentials'}, status=401)


@api_view(['GET'])
def admin_dashboard(request):
    err = _check_admin(request)
    if err:
        return err

    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    from astradev.projects.models import Project
    total_projects = Project.objects.count()
    pending_payments = Payment.objects.filter(status='pending').count()

    return Response({
        'total_users': total_users,
        'active_users': active_users,
        'total_projects': total_projects,
        'pending_payments': pending_payments,
        'plan_distribution': {
            'free': User.objects.filter(plan='free').count(),
            'pro': User.objects.filter(plan='pro').count(),
            'plus': User.objects.filter(plan='plus').count(),
        },
    })


@api_view(['GET'])
def admin_users(request):
    err = _check_admin(request)
    if err:
        return err

    users = User.objects.all().order_by('-created_at')
    data = [{
        'id': str(u.id),
        'email': u.email,
        'display_name': u.display_name,
        'plan': u.plan,
        'is_active': u.is_active,
        'is_staff': u.is_staff,
        'total_messages_sent': u.total_messages_sent,
        'total_projects_created': u.total_projects_created,
        'created_at': u.created_at.isoformat(),
    } for u in users]
    return Response(data)


@api_view(['GET'])
def admin_payments(request):
    err = _check_admin(request)
    if err:
        return err

    payments = Payment.objects.all().select_related('user')
    data = [{
        'id': str(p.id),
        'user_email': p.user.email,
        'plan': p.plan,
        'amount_usd': float(p.amount_usd),
        'amount_bdt': float(p.amount_bdt),
        'transaction_id': p.bkash_transaction_id,
        'sender_number': p.bkash_sender_number,
        'status': p.status,
        'created_at': p.created_at.isoformat(),
    } for p in payments]
    return Response(data)


@api_view(['POST'])
def admin_verify_payment(request, payment_id):
    err = _check_admin(request)
    if err:
        return err

    try:
        payment = Payment.objects.get(id=payment_id)
    except Payment.DoesNotExist:
        return Response({'error': 'Payment not found'}, status=404)

    action = request.data.get('action')  # 'verify' or 'reject'
    if action == 'verify':
        payment.status = 'verified'
        payment.verified_at = timezone.now()
        payment.save()
        # Upgrade user plan
        user = payment.user
        user.plan = payment.plan
        user.plan_expires_at = timezone.now() + timezone.timedelta(days=30)
        user.save(update_fields=['plan', 'plan_expires_at'])
        return Response({'message': f'Payment verified. User upgraded to {payment.plan}.'})
    elif action == 'reject':
        payment.status = 'rejected'
        payment.admin_note = request.data.get('note', '')
        payment.save()
        return Response({'message': 'Payment rejected.'})

    return Response({'error': 'Action must be verify or reject'}, status=400)


@api_view(['DELETE'])
def admin_delete_user(request, user_id):
    err = _check_admin(request)
    if err:
        return err

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=404)

    if user.is_superuser:
        return Response({'error': 'Cannot delete superuser'}, status=400)

    user.delete()
    return Response({'message': 'User deleted'})

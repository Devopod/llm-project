import re
from rest_framework import serializers
from .models import User


class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    display_name = serializers.CharField(max_length=150, required=False, default='')

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('Email already registered')
        return value

    def validate_password(self, value):
        if not re.search(r'[A-Z]', value):
            raise serializers.ValidationError('Must include uppercase letter')
        if not re.search(r'[a-z]', value):
            raise serializers.ValidationError('Must include lowercase letter')
        if not re.search(r'[0-9]', value):
            raise serializers.ValidationError('Must include number')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
            raise serializers.ValidationError('Must include special character')
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'display_name', 'avatar_url', 'bio', 'is_verified', 'plan', 'is_staff', 'created_at']
        read_only_fields = ['id', 'email', 'is_verified', 'plan', 'is_staff', 'created_at']

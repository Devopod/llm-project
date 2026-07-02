import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_verified', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    PLAN_CHOICES = [
        ('free', 'Free'),
        ('pro', 'Pro'),
        ('plus', 'Plus'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    display_name = models.CharField(max_length=150, blank=True)
    avatar_url = models.URLField(blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    plan = models.CharField(max_length=10, choices=PLAN_CHOICES, default='free')
    plan_expires_at = models.DateTimeField(null=True, blank=True)
    messages_used_today = models.IntegerField(default=0)
    apk_builds_today = models.IntegerField(default=0)
    usage_reset_date = models.DateField(null=True, blank=True)
    total_messages_sent = models.IntegerField(default=0)
    total_projects_created = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        app_label = 'accounts'

    def __str__(self):
        return self.email

    @property
    def message_limit(self):
        limits = {'free': 20, 'pro': 500, 'plus': 9999}
        return limits.get(self.plan, 20)

    @property
    def apk_limit(self):
        limits = {'free': 3, 'pro': 50, 'plus': 9999}
        return limits.get(self.plan, 3)

    def check_and_reset_usage(self):
        today = timezone.now().date()
        if self.usage_reset_date != today:
            self.messages_used_today = 0
            self.apk_builds_today = 0
            self.usage_reset_date = today
            self.save(update_fields=['messages_used_today', 'apk_builds_today', 'usage_reset_date'])

    def can_send_message(self):
        self.check_and_reset_usage()
        return self.messages_used_today < self.message_limit

    def can_build_apk(self):
        self.check_and_reset_usage()
        return self.apk_builds_today < self.apk_limit


class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    plan = models.CharField(max_length=10, choices=User.PLAN_CHOICES)
    amount_usd = models.DecimalField(max_digits=10, decimal_places=2)
    amount_bdt = models.DecimalField(max_digits=10, decimal_places=2)
    bkash_transaction_id = models.CharField(max_length=100)
    bkash_sender_number = models.CharField(max_length=20)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    admin_note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = 'accounts'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - {self.plan} - {self.status}"

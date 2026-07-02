import uuid
from django.db import models
from django.conf import settings


class Project(models.Model):
    STATUS_CHOICES = [
        ('created', 'Created'),
        ('planning', 'Planning'),
        ('executing', 'Executing'),
        ('testing', 'Testing'),
        ('deploying', 'Deploying'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('paused', 'Paused'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='projects')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='created')
    primary_language = models.CharField(max_length=50, blank=True, null=True)
    primary_framework = models.CharField(max_length=50, blank=True, null=True)
    workspace_container_id = models.CharField(max_length=100, blank=True, null=True)
    workspace_volume_name = models.CharField(max_length=100, blank=True, null=True)
    project_state = models.JSONField(default=dict, blank=True)
    roadmap = models.JSONField(default=dict, blank=True)
    deployment_url = models.URLField(blank=True, null=True)
    total_tokens_used = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = 'projects'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.status})"


class Task(models.Model):
    TASK_TYPE_CHOICES = [
        ('plan', 'Plan'),
        ('read_code', 'Read Code'),
        ('write_code', 'Write Code'),
        ('review', 'Review'),
        ('test', 'Test'),
        ('debug', 'Debug'),
        ('deploy', 'Deploy'),
        ('document', 'Document'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    parent_task = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subtasks')
    task_type = models.CharField(max_length=20, choices=TASK_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    assigned_agent = models.CharField(max_length=50, blank=True)
    input_data = models.JSONField(default=dict, blank=True)
    output_data = models.JSONField(default=dict, blank=True, null=True)
    error_log = models.TextField(blank=True, null=True)
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    tokens_used = models.IntegerField(default=0)
    order = models.IntegerField(default=0)
    dependencies = models.JSONField(default=list, blank=True)

    class Meta:
        app_label = 'projects'
        ordering = ['order']


class Message(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('orchestrator', 'Orchestrator'),
        ('planner', 'Planner'),
        ('reader', 'Reader'),
        ('writer', 'Writer'),
        ('reviewer', 'Reviewer'),
        ('tester', 'Tester'),
        ('debugger', 'Debugger'),
        ('deployer', 'Deployer'),
        ('documenter', 'Documenter'),
    ]
    MESSAGE_TYPE_CHOICES = [
        ('thinking', 'Thinking'),
        ('plan', 'Plan'),
        ('action', 'Action'),
        ('code', 'Code'),
        ('output', 'Output'),
        ('error', 'Error'),
        ('fix', 'Fix'),
        ('success', 'Success'),
        ('deployment', 'Deployment'),
        ('message', 'Message'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES, default='message')
    metadata = models.JSONField(default=dict, blank=True, null=True)
    tokens_input = models.IntegerField(default=0)
    tokens_output = models.IntegerField(default=0)
    api_key_used = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'projects'
        ordering = ['created_at']


class FileRecord(models.Model):
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('modified', 'Modified'),
        ('deleted', 'Deleted'),
        ('read', 'Read'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='files')
    path = models.CharField(max_length=500)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    content_hash = models.CharField(max_length=64, blank=True)
    size_bytes = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'projects'


class TokenUsage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    api_key_label = models.CharField(max_length=20)
    tokens_used = models.IntegerField()
    request_type = models.CharField(max_length=50)
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'projects'

import uuid
from django.db import models
from django.conf import settings


class Upload(models.Model):
    FILE_TYPE_CHOICES = [('zip', 'ZIP'), ('seven_z', '7Z')]
    STATUS_CHOICES = [
        ('uploaded', 'Uploaded'),
        ('extracting', 'Extracting'),
        ('analyzing', 'Analyzing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='uploads')
    project = models.ForeignKey('projects.Project', on_delete=models.SET_NULL, null=True, blank=True)
    original_filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    file_size = models.IntegerField()
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded')
    extraction_result = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'uploads'

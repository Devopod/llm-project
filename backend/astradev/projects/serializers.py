from rest_framework import serializers
from .models import Project, Task, Message, FileRecord


class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = '__all__'
        read_only_fields = ['id', 'started_at', 'completed_at', 'tokens_used']


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class FileRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileRecord
        fields = '__all__'


class ProjectSerializer(serializers.ModelSerializer):
    tasks_count = serializers.SerializerMethodField()
    completed_tasks = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = '__all__'
        read_only_fields = ['id', 'user', 'created_at', 'updated_at', 'completed_at',
                            'workspace_container_id', 'workspace_volume_name', 'total_tokens_used']

    def get_tasks_count(self, obj):
        return obj.tasks.count()

    def get_completed_tasks(self, obj):
        return obj.tasks.filter(status='completed').count()


class ProjectCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, default='')
    prompt = serializers.CharField(required=False, default='')

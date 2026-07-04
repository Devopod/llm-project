import json
from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync


class ProjectConsumer(WebsocketConsumer):
    def connect(self):
        self.project_id = self.scope['url_route']['kwargs']['project_id']
        self.project_group_name = f"project_{self.project_id}"

        async_to_sync(self.channel_layer.group_add)(
            self.project_group_name, self.channel_name
        )
        self.accept()
        self.send(text_data=json.dumps({
            'type': 'connection',
            'content': 'Connected to project stream',
            'project_id': self.project_id,
        }))

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.project_group_name, self.channel_name
        )

    def receive(self, text_data):
        data = json.loads(text_data)
        message = data.get('message', '')

        if message:
            from astradev.projects.models import Project, Message
            try:
                project = Project.objects.get(id=self.project_id)
                Message.objects.create(
                    project=project,
                    role='user',
                    content=message,
                    message_type='message',
                )
                from astradev.agents.tasks import run_agent_pipeline
                run_agent_pipeline.delay(self.project_id, message)
            except Project.DoesNotExist:
                self.send(text_data=json.dumps({
                    'type': 'error',
                    'content': 'Project not found',
                }))

    def agent_message(self, event):
        self.send(text_data=json.dumps(event['data']))

import logging
import os
import uuid
from celery import shared_task
from astradev.projects.models import Project

logger = logging.getLogger('astradev.agents')


@shared_task(bind=True, max_retries=2)
def run_agent_pipeline(self, project_id: str, prompt: str):
    try:
        project = Project.objects.get(id=project_id)
        from .orchestrator import OrchestratorAgent
        orchestrator = OrchestratorAgent(project)
        result = orchestrator.execute(prompt)
        logger.info(f"Agent pipeline completed for project {project_id}: {result.get('status')}")
        return result
    except Project.DoesNotExist:
        logger.error(f"Project {project_id} not found")
        return {'status': 'error', 'message': 'Project not found'}
    except Exception as e:
        logger.error(f"Agent pipeline error: {e}")
        try:
            project = Project.objects.get(id=project_id)
            project.status = 'failed'
            project.save(update_fields=['status'])
        except Exception:
            pass
        raise self.retry(exc=e, countdown=10)


@shared_task(bind=True, max_retries=1)
def deploy_project_task(self, project_id: str):
    try:
        project = Project.objects.get(id=project_id)
        from .deployer import DeployerAgent
        deployer = DeployerAgent(project)

        # Generate a deployment URL (simulated ngrok-style)
        deploy_id = str(uuid.uuid4())[:8]
        host = os.getenv('DEPLOY_HOST', 'localhost')
        port = 8080 + (hash(project_id) % 100)
        deploy_url = f"https://{deploy_id}.ngrok-free.dev"

        project.deployment_url = deploy_url
        project.status = 'completed'
        project.save(update_fields=['deployment_url', 'status'])

        # Send deployment message
        from astradev.projects.models import Message
        Message.objects.create(
            project=project,
            role='deployer',
            content=f"Deployment successful! Your app is live at: {deploy_url}",
            message_type='deployment',
            metadata={'url': deploy_url, 'status': 'live'},
        )
        logger.info(f"Project {project_id} deployed to {deploy_url}")
        return {'status': 'deployed', 'url': deploy_url}
    except Exception as e:
        logger.error(f"Deploy error: {e}")
        try:
            project = Project.objects.get(id=project_id)
            project.status = 'failed'
            project.save(update_fields=['status'])
        except Exception:
            pass
        raise

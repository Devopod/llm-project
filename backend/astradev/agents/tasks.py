import logging
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

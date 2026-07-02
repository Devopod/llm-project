"""Reverse proxy for deployed project apps.

Serves deployed project applications at /projects/<id>/deployed/
by proxying requests to the project's local server running on a dynamic port.
"""
import logging
import urllib.request
import urllib.error
from django.http import HttpResponse, Http404
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .models import Project

logger = logging.getLogger('astradev.agents')


@method_decorator(csrf_exempt, name='dispatch')
class DeployProxyView(View):
    def dispatch(self, request, project_id, path='', *args, **kwargs):
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            raise Http404("Project not found")

        deploy_info = project.project_state.get('deploy_info', {})
        port = deploy_info.get('port')
        if not port:
            return HttpResponse(
                "<h1>Not Deployed</h1><p>This project has not been deployed yet. "
                "Click the Deploy button in the project page.</p>",
                status=503, content_type='text/html'
            )

        # Build target URL
        target_url = f"http://127.0.0.1:{port}/{path}"
        if request.META.get('QUERY_STRING'):
            target_url += f"?{request.META['QUERY_STRING']}"

        try:
            # Forward the request
            headers = {}
            content_type = request.content_type
            if content_type:
                headers['Content-Type'] = content_type

            body = request.body if request.method in ('POST', 'PUT', 'PATCH') else None

            req = urllib.request.Request(
                target_url,
                data=body,
                headers=headers,
                method=request.method,
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                response_body = resp.read()
                response_content_type = resp.headers.get('Content-Type', 'text/html')
                django_response = HttpResponse(
                    response_body,
                    status=resp.status,
                    content_type=response_content_type,
                )
                return django_response

        except urllib.error.HTTPError as e:
            return HttpResponse(e.read(), status=e.code, content_type='text/html')
        except (urllib.error.URLError, ConnectionRefusedError, OSError):
            return HttpResponse(
                "<h1>Service Unavailable</h1><p>The deployed application is not running. "
                "Try deploying again.</p>",
                status=503, content_type='text/html'
            )

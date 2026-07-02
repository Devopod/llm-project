import os
import uuid
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from .models import Upload
from .tasks import extract_upload


@api_view(['POST'])
@parser_classes([MultiPartParser])
def upload_file(request):
    file = request.FILES.get('file')
    if not file:
        return Response({'error': {'code': 'NO_FILE', 'message': 'No file provided'}},
                        status=status.HTTP_400_BAD_REQUEST)

    # Validate extension
    ext = file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else ''
    if ext not in ('zip', '7z'):
        return Response({'error': {'code': 'INVALID_TYPE', 'message': 'Only .zip and .7z files allowed'}},
                        status=status.HTTP_400_BAD_REQUEST)

    # Validate size
    if file.size > settings.MAX_UPLOAD_SIZE:
        return Response({'error': {'code': 'TOO_LARGE', 'message': 'File exceeds 100MB limit'}},
                        status=status.HTTP_400_BAD_REQUEST)

    # Save file
    upload_dir = os.path.join(settings.MEDIA_ROOT, 'uploads', str(request.user.id))
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"{uuid.uuid4()}_{file.name}"
    file_path = os.path.join(upload_dir, filename)

    with open(file_path, 'wb') as f:
        for chunk in file.chunks():
            f.write(chunk)

    file_type = 'seven_z' if ext == '7z' else 'zip'
    upload = Upload.objects.create(
        user=request.user,
        original_filename=file.name,
        file_path=file_path,
        file_size=file.size,
        file_type=file_type,
    )

    # Trigger extraction
    extract_upload.delay(str(upload.id))

    return Response({
        'id': str(upload.id),
        'filename': file.name,
        'size': file.size,
        'status': upload.status,
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
def upload_status(request, upload_id):
    try:
        upload = Upload.objects.get(id=upload_id, user=request.user)
    except Upload.DoesNotExist:
        return Response({'error': {'code': 'NOT_FOUND', 'message': 'Upload not found'}},
                        status=status.HTTP_404_NOT_FOUND)

    return Response({
        'id': str(upload.id),
        'filename': upload.original_filename,
        'size': upload.file_size,
        'status': upload.status,
        'extraction_result': upload.extraction_result,
        'error_message': upload.error_message,
    })

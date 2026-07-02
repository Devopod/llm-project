import os
import zipfile
import tempfile
import logging
from celery import shared_task

logger = logging.getLogger('astradev.uploads')


@shared_task
def extract_upload(upload_id: str):
    from .models import Upload
    try:
        upload = Upload.objects.get(id=upload_id)
    except Upload.DoesNotExist:
        return

    upload.status = 'extracting'
    upload.save(update_fields=['status'])

    try:
        validate_archive(upload.file_path, upload.file_type)
        temp_dir = tempfile.mkdtemp(prefix='astradev_extract_')
        extract_archive(upload.file_path, upload.file_type, temp_dir)
        project_info = detect_project_type(temp_dir)
        file_stats = get_file_stats(temp_dir)

        upload.status = 'completed'
        upload.extraction_result = {
            'project_info': project_info,
            'file_stats': file_stats,
            'temp_dir': temp_dir,
        }
        upload.save()
    except Exception as e:
        upload.status = 'failed'
        upload.error_message = str(e)
        upload.save()
        logger.error(f"Upload extraction failed: {e}")


def validate_archive(file_path: str, file_type: str):
    if file_type == 'zip':
        with zipfile.ZipFile(file_path) as zf:
            total_size = sum(info.file_size for info in zf.infolist())
            if total_size > 500 * 1024 * 1024:
                raise ValueError("Extracted size exceeds 500MB limit")
            if len(zf.infolist()) > 10000:
                raise ValueError("Too many files in archive (max 10000)")
            for info in zf.infolist():
                if '..' in info.filename or info.filename.startswith('/'):
                    raise ValueError(f"Path traversal detected: {info.filename}")
    elif file_type == 'seven_z':
        import py7zr
        with py7zr.SevenZipFile(file_path, mode='r') as z:
            names = z.getnames()
            if len(names) > 10000:
                raise ValueError("Too many files in archive")
            for name in names:
                if '..' in name or name.startswith('/'):
                    raise ValueError(f"Path traversal detected: {name}")


def extract_archive(file_path: str, file_type: str, dest_dir: str):
    if file_type == 'zip':
        with zipfile.ZipFile(file_path, 'r') as zf:
            zf.extractall(dest_dir)
    elif file_type == 'seven_z':
        import py7zr
        with py7zr.SevenZipFile(file_path, mode='r') as z:
            z.extractall(path=dest_dir)


def detect_project_type(directory: str) -> dict:
    markers = {
        'package.json': ('JavaScript/TypeScript', None),
        'requirements.txt': ('Python', None),
        'Cargo.toml': ('Rust', None),
        'go.mod': ('Go', None),
        'pom.xml': ('Java', 'Maven'),
        'build.gradle': ('Java/Kotlin', 'Gradle'),
        'composer.json': ('PHP', None),
        'CMakeLists.txt': ('C/C++', 'CMake'),
        'next.config.js': ('JavaScript', 'Next.js'),
        'next.config.mjs': ('JavaScript', 'Next.js'),
        'manage.py': ('Python', 'Django'),
        'artisan': ('PHP', 'Laravel'),
    }

    detected = {'language': 'Unknown', 'framework': 'Unknown', 'markers_found': []}
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ('node_modules', '.git', '__pycache__')]
        for f in files:
            if f in markers:
                lang, fw = markers[f]
                detected['language'] = lang
                if fw:
                    detected['framework'] = fw
                detected['markers_found'].append(f)
        break  # Only check top level

    return detected


def get_file_stats(directory: str) -> dict:
    total_files = 0
    total_size = 0
    extensions = {}
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ('node_modules', '.git')]
        for f in files:
            total_files += 1
            fpath = os.path.join(root, f)
            size = os.path.getsize(fpath)
            total_size += size
            ext = f.rsplit('.', 1)[-1] if '.' in f else 'no_ext'
            extensions[ext] = extensions.get(ext, 0) + 1

    return {
        'total_files': total_files,
        'total_size_bytes': total_size,
        'extensions': extensions,
    }

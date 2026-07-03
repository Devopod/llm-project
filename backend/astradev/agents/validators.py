"""
AstraDev File Validation Pipeline

Validates generated files for completeness, syntax correctness, and quality.
Every file must pass ALL validators before the project can reach 'completed' state.

Pipeline: Writer -> Syntax -> AST -> Import -> Completeness -> Language-specific -> PASS/FAIL
"""

import ast
import json
import re
import os
import hashlib
import logging
import subprocess
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger('astradev.agents')


class ValidationStatus(Enum):
    PASSED = 'passed'
    FAILED = 'failed'
    WARNING = 'warning'


@dataclass
class ValidationResult:
    status: ValidationStatus
    file_path: str
    validator: str
    message: str
    line: int | None = None
    auto_fixable: bool = False


@dataclass
class FileValidationReport:
    file_path: str
    results: list[ValidationResult] = field(default_factory=list)
    sha256: str = ''
    line_count: int = 0
    byte_count: int = 0
    encoding: str = 'utf-8'
    syntax_ok: bool = False
    eof_ok: bool = False

    @property
    def passed(self) -> bool:
        return all(r.status != ValidationStatus.FAILED for r in self.results)

    @property
    def failures(self) -> list[ValidationResult]:
        return [r for r in self.results if r.status == ValidationStatus.FAILED]

    @property
    def summary(self) -> str:
        fails = self.failures
        if not fails:
            return f'{self.file_path}: ALL PASSED'
        msgs = '; '.join(f'{f.validator}: {f.message}' for f in fails[:3])
        return f'{self.file_path}: FAILED ({msgs})'


@dataclass
class ProjectValidationReport:
    file_reports: list[FileValidationReport] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.file_reports)

    @property
    def failed_files(self) -> list[FileValidationReport]:
        return [r for r in self.file_reports if not r.passed]

    @property
    def summary(self) -> str:
        total = len(self.file_reports)
        passed = sum(1 for r in self.file_reports if r.passed)
        return f'{passed}/{total} files passed validation'


# ---------------------------------------------------------------------------
# Individual Validators
# ---------------------------------------------------------------------------

def validate_not_empty(content: str, path: str) -> ValidationResult:
    stripped = content.strip()
    if not stripped:
        return ValidationResult(ValidationStatus.FAILED, path, 'empty_check',
                                'File is empty', auto_fixable=True)
    if len(stripped) < 10:
        return ValidationResult(ValidationStatus.FAILED, path, 'empty_check',
                                f'File too short ({len(stripped)} chars)', auto_fixable=True)
    return ValidationResult(ValidationStatus.PASSED, path, 'empty_check', 'OK')


def validate_encoding(content: str, path: str) -> ValidationResult:
    try:
        content.encode('utf-8')
        return ValidationResult(ValidationStatus.PASSED, path, 'encoding', 'UTF-8 valid')
    except UnicodeEncodeError as e:
        return ValidationResult(ValidationStatus.FAILED, path, 'encoding',
                                f'Encoding error: {e}', auto_fixable=False)


def validate_no_prompt_leakage(content: str, path: str) -> ValidationResult:
    """Detect LLM output artifacts leaked into file content."""
    leakage_patterns = [
        (r'^```(json|python|javascript|html|yaml|markdown|css|typescript)', 'Code fence wrapper'),
        (r'^Here (?:is|are) (?:the|a|an)', 'Conversational prefix'),
        (r'^Sure[,!]?\s', 'Conversational prefix'),
        (r'^I\'ll\s', 'Conversational prefix'),
        (r'^Let me\s', 'Conversational prefix'),
        (r'^Certainly', 'Conversational prefix'),
        (r'^Of course', 'Conversational prefix'),
    ]
    first_line = content.strip().split('\n')[0] if content.strip() else ''
    for pattern, desc in leakage_patterns:
        if re.match(pattern, first_line, re.IGNORECASE):
            return ValidationResult(ValidationStatus.FAILED, path, 'prompt_leakage',
                                    f'{desc}: "{first_line[:60]}"', auto_fixable=True)
    return ValidationResult(ValidationStatus.PASSED, path, 'prompt_leakage', 'No leakage')


def validate_no_placeholders(content: str, path: str) -> ValidationResult:
    """Detect placeholder/stub code that indicates incomplete generation."""
    placeholder_patterns = [
        (r'#\s*TODO\s*:?\s*implement', 'TODO placeholder'),
        (r'//\s*TODO\s*:?\s*implement', 'TODO placeholder'),
        (r'/\*\s*TODO\s*:?\s*implement', 'TODO placeholder'),
        (r'raise\s+NotImplementedError', 'NotImplementedError'),
        (r'#\s*\.\.\.', 'Ellipsis comment'),
        (r'//\s*\.\.\.', 'Ellipsis comment'),
        (r'#\s*rest of (?:the )?code', 'Incomplete marker'),
        (r'//\s*rest of (?:the )?code', 'Incomplete marker'),
        (r'#\s*continue (?:here|later|implementation)', 'Incomplete marker'),
        (r'#\s*add (?:more|rest|remaining)', 'Incomplete marker'),
        (r'//\s*add (?:more|rest|remaining)', 'Incomplete marker'),
    ]
    lines = content.strip().split('\n')
    for i, line in enumerate(lines):
        for pattern, desc in placeholder_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                # Allow 'pass' in small __init__.py or abstract methods
                if 'NotImplementedError' in line and path.endswith('__init__.py'):
                    continue
                return ValidationResult(ValidationStatus.FAILED, path, 'placeholder',
                                        f'{desc} at line {i+1}: {line.strip()[:80]}',
                                        line=i+1, auto_fixable=True)
    return ValidationResult(ValidationStatus.PASSED, path, 'placeholder', 'No placeholders')


# ---------------------------------------------------------------------------
# Python Validators
# ---------------------------------------------------------------------------

def validate_python_syntax(content: str, path: str) -> ValidationResult:
    try:
        ast.parse(content)
        return ValidationResult(ValidationStatus.PASSED, path, 'python_syntax', 'AST parse OK')
    except SyntaxError as e:
        return ValidationResult(ValidationStatus.FAILED, path, 'python_syntax',
                                f'Line {e.lineno}: {e.msg}', line=e.lineno, auto_fixable=True)


def validate_python_compile(content: str, path: str) -> ValidationResult:
    try:
        compile(content, path, 'exec')
        return ValidationResult(ValidationStatus.PASSED, path, 'python_compile', 'Compile OK')
    except SyntaxError as e:
        return ValidationResult(ValidationStatus.FAILED, path, 'python_compile',
                                f'Compile error line {e.lineno}: {e.msg}',
                                line=e.lineno, auto_fixable=True)


def validate_python_completeness(content: str, path: str) -> ValidationResult:
    """Check for truncated Python files."""
    stripped = content.rstrip()
    issues = []

    # Bracket balance
    opens = stripped.count('(') - stripped.count(')')
    if opens > 2:
        issues.append(f'Unclosed parentheses ({opens} extra)')
    brackets = stripped.count('[') - stripped.count(']')
    if brackets > 2:
        issues.append(f'Unclosed brackets ({brackets} extra)')
    braces = stripped.count('{') - stripped.count('}')
    if braces > 2:
        issues.append(f'Unclosed braces ({braces} extra)')

    # Triple-quote balance
    dq = stripped.count('"""')
    if dq % 2 != 0:
        issues.append('Unclosed triple-double-quote string')
    sq = stripped.count("'''")
    if sq % 2 != 0:
        issues.append('Unclosed triple-single-quote string')

    # Check for truncation markers
    last_lines = stripped.split('\n')[-3:]
    for line in last_lines:
        if re.match(r'^\s*\.\.\.\s*$', line):
            issues.append('File ends with ellipsis')

    if issues:
        return ValidationResult(ValidationStatus.FAILED, path, 'python_completeness',
                                '; '.join(issues), auto_fixable=True)
    return ValidationResult(ValidationStatus.PASSED, path, 'python_completeness', 'Complete')


def validate_python_imports(content: str, path: str) -> ValidationResult:
    """Check that import statements are well-formed."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return ValidationResult(ValidationStatus.WARNING, path, 'python_imports',
                                'Cannot check imports (syntax error)')

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                # Check for obviously broken imports
                if node.module.startswith('.') and not any(
                    n.name for n in node.names if n.name != '*'
                ):
                    return ValidationResult(ValidationStatus.WARNING, path, 'python_imports',
                                            f'Suspicious relative import: from {node.module}',
                                            line=node.lineno)
    return ValidationResult(ValidationStatus.PASSED, path, 'python_imports', 'Imports OK')


def validate_python_functions_complete(content: str, path: str) -> ValidationResult:
    """Check that functions and classes have bodies (not just 'pass' stubs in main files)."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return ValidationResult(ValidationStatus.WARNING, path, 'python_functions',
                                'Cannot check functions (syntax error)')

    # Skip __init__.py files — they legitimately have pass
    if os.path.basename(path) == '__init__.py':
        return ValidationResult(ValidationStatus.PASSED, path, 'python_functions', 'OK (init file)')

    stub_funcs = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            # A function with only a pass or only a docstring+pass is a stub
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                stub_funcs.append(node.name)
            elif (len(body) == 2
                  and isinstance(body[0], ast.Expr)
                  and isinstance(body[0].value, (ast.Constant, ast.Str))
                  and isinstance(body[1], ast.Pass)):
                stub_funcs.append(node.name)

    if stub_funcs and len(stub_funcs) > 2:
        return ValidationResult(ValidationStatus.FAILED, path, 'python_functions',
                                f'{len(stub_funcs)} stub functions: {", ".join(stub_funcs[:5])}',
                                auto_fixable=True)
    return ValidationResult(ValidationStatus.PASSED, path, 'python_functions', 'Functions complete')


# ---------------------------------------------------------------------------
# HTML Validators
# ---------------------------------------------------------------------------

def validate_html(content: str, path: str) -> ValidationResult:
    stripped = content.strip().lower()
    issues = []

    if '<html' in stripped and '</html>' not in stripped:
        issues.append('Missing </html> closing tag')
    if '<body' in stripped and '</body>' not in stripped:
        issues.append('Missing </body> closing tag')
    if '<head' in stripped and '</head>' not in stripped:
        issues.append('Missing </head> closing tag')

    # Check for unclosed script/style tags
    if stripped.count('<script') != stripped.count('</script>'):
        issues.append('Unclosed <script> tag')
    if stripped.count('<style') != stripped.count('</style>'):
        issues.append('Unclosed <style> tag')

    if issues:
        return ValidationResult(ValidationStatus.FAILED, path, 'html',
                                '; '.join(issues), auto_fixable=True)
    return ValidationResult(ValidationStatus.PASSED, path, 'html', 'HTML valid')


# ---------------------------------------------------------------------------
# JSON Validator
# ---------------------------------------------------------------------------

def validate_json(content: str, path: str) -> ValidationResult:
    try:
        json.loads(content)
        return ValidationResult(ValidationStatus.PASSED, path, 'json', 'JSON valid')
    except json.JSONDecodeError as e:
        return ValidationResult(ValidationStatus.FAILED, path, 'json',
                                f'JSON parse error: {e.msg} at line {e.lineno}',
                                line=e.lineno, auto_fixable=True)


# ---------------------------------------------------------------------------
# YAML Validator
# ---------------------------------------------------------------------------

def validate_yaml(content: str, path: str) -> ValidationResult:
    try:
        import yaml
        yaml.safe_load(content)
        return ValidationResult(ValidationStatus.PASSED, path, 'yaml', 'YAML valid')
    except ImportError:
        return ValidationResult(ValidationStatus.WARNING, path, 'yaml', 'PyYAML not installed')
    except Exception as e:
        return ValidationResult(ValidationStatus.FAILED, path, 'yaml',
                                f'YAML parse error: {str(e)[:100]}', auto_fixable=True)


# ---------------------------------------------------------------------------
# Markdown Validator
# ---------------------------------------------------------------------------

def validate_markdown(content: str, path: str) -> ValidationResult:
    """Validate markdown files, especially README.md."""
    issues = []
    stripped = content.strip()

    # Check for JSON wrapper leakage (common LLM bug)
    if stripped.startswith('{') or stripped.startswith('['):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict) and ('files' in parsed or 'content' in parsed or 'path' in parsed):
                issues.append('File contains JSON wrapper instead of markdown')
        except json.JSONDecodeError:
            pass

    # Check for prompt leakage patterns
    if '"files":' in stripped[:200] and '"content":' in stripped[:500]:
        issues.append('Contains JSON file/content structure (parser leakage)')
    if '"path":' in stripped[:200] and '"content":' in stripped[:500]:
        issues.append('Contains JSON path/content structure (parser leakage)')

    # Check code fence balance
    fence_count = stripped.count('```')
    if fence_count % 2 != 0:
        issues.append(f'Unclosed code fence (found {fence_count} backtick-triples)')

    if issues:
        return ValidationResult(ValidationStatus.FAILED, path, 'markdown',
                                '; '.join(issues), auto_fixable=True)
    return ValidationResult(ValidationStatus.PASSED, path, 'markdown', 'Markdown valid')


# ---------------------------------------------------------------------------
# JavaScript/TypeScript Validators
# ---------------------------------------------------------------------------

def validate_js_completeness(content: str, path: str) -> ValidationResult:
    """Basic JS/TS completeness check via brace/bracket balance."""
    stripped = content.rstrip()
    issues = []

    braces = stripped.count('{') - stripped.count('}')
    if braces > 2:
        issues.append(f'Unclosed braces ({braces} extra)')
    brackets = stripped.count('[') - stripped.count(']')
    if brackets > 2:
        issues.append(f'Unclosed brackets ({brackets} extra)')
    parens = stripped.count('(') - stripped.count(')')
    if parens > 2:
        issues.append(f'Unclosed parentheses ({parens} extra)')

    # Template literal balance
    backticks = stripped.count('`')
    if backticks % 2 != 0:
        issues.append('Unclosed template literal')

    if issues:
        return ValidationResult(ValidationStatus.FAILED, path, 'js_completeness',
                                '; '.join(issues), auto_fixable=True)
    return ValidationResult(ValidationStatus.PASSED, path, 'js_completeness', 'JS complete')


# ---------------------------------------------------------------------------
# CSS Validator
# ---------------------------------------------------------------------------

def validate_css(content: str, path: str) -> ValidationResult:
    stripped = content.rstrip()
    braces = stripped.count('{') - stripped.count('}')
    if braces != 0:
        return ValidationResult(ValidationStatus.FAILED, path, 'css',
                                f'Brace imbalance: {braces}', auto_fixable=True)
    return ValidationResult(ValidationStatus.PASSED, path, 'css', 'CSS valid')


# ---------------------------------------------------------------------------
# Dockerfile Validator
# ---------------------------------------------------------------------------

def validate_dockerfile(content: str, path: str) -> ValidationResult:
    stripped = content.strip()
    if not stripped:
        return ValidationResult(ValidationStatus.FAILED, path, 'dockerfile', 'Empty Dockerfile')

    has_from = any(line.strip().upper().startswith('FROM ') for line in stripped.split('\n'))
    if not has_from:
        return ValidationResult(ValidationStatus.FAILED, path, 'dockerfile',
                                'Missing FROM instruction', auto_fixable=True)
    return ValidationResult(ValidationStatus.PASSED, path, 'dockerfile', 'Dockerfile valid')


# ---------------------------------------------------------------------------
# Main Validation Orchestrator
# ---------------------------------------------------------------------------

def get_file_extension(path: str) -> str:
    _, ext = os.path.splitext(path)
    return ext.lower()


def validate_file(content: str, path: str) -> FileValidationReport:
    """Run all applicable validators on a single file."""
    report = FileValidationReport(
        file_path=path,
        sha256=hashlib.sha256(content.encode('utf-8', errors='replace')).hexdigest(),
        line_count=content.count('\n') + 1,
        byte_count=len(content.encode('utf-8', errors='replace')),
    )

    # Universal validators
    report.results.append(validate_not_empty(content, path))
    report.results.append(validate_encoding(content, path))
    report.results.append(validate_no_prompt_leakage(content, path))
    report.results.append(validate_no_placeholders(content, path))

    ext = get_file_extension(path)
    basename = os.path.basename(path).lower()

    # Language-specific validators
    if ext == '.py':
        report.results.append(validate_python_syntax(content, path))
        report.results.append(validate_python_compile(content, path))
        report.results.append(validate_python_completeness(content, path))
        report.results.append(validate_python_imports(content, path))
        report.results.append(validate_python_functions_complete(content, path))
        report.syntax_ok = all(
            r.status != ValidationStatus.FAILED
            for r in report.results
            if r.validator in ('python_syntax', 'python_compile')
        )

    elif ext in ('.html', '.htm'):
        report.results.append(validate_html(content, path))

    elif ext == '.json':
        report.results.append(validate_json(content, path))

    elif ext in ('.yaml', '.yml'):
        report.results.append(validate_yaml(content, path))

    elif ext == '.md':
        report.results.append(validate_markdown(content, path))

    elif ext in ('.js', '.jsx', '.ts', '.tsx'):
        report.results.append(validate_js_completeness(content, path))

    elif ext == '.css':
        report.results.append(validate_css(content, path))

    elif basename == 'dockerfile' or path.endswith('Dockerfile'):
        report.results.append(validate_dockerfile(content, path))

    # EOF check
    report.eof_ok = content.rstrip().endswith(('\n', '}', ')', ']', '>', ';', ':'))
    if not content.strip():
        report.eof_ok = False

    return report


def validate_workspace(workspace_path: str) -> ProjectValidationReport:
    """Validate all files in a project workspace."""
    project_report = ProjectValidationReport()

    if not os.path.isdir(workspace_path):
        return project_report

    skip_dirs = {'node_modules', '.git', '__pycache__', 'venv', '.venv', '.tox',
                 'dist', 'build', 'egg-info', '.eggs'}

    for root, dirs, files in os.walk(workspace_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            fpath = os.path.join(root, fname)
            rel_path = os.path.relpath(fpath, workspace_path)

            # Skip binary/generated files
            ext = get_file_extension(fname)
            if ext in ('.pyc', '.pyo', '.so', '.o', '.a', '.dll', '.exe',
                       '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg',
                       '.woff', '.woff2', '.ttf', '.eot', '.zip', '.tar',
                       '.gz', '.lock'):
                continue
            # Skip the launcher script we generate
            if fname == '_astradev_launcher.py':
                continue

            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                report = validate_file(content, rel_path)
                project_report.file_reports.append(report)
            except Exception as e:
                logger.warning(f'Could not validate {rel_path}: {e}')

    return project_report


def validate_runtime(workspace_path: str, port: int = None) -> list[ValidationResult]:
    """Validate that the application can actually run."""
    results = []

    # Check for Python apps
    py_files = []
    for root, dirs, files in os.walk(workspace_path):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', 'venv', '.venv', 'node_modules')]
        for f in files:
            if f.endswith('.py'):
                py_files.append(os.path.relpath(os.path.join(root, f), workspace_path))

    # Try py_compile on all Python files
    for py_file in py_files:
        full_path = os.path.join(workspace_path, py_file)
        try:
            proc = subprocess.run(
                ['python3', '-m', 'py_compile', full_path],
                capture_output=True, text=True, timeout=10
            )
            if proc.returncode != 0:
                results.append(ValidationResult(
                    ValidationStatus.FAILED, py_file, 'py_compile',
                    f'py_compile failed: {proc.stderr[:200]}', auto_fixable=True
                ))
            else:
                results.append(ValidationResult(
                    ValidationStatus.PASSED, py_file, 'py_compile', 'py_compile OK'
                ))
        except subprocess.TimeoutExpired:
            results.append(ValidationResult(
                ValidationStatus.WARNING, py_file, 'py_compile', 'Timeout'
            ))
        except Exception as e:
            results.append(ValidationResult(
                ValidationStatus.WARNING, py_file, 'py_compile', f'Error: {str(e)[:100]}'
            ))

    # Health check if port is provided
    if port:
        import urllib.request
        endpoints = ['/', '/health']
        for endpoint in endpoints:
            try:
                req = urllib.request.Request(f'http://127.0.0.1:{port}{endpoint}')
                req.add_header('User-Agent', 'AstraDev-Validator')
                resp = urllib.request.urlopen(req, timeout=5)
                if resp.status < 400:
                    results.append(ValidationResult(
                        ValidationStatus.PASSED, endpoint, 'health_check',
                        f'HTTP {resp.status}'
                    ))
                else:
                    results.append(ValidationResult(
                        ValidationStatus.FAILED, endpoint, 'health_check',
                        f'HTTP {resp.status}'
                    ))
            except Exception as e:
                if endpoint == '/health':
                    # /health is optional
                    results.append(ValidationResult(
                        ValidationStatus.WARNING, endpoint, 'health_check',
                        f'Not available: {str(e)[:60]}'
                    ))
                else:
                    results.append(ValidationResult(
                        ValidationStatus.FAILED, endpoint, 'health_check',
                        f'Failed: {str(e)[:60]}'
                    ))

    return results

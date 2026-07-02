"""Create sample projects for new users."""
import os
import uuid
import logging
from .models import Project, Task, Message, FileRecord

logger = logging.getLogger('astradev.agents')

FLASK_CALCULATOR_FILES = {
    'app.py': '''from flask import Flask, render_template, request, jsonify
from calc import add, subtract, multiply, divide

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/calculate', methods=['POST'])
def calculate():
    data = request.get_json()
    num1 = float(data.get('num1', 0))
    num2 = float(data.get('num2', 0))
    operation = data.get('operation', 'add')

    try:
        if operation == 'add':
            result = add(num1, num2)
        elif operation == 'subtract':
            result = subtract(num1, num2)
        elif operation == 'multiply':
            result = multiply(num1, num2)
        elif operation == 'divide':
            result = divide(num1, num2)
        else:
            return jsonify({'error': 'Invalid operation'}), 400
        return jsonify({'result': result})
    except ZeroDivisionError:
        return jsonify({'error': 'Cannot divide by zero'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 400


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
''',
    'calc.py': '''"""Basic arithmetic operations."""


def add(a, b):
    return float(a) + float(b)


def subtract(a, b):
    return float(a) - float(b)


def multiply(a, b):
    return float(a) * float(b)


def divide(a, b):
    if float(b) == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return float(a) / float(b)
''',
    'requirements.txt': 'flask\n',
    'templates/index.html': '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Flask Calculator</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', system-ui, sans-serif; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .calculator { background: #1e293b; border-radius: 20px; padding: 2rem; box-shadow: 0 25px 60px rgba(0,0,0,0.5); width: 360px; }
        h1 { color: #e2e8f0; text-align: center; margin-bottom: 1.5rem; font-size: 1.5rem; }
        .display { background: #0f172a; border: 2px solid #334155; border-radius: 12px; padding: 1rem; margin-bottom: 1.5rem; min-height: 60px; display: flex; align-items: center; justify-content: flex-end; }
        .display span { color: #4ade80; font-size: 2rem; font-family: 'Courier New', monospace; }
        .inputs { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-bottom: 1rem; }
        input { background: #0f172a; border: 2px solid #334155; border-radius: 10px; padding: 0.75rem 1rem; color: #e2e8f0; font-size: 1.1rem; outline: none; transition: border-color 0.2s; }
        input:focus { border-color: #6366f1; }
        .operations { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem; margin-bottom: 1rem; }
        .op-btn { padding: 0.75rem; border: none; border-radius: 10px; font-size: 1.2rem; cursor: pointer; transition: all 0.2s; background: #334155; color: #e2e8f0; }
        .op-btn:hover { background: #6366f1; transform: scale(1.05); }
        .op-btn.active { background: #6366f1; box-shadow: 0 0 15px rgba(99,102,241,0.5); }
        .calc-btn { width: 100%; padding: 0.9rem; border: none; border-radius: 12px; background: linear-gradient(135deg, #6366f1, #8b5cf6); color: white; font-size: 1.1rem; font-weight: 600; cursor: pointer; transition: all 0.2s; }
        .calc-btn:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(99,102,241,0.4); }
        .error { color: #f87171; text-align: center; margin-top: 0.5rem; font-size: 0.9rem; }
        .footer { text-align: center; color: #64748b; margin-top: 1rem; font-size: 0.8rem; }
    </style>
</head>
<body>
    <div class="calculator">
        <h1>Flask Calculator</h1>
        <div class="display"><span id="result">0</span></div>
        <div class="inputs">
            <input type="number" id="num1" placeholder="Number 1" step="any">
            <input type="number" id="num2" placeholder="Number 2" step="any">
        </div>
        <div class="operations">
            <button class="op-btn active" data-op="add">+</button>
            <button class="op-btn" data-op="subtract">-</button>
            <button class="op-btn" data-op="multiply">&times;</button>
            <button class="op-btn" data-op="divide">&divide;</button>
        </div>
        <button class="calc-btn" onclick="calculate()">Calculate</button>
        <p class="error" id="error"></p>
        <p class="footer">Built with AstraDev AI</p>
    </div>
    <script>
        let selectedOp = 'add';
        document.querySelectorAll('.op-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.op-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                selectedOp = btn.dataset.op;
            });
        });
        async function calculate() {
            const num1 = document.getElementById('num1').value;
            const num2 = document.getElementById('num2').value;
            document.getElementById('error').textContent = '';
            if (!num1 || !num2) { document.getElementById('error').textContent = 'Please enter both numbers'; return; }
            try {
                const res = await fetch('/calculate', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({num1: parseFloat(num1), num2: parseFloat(num2), operation: selectedOp})
                });
                const data = await res.json();
                if (data.error) { document.getElementById('error').textContent = data.error; document.getElementById('result').textContent = 'Error'; }
                else { document.getElementById('result').textContent = data.result; }
            } catch(e) { document.getElementById('error').textContent = 'Network error'; }
        }
    </script>
</body>
</html>
''',
}


def create_sample_projects(user):
    """Create sample Flask Calculator project for a new user."""
    project_id = uuid.uuid4()
    workspace = f"/tmp/astradev_workspaces/{project_id}"

    # Create workspace directory and files
    os.makedirs(workspace, exist_ok=True)
    for filepath, content in FLASK_CALCULATOR_FILES.items():
        full_path = os.path.join(workspace, filepath)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w') as f:
            f.write(content)

    # Create project record
    project = Project.objects.create(
        id=project_id,
        user=user,
        name='Flask Calculator (Sample)',
        description='A simple Flask web calculator with add, subtract, multiply, and divide operations. Built by AstraDev AI agents.',
        status='completed',
        primary_language='Python',
        project_state={
            'workspace_path': workspace,
            'file_tree': {k: {'type': 'file', 'size': len(v)} for k, v in FLASK_CALCULATOR_FILES.items()},
        },
    )

    # Create file records
    for filepath, content in FLASK_CALCULATOR_FILES.items():
        FileRecord.objects.create(
            project=project,
            path=filepath,
            action='created',
            size_bytes=len(content),
        )

    # Create task and messages
    Task.objects.create(
        project=project,
        task_type='write_code',
        title='Build Flask Calculator',
        description='Create a Flask web app with calculator functionality',
        status='completed',
        assigned_agent='writer',
    )
    Message.objects.create(
        project=project,
        role='orchestrator',
        content='Sample project created with complete Flask calculator code.',
        message_type='message',
    )

    logger.info(f"Created sample Flask Calculator project for user {user.email}")
    return project

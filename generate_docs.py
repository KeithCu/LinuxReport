"""
generate_docs.py

Automatically generates API documentation from Python files.
"""
import ast
import os
from typing import Dict, List, Set
import inspect
from dataclasses import is_dataclass

def parse_python_file(file_path: str) -> Dict:
    """Parse a Python file and extract class and function information."""
    with open(file_path, 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())
    
    classes = {}
    functions = {}
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = []
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    methods.append({
                        'name': item.name,
                        'args': [arg.arg for arg in item.args.args],
                        'returns': getattr(item.returns, 'id', None) if item.returns else None
                    })
            classes[node.name] = {
                'methods': methods,
                'docstring': ast.get_docstring(node)
            }
        elif isinstance(node, ast.FunctionDef):
            functions[node.name] = {
                'args': [arg.arg for arg in node.args.args],
                'returns': getattr(node.returns, 'id', None) if node.returns else None,
                'docstring': ast.get_docstring(node)
            }
    
    return {
        'classes': classes,
        'functions': functions
    }

def get_module_dependencies(file_path: str) -> Set[str]:
    """Extract module dependencies from a Python file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())
    
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                imports.add(name.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    
    return imports

def should_process_file(file_path: str) -> bool:
    """Determine if a file should be processed for documentation."""
    # Skip files in venv directory
    if 'venv' in file_path.split(os.sep):
        return False
    
    # Skip files in __pycache__ directories
    if '__pycache__' in file_path.split(os.sep):
        return False
    
    # Skip files in .git directory
    if '.git' in file_path.split(os.sep):
        return False
    
    return True

def generate_markdown_docs(directory: str) -> str:
    """Generate markdown documentation for all Python files in a directory."""
    docs = ["# API Documentation\n"]
    
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                
                # Skip files that shouldn't be processed
                if not should_process_file(file_path):
                    continue
                
                module_name = os.path.splitext(file)[0]
                
                # Parse the file
                parsed = parse_python_file(file_path)
                deps = get_module_dependencies(file_path)
                
                # Add module section
                docs.append(f"\n## {module_name}\n")
                docs.append(f"**File**: `{file_path}`\n")
                
                # Add dependencies
                if deps:
                    docs.append("\n### Dependencies")
                    docs.append("```python")
                    for dep in sorted(deps):
                        docs.append(f"import {dep}")
                    docs.append("```\n")
                
                # Add classes
                if parsed['classes']:
                    docs.append("\n### Classes")
                    for class_name, class_info in parsed['classes'].items():
                        docs.append(f"\n#### {class_name}")
                        if class_info['docstring']:
                            docs.append(f"\n{class_info['docstring']}\n")
                        if class_info['methods']:
                            docs.append("\nMethods:")
                            for method in class_info['methods']:
                                args = ', '.join(method['args'])
                                returns = f" -> {method['returns']}" if method['returns'] else ""
                                docs.append(f"- `{method['name']}({args}){returns}`")
                
                # Add functions
                if parsed['functions']:
                    docs.append("\n### Functions")
                    for func_name, func_info in parsed['functions'].items():
                        docs.append(f"\n#### {func_name}")
                        if func_info['docstring']:
                            docs.append(f"\n{func_info['docstring']}\n")
                        args = ', '.join(func_info['args'])
                        returns = f" -> {func_info['returns']}" if func_info['returns'] else ""
                        docs.append(f"```python\ndef {func_name}({args}){returns}\n```")
    
    return '\n'.join(docs)

if __name__ == '__main__':
    # Generate documentation for the current directory
    docs = generate_markdown_docs('.')
    
    # Write to file
    with open('api_docs.md', 'w', encoding='utf-8') as f:
        f.write(docs) 
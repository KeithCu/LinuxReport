"""
generate_dependency_graph.py

Generates:
1. A function-level dependency graph using graphviz (SVG format)
2. A markdown documentation of function dependencies
3. A JSON database of function dependencies for querying
"""
import ast
import os
import json
from typing import Dict, Set, List, Tuple
import graphviz
from datetime import datetime
from pathlib import Path

class FunctionVisitor(ast.NodeVisitor):
    """AST visitor to collect function definitions and their calls."""
    def __init__(self):
        self.functions = {}  # name -> (args, docstring)
        self.calls = {}      # function -> set of called functions
        self.current_function = None
        self.imports = set()  # Track imported modules
        self.classes = {}    # Track class definitions and their bases
        self.class_methods = {}  # Track methods within classes
        self.class_instances = {}  # Track class instantiations
    
    def _get_attr_name(self, node):
        """Recursively extract the full name from an Attribute node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            value = self._get_attr_name(node.value)
            return f"{value}.{node.attr}"
        else:
            return None

    def visit_Import(self, node):
        for name in node.names:
            self.imports.add(name.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            self.imports.add(node.module)
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        # Track class inheritance
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
                # Add inheritance relationship to calls
                if self.current_function:
                    self.calls[self.current_function].add(base.id)
            elif isinstance(base, ast.Attribute):
                base_name = self._get_attr_name(base)
                if base_name:
                    bases.append(base_name)
                    # Add inheritance relationship to calls
                    if self.current_function:
                        self.calls[self.current_function].add(base_name)
        
        self.classes[node.name] = bases
        
        # Track methods within this class
        self.class_methods[node.name] = {}
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                self.class_methods[node.name][item.name] = {
                    'args': [arg.arg for arg in item.args.args],
                    'docstring': ast.get_docstring(item)
                }
        
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        # Store function definition
        self.functions[node.name] = {
            'args': [arg.arg for arg in node.args.args],
            'docstring': ast.get_docstring(node)
        }
        
        # Track function calls within this function
        self.current_function = node.name
        self.calls[node.name] = set()
        self.generic_visit(node)
        self.current_function = None

    def visit_With(self, node):
        """Handle with statements to track context manager usage."""
        if self.current_function:
            for item in node.items:
                # Handle the context manager expression
                if isinstance(item.context_expr, ast.Call):
                    # Direct call like with get_lock("name"):
                    if isinstance(item.context_expr.func, ast.Name):
                        self.calls[self.current_function].add(item.context_expr.func.id)
                        # Track the class being instantiated
                        if item.context_expr.func.id in self.classes:
                            self.class_instances.setdefault(item.context_expr.func.id, set()).add(self.current_function)
                    # Method call like with some_obj.get_lock():
                    elif isinstance(item.context_expr.func, ast.Attribute):
                        if isinstance(item.context_expr.func.value, ast.Name):
                            self.calls[self.current_function].add(f"{item.context_expr.func.value.id}.{item.context_expr.func.attr}")
                # Handle the context manager itself
                elif isinstance(item.context_expr, ast.Name):
                    # Direct variable like with lock:
                    self.calls[self.current_function].add(item.context_expr.id)
                elif isinstance(item.context_expr, ast.Attribute):
                    # Attribute access like with obj.lock:
                    if isinstance(item.context_expr.value, ast.Name):
                        self.calls[self.current_function].add(f"{item.context_expr.value.id}.{item.context_expr.attr}")
        self.generic_visit(node)

    def visit_Call(self, node):
        if self.current_function:
            if isinstance(node.func, ast.Name):
                # Direct function call
                self.calls[self.current_function].add(node.func.id)
                # Track class instantiation
                if node.func.id in self.classes:
                    self.class_instances.setdefault(node.func.id, set()).add(self.current_function)
            elif isinstance(node.func, ast.Attribute):
                # Method call or imported function
                if isinstance(node.func.value, ast.Name):
                    self.calls[self.current_function].add(f"{node.func.value.id}.{node.func.attr}")
                elif isinstance(node.func.value, ast.Call):
                    # Handle cases like issubclass(LOCK_CLASS, FileLockWrapper)
                    if isinstance(node.func.value.func, ast.Name) and node.func.value.func.id == 'issubclass':
                        args = node.func.value.args
                        if len(args) == 2:
                            if isinstance(args[0], ast.Name) and isinstance(args[1], ast.Name):
                                # Add both the class and its base as dependencies
                                self.calls[self.current_function].add(args[0].id)
                                self.calls[self.current_function].add(args[1].id)
                                # Track class relationships
                                if args[0].id in self.classes:
                                    self.class_instances.setdefault(args[0].id, set()).add(self.current_function)
                                if args[1].id in self.classes:
                                    self.class_instances.setdefault(args[1].id, set()).add(self.current_function)
        self.generic_visit(node)

def get_function_dependencies(file_path: str) -> Tuple[Dict, Dict, Set]:
    """Extract function definitions and their dependencies from a Python file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        # Try with different encoding or skip the file
        try:
            with open(file_path, 'r', encoding='latin-1') as f:
                content = f.read()
        except Exception:
            # Skip files that can't be decoded
            return {}, {}, set()
    
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        # Skip files with syntax errors
        return {}, {}, set()
    
    try:
        visitor = FunctionVisitor()
        visitor.visit(tree)
        
        # Add class instantiation relationships to calls
        for class_name, callers in visitor.class_instances.items():
            for caller in callers:
                visitor.calls[caller].add(class_name)
        
        return visitor.functions, visitor.calls, visitor.imports
    except (RecursionError, AttributeError, TypeError) as e:
        # Skip files that cause recursion errors or other AST parsing issues
        print(f"Warning: Skipping {file_path} due to error: {e}")
        return {}, {}, set()

def should_process_file(file_path: str) -> bool:
    """Determine if a file should be processed."""
    if '.venv' in file_path.split(os.sep):
        return False
    if '__pycache__' in file_path.split(os.sep):
        return False
    if '.git' in file_path.split(os.sep):
        return False
    # Exclude test files
    if 'tests' in file_path.split(os.sep):
        return False
    if os.path.basename(file_path).startswith('test_'):
        return False
    # Exclude the dependency graph generator itself
    if os.path.basename(file_path) == 'generate_dependency_graph.py':
        return False
    return True

def generate_documentation(directory: str) -> None:
    """Generate markdown documentation and JSON database of function dependencies."""
    # Track all functions and their dependencies
    all_functions = {}  # module -> {function -> function info}
    all_calls = {}      # module -> {function -> set of called functions}
    all_imports = {}    # module -> set of imported modules
    
    # First pass: collect all functions and their dependencies
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                file_path = Path(root) / file
                if should_process_file(str(file_path)):
                    module_name = Path(file).stem
                    functions, calls, imports = get_function_dependencies(str(file_path))
                    
                    all_functions[module_name] = functions
                    all_calls[module_name] = calls
                    all_imports[module_name] = imports

    # Build reverse dependency map
    reverse_deps = {}  # module.function -> set of (module.function) that call it
    for module_name, calls in all_calls.items():
        for caller, callees in calls.items():
            for callee in callees:
                # Handle both direct function calls and module.function calls
                if '.' in callee:
                    # Already in module.function format
                    reverse_deps.setdefault(callee, set()).add(f"{module_name}.{caller}")
                else:
                    # Direct function call - check all modules
                    for other_module in all_functions:
                        if callee in all_functions[other_module]:
                            reverse_deps.setdefault(f"{other_module}.{callee}", set()).add(f"{module_name}.{caller}")

    # Generate markdown documentation
    with open('function_dependencies.md', 'w', encoding='utf-8') as f:
        f.write(f"# Function Dependencies Documentation\n\n")
        f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        # Table of Contents
        f.write("## Table of Contents\n\n")
        for module_name in sorted(all_functions.keys()):
            f.write(f"- [{module_name}](#{module_name.lower()})\n")
        f.write("\n")
        
        # Module sections
        for module_name in sorted(all_functions.keys()):
            f.write(f"## {module_name}\n\n")
            
            # Module imports - commented out for now
            # if all_imports[module_name]:
            #     f.write("### Imports\n\n")
            #     for imp in sorted(all_imports[module_name]):
            #         f.write(f"- `{imp}`\n")
            #     f.write("\n")
            
            # Functions
            f.write("### Functions\n\n")
            for func_name, func_info in sorted(all_functions[module_name].items()):
                f.write(f"#### {func_name}\n\n")
                if func_info['docstring']:
                    f.write(f"{func_info['docstring']}\n\n")
                f.write(f"**Arguments:** `{', '.join(func_info['args'])}`\n\n")
                
                # Function calls - commented out for now
                # if func_name in all_calls[module_name] and all_calls[module_name][func_name]:
                #     f.write("**Calls:**\n\n")
                #     for called_func in sorted(all_calls[module_name][func_name]):
                #         f.write(f"- `{called_func}`\n")
                #     f.write("\n")
                
                # Reverse dependencies (who calls this function)
                f.write("**Called by:**\n\n")
                full_func_name = f"{module_name}.{func_name}"
                called_by = sorted(reverse_deps.get(full_func_name, set()))
                if called_by:
                    for caller in called_by:
                        f.write(f"- `{caller}`\n")
                else:
                    f.write("- No other functions call this function\n")
                f.write("\n")

    # Generate JSON database
    dependency_db = {
        'generated_at': datetime.now().isoformat(),
        'modules': {}
    }
    
    for module_name in all_functions:
        dependency_db['modules'][module_name] = {
            # 'imports': list(all_imports[module_name]),  # Commented out for now
            'functions': {}
        }
        
        for func_name, func_info in all_functions[module_name].items():
            full_func_name = f"{module_name}.{func_name}"
            dependency_db['modules'][module_name]['functions'][func_name] = {
                'arguments': func_info['args'],
                'docstring': func_info['docstring'],
                # 'calls': list(all_calls[module_name].get(func_name, set())),  # Commented out for now
                'called_by': sorted(reverse_deps.get(full_func_name, set()))
            }

    with open('function_dependencies.json', 'w', encoding='utf-8') as f:
        json.dump(dependency_db, f, indent=2)

def generate_function_graph(directory: str) -> None:
    """Generate a function-level dependency graph for all Python files in a directory."""
    # Create a new directed graph
    dot = graphviz.Digraph(comment='Function Dependencies')
    
    # Set graph attributes for force-directed layout
    dot.attr('graph', layout='fdp')  # Force-directed placement
    dot.attr('graph', splines='true')  # Curved edges
    dot.attr('graph', overlap='false')
    dot.attr('graph', sep='+25,25')
    dot.attr('graph', nodesep='0.8')
    dot.attr('graph', ranksep='1.0')
    dot.attr('graph', size='11.7,8.3')  # A4 landscape
    dot.attr('graph', ratio='fill')
    dot.attr('graph', concentrate='true')  # Merge edges
    
    # Node styling
    dot.attr('node', shape='box', style='rounded,filled', fillcolor='lightblue')
    dot.attr('node', fontname='Arial')
    dot.attr('node', fontsize='12')  # Increased font size
    dot.attr('node', margin='0.2')   # Added margin for better spacing
    
    # Edge styling
    dot.attr('edge', fontname='Arial')
    dot.attr('edge', fontsize='10')  # Increased font size
    dot.attr('edge', penwidth='1.5') # Increased edge width
    
    # Track all functions and their dependencies
    all_functions = {}  # module -> {function -> function info}
    all_calls = {}      # module -> {function -> set of called functions}
    all_imports = {}    # module -> set of imported modules
    
    # First pass: collect all functions and their dependencies
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                file_path = Path(root) / file
                if should_process_file(str(file_path)):
                    module_name = Path(file).stem
                    functions, calls, imports = get_function_dependencies(str(file_path))
                    
                    all_functions[module_name] = functions
                    all_calls[module_name] = calls
                    all_imports[module_name] = imports
    
    # Create subgraphs for each module
    for module_name, functions in all_functions.items():
        with dot.subgraph(name=f'cluster_{module_name}') as s:
            s.attr(label=module_name)
            s.attr(style='rounded')
            s.attr(bgcolor='lightgrey')
            s.attr('node', shape='box', style='rounded,filled', fillcolor='lightblue')
            
            # Add nodes for each function in this module
            for func_name, func_info in functions.items():
                args = ', '.join(func_info['args'])
                label = f"{func_name}({args})"
                s.node(f"{module_name}.{func_name}", label)
    
    # Add edges for function calls
    for module_name, calls in all_calls.items():
        for func_name, called_funcs in calls.items():
            for called_func in called_funcs:
                # Check if this is a cross-module call
                for other_module in all_functions:
                    if called_func in all_functions[other_module]:
                        # Create edge with appropriate style
                        if other_module == module_name:
                            # Internal call
                            dot.edge(
                                f"{module_name}.{func_name}",
                                f"{other_module}.{called_func}",
                                style='solid',
                                penwidth='1.0'
                            )
                        else:
                            # Cross-module call
                            dot.edge(
                                f"{module_name}.{func_name}",
                                f"{other_module}.{called_func}",
                                style='dashed',
                                color='red',
                                penwidth='1.5'
                            )
    
    # Save the graph
    dot.render('function_dependency_graph', format='svg', cleanup=True)
    print("Function dependency graph generated as 'function_dependency_graph.svg'")
    
    # Also generate documentation
    generate_documentation(directory)

if __name__ == '__main__':
    generate_function_graph('.') 
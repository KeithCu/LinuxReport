#!/usr/bin/env python3
"""
Advanced Requirements Minimizer

This script uses a dependency database to minimize requirements without
having to query each package individually. Much faster than the basic version.
"""

import json
import requests
from typing import List, Set, Tuple, Dict
import time
from pathlib import Path


def get_package_dependencies_from_pypi(package_name: str) -> Set[str]:
    """
    Get package dependencies from PyPI API.
    """
    try:
        url = f"https://pypi.org/pypi/{package_name}/json"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            info = data.get('info', {})
            requires_dist = info.get('requires_dist', [])
            
            dependencies = set()
            if requires_dist is not None:
                for req in requires_dist:
                    if req and isinstance(req, str):
                        # Extract package name from requirement string
                        # e.g., "requests>=2.25.1" -> "requests"
                        package = req.split('[')[0].split('>=')[0].split('<=')[0].split('==')[0].split('!=')[0].split('~=')[0].split('>')[0].split('<')[0].strip()
                        if package and not package.startswith('#'):
                            dependencies.add(package)
            
            return dependencies
    except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
        print(f"Warning: Could not get dependencies for {package_name}: {e}")
    
    return set()


def build_dependency_cache(packages: List[Tuple[str, str]]) -> Dict[str, Set[str]]:
    """
    Build a cache of package dependencies to minimize API calls.
    """
    cache = {}
    unique_packages = set()
    
    # First pass: collect all unique package names
    for package_name, _ in packages:
        unique_packages.add(package_name.lower())
    
    print(f"Building dependency cache for {len(unique_packages)} unique packages...")
    
    # Second pass: get dependencies for each unique package
    for i, package_name in enumerate(sorted(unique_packages)):
        print(f"Querying {package_name} ({i+1}/{len(unique_packages)})")
        try:
            deps = get_package_dependencies_from_pypi(package_name)
            cache[package_name] = deps
        except (ValueError, TypeError) as e:
            print(f"Error processing {package_name}: {e}")
            cache[package_name] = set()
        
        # Small delay to be respectful to PyPI
        time.sleep(0.2)
    
    return cache


def get_all_transitive_dependencies(package_name: str, dependency_cache: Dict[str, Set[str]], visited: Set[str] = None) -> Set[str]:
    """
    Recursively get all transitive dependencies of a package.
    """
    if visited is None:
        visited = set()
    
    if package_name.lower() in visited:
        return set()  # Avoid circular dependencies
    
    visited.add(package_name.lower())
    all_deps = set()
    
    # Get direct dependencies
    direct_deps = dependency_cache.get(package_name.lower(), set())
    all_deps.update(direct_deps)
    
    # Recursively get transitive dependencies
    for dep in direct_deps:
        transitive_deps = get_all_transitive_dependencies(dep, dependency_cache, visited.copy())
        all_deps.update(transitive_deps)
    
    return all_deps


def minimize_requirements_advanced(packages: List[Tuple[str, str]], dependency_cache: Dict[str, Set[str]]) -> List[Tuple[str, str]]:
    """
    Advanced minimization using recursive dependency cache.
    """
    # Collect all transitive dependencies and track which package requires what
    all_dependencies = set()
    dependency_sources = {}  # Track which package requires each dependency
    
    for package_name, _ in packages:
        # Get all transitive dependencies (recursive)
        deps = get_all_transitive_dependencies(package_name, dependency_cache)
        all_dependencies.update(deps)
        
        # Track which package requires each dependency
        for dep in deps:
            if dep.lower() not in dependency_sources:
                dependency_sources[dep.lower()] = []
            dependency_sources[dep.lower()].append(package_name)
    
    # Filter out packages that are dependencies of others
    minimal_packages = []
    removed_packages = []
    
    for package_name, version in packages:
        if package_name.lower() not in {dep.lower() for dep in all_dependencies}:
            minimal_packages.append((package_name, version))
        else:
            # Track what this package is a dependency of
            requiring_packages = dependency_sources.get(package_name.lower(), [])
            removed_packages.append((package_name, version, requiring_packages))
    
    # Show all removed dependencies
    if removed_packages:
        print(f"\nAll removed dependencies (including transitive):")
        for removed_pkg, removed_ver, requiring_pkgs in sorted(removed_packages, key=lambda x: x[0].lower()):
            print(f"  {removed_pkg}=={removed_ver} (required by: {', '.join(sorted(requiring_pkgs))})")
    
    return minimal_packages


def parse_requirements_from_file(file_path: str) -> List[Tuple[str, str]]:
    """
    Parse requirements from a file.
    """
    packages = []
    
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Split by whitespace and get package name and version
                    parts = line.split()
                    if len(parts) >= 2:
                        package_name = parts[0]
                        version = parts[1]
                        # Skip header lines and invalid package names
                        if (package_name != "Package" and 
                            package_name != "-------------------------" and
                            not package_name.startswith('-')):
                            packages.append((package_name, version))
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found")
        return []
    
    return packages


def write_requirements_file(packages: List[Tuple[str, str]], output_file: str):
    """
    Write packages to a requirements file.
    """
    with open(output_file, 'w') as f:
        for package_name, version in sorted(packages, key=lambda x: x[0].lower()):
            f.write(f"{package_name}>={version}\n")


import os

def save_dependency_cache(cache: Dict[str, Set[str]], cache_dir: str):
    """
    Save dependency cache to individual files in a directory for future use.
    """
    # Create cache directory if it doesn't exist
    Path(cache_dir).mkdir(parents=True, exist_ok=True)

    # Save each package's dependencies to a separate file
    for package_name, dependencies in cache.items():
        cache_file = Path(cache_dir) / f"{package_name}.json"
        # Convert set to list for JSON serialization
        deps_list = list(dependencies)
        
        with open(cache_file, 'w') as f:
            json.dump(deps_list, f, indent=2)
    
    print(f"Saved dependency cache for {len(cache)} packages to {cache_dir}/")


def load_dependency_cache(cache_dir: str) -> Dict[str, Set[str]]:
    """
    Load dependency cache from individual files in directory.
    """
    cache = {}

    if not Path(cache_dir).exists():
        return cache

    # Load each package's dependencies from individual files
    for filename in os.listdir(cache_dir):
        if filename.endswith('.json'):
            package_name = filename[:-5]  # Remove .json extension
            cache_file = Path(cache_dir) / filename
            
            try:
                with open(cache_file, 'r') as f:
                    deps_list = json.load(f)
                    cache[package_name] = set(deps_list)
            except (json.JSONDecodeError, FileNotFoundError):
                print(f"Warning: Could not load cache for {package_name}")
    
    return cache


def main():
    input_file = "fulllist.txt"
    cache_dir = "dependency_cache"
    
    print(f"Parsing requirements from {input_file}...")
    packages = parse_requirements_from_file(input_file)
    
    if not packages:
        print("No packages found. Please check the input file format.")
        return
    
    print(f"Original packages: {len(packages)}")
    
    # Try to load existing cache
    dependency_cache = load_dependency_cache(cache_dir)
    if dependency_cache:
        print(f"Loaded existing dependency cache with {len(dependency_cache)} packages")
    else:
        print("No existing cache found, building new one...")
        dependency_cache = build_dependency_cache(packages)
        save_dependency_cache(dependency_cache, cache_dir)
    
    # Minimize requirements using cache
    minimal_packages = minimize_requirements_advanced(packages, dependency_cache)
    
    print(f"\nMinimal packages: {len(minimal_packages)}")
    print(f"Removed {len(packages) - len(minimal_packages)} dependencies")
    
    # Write output
    output_file = "computed_requirements.txt"
    write_requirements_file(minimal_packages, output_file)
    print(f"\nMinimal requirements written to {output_file}")
    
    print("\nMinimal packages:")
    for package_name, version in sorted(minimal_packages, key=lambda x: x[0].lower()):
        print(f"  {package_name}>={version}")


if __name__ == '__main__':
    main() 
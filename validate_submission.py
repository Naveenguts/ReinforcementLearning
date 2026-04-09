#!/usr/bin/env python3
"""
Meta Hackathon Phase 1 Validation Script
=========================================

This script validates that your Supply Chain Chaos environment meets 
all Meta hackathon Phase 1 automated gate requirements.

Run this BEFORE submitting to identify any issues.
"""

import subprocess
import sys
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

# Color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
END = "\033[0m"


def print_header(text: str) -> None:
    """Print a colored header."""
    print(f"\n{BLUE}{'='*60}{END}")
    print(f"{BLUE}{text}{END}")
    print(f"{BLUE}{'='*60}{END}\n")


def print_pass(text: str) -> None:
    """Print passing test."""
    print(f"{GREEN}✅ PASS{END}  {text}")


def print_fail(text: str) -> None:
    """Print failing test."""
    print(f"{RED}✗ FAIL{END}  {text}")


def print_warn(text: str) -> None:
    """Print warning."""
    print(f"{YELLOW}⚠️  WARN{END}  {text}")


def check_python_syntax(file_path: str) -> Tuple[bool, str]:
    """Check if Python file has valid syntax."""
    try:
        with open(file_path, "r") as f:
            compile(f.read(), file_path, "exec")
        return True, "OK"
    except SyntaxError as e:
        return False, f"Syntax error at line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def check_file_exists(file_path: str) -> bool:
    """Check if file exists."""
    return Path(file_path).exists()


def check_openenv_yaml() -> Tuple[bool, Dict]:
    """Validate openenv.yaml structure."""
    try:
        import yaml
        with open("openenv.yaml", "r") as f:
            config = yaml.safe_load(f)
        
        required_fields = ["name", "version", "description", "entrypoint"]
        required_tasks = ["tasks", "observation", "action", "endpoints"]
        
        missing_fields = [f for f in required_fields if f not in config]
        missing_tasks = [f for f in required_tasks if f not in config]
        
        if missing_fields or missing_tasks:
            return False, {"missing": missing_fields + missing_tasks}
        
        # Check tasks array
        tasks = config.get("tasks", [])
        if len(tasks) < 3:
            return False, {"error": f"Only {len(tasks)} tasks defined, need 3+"}
        
        task_names = {t.get("name") for t in tasks}
        required_task_names = {"steady_state", "port_strike", "black_swan"}
        if not required_task_names.issubset(task_names):
            return False, {"missing_tasks": list(required_task_names - task_names)}
        
        return True, {"tasks": len(tasks), "endpoints": len(config.get("endpoints", []))}
    
    except ImportError:
        return None, {"warning": "PyYAML not installed, skipping YAML validation"}
    except Exception as e:
        return False, {"error": str(e)}


def check_env_vars_in_inference() -> Tuple[bool, List[str]]:
    """Check if inference.py reads required env vars."""
    try:
        with open("inference.py", "r") as f:
            content = f.read()
        
        required_vars = ["API_BASE_URL", "API_KEY", "SUPPLY_CHAIN_HF_MODEL"]
        found_vars = []
        
        for var in required_vars:
            # Accept getenv forms with or without default arguments.
            pattern = re.compile(
                rf"(?:os\.)?getenv\(\s*['\"]{re.escape(var)}['\"]\s*(?:,|\))",
                re.IGNORECASE,
            )
            if pattern.search(content):
                found_vars.append(var)
        
        if len(found_vars) == len(required_vars):
            return True, found_vars
        else:
            missing = set(required_vars) - set(found_vars)
            return False, list(missing)
    
    except Exception as e:
        return False, [str(e)]


def check_logging_format(script_output: str) -> Tuple[bool, str]:
    """Validate logging format from inference.py output."""
    lines = script_output.strip().split("\n")
    
    # Check [START] line
    if not lines or not re.match(r"\[START\] task=\w+ env=[\w\-]+ model=[\w\.\-]+", lines[0]):
        return False, "Invalid or missing [START] line"
    
    # Check [STEP] lines
    step_pattern = r"\[STEP\] step=\d+ action=.+ reward=[\d\.\-]+ done=(true|false) error=(null|.+)"
    step_lines = [l for l in lines if l.startswith("[STEP]")]
    if not step_lines:
        return False, "No [STEP] lines found"
    
    for line in step_lines:
        if not re.match(step_pattern, line):
            return False, f"Invalid [STEP] format: {line}"
    
    # Check [END] line
    if not lines or not re.match(r"\[END\] success=(true|false) steps=\d+ rewards=[\d\.,\-]+", lines[-1]):
        return False, "Invalid or missing [END] line"
    
    return True, f"Valid: {len(step_lines)} steps logged correctly"


def check_grader_existence() -> Tuple[bool, List[str]]:
    """Check if graders.py exists and has all required grader classes."""
    try:
        with open("graders.py", "r") as f:
            content = f.read()
        
        required_classes = ["SteadyStateGrader", "PortStrikeGrader", "BlackSwanGrader"]
        found_classes = [cls for cls in required_classes if f"class {cls}" in content]
        
        if len(found_classes) == len(required_classes):
            return True, found_classes
        else:
            missing = set(required_classes) - set(found_classes)
            return False, list(missing)
    
    except Exception as e:
        return False, [str(e)]


def check_dockerfile() -> Tuple[bool, str]:
    """Check if Dockerfile exists and has key components."""
    try:
        with open("Dockerfile", "r") as f:
            content = f.read()
        
        required_keywords = ["FROM", "COPY", "RUN", "EXPOSE", "CMD"]
        missing = [kw for kw in required_keywords if kw not in content]
        
        if missing:
            return False, f"Missing keywords: {missing}"
        
        if "uvicorn" in content and "server:app" in content:
            return True, "Valid FastAPI Dockerfile"
        else:
            return False, "Missing uvicorn or server:app reference"
    
    except Exception as e:
        return False, str(e)


def check_models_pydantic() -> Tuple[bool, List[str]]:
    """Check if models.py has all required Pydantic models."""
    try:
        with open("models.py", "r") as f:
            content = f.read()
        
        required_models = ["Observation", "Action", "Reward", "StepResult"]
        found_models = [m for m in required_models if f"class {m}" in content]
        
        if len(found_models) == len(required_models):
            return True, found_models
        else:
            missing = set(required_models) - set(found_models)
            return False, list(missing)
    
    except Exception as e:
        return False, [str(e)]


def check_server_endpoints() -> Tuple[bool, List[str]]:
    """Check if server.py has all required endpoints."""
    try:
        with open("server.py", "r") as f:
            content = f.read()
        
        required_endpoints = ["/reset", "/step", "/state", "/grade"]
        found_endpoints = [ep for ep in required_endpoints if f'"{ep}"' in content or f"'{ep}'" in content]
        
        if len(found_endpoints) == len(required_endpoints):
            return True, found_endpoints
        else:
            missing = set(required_endpoints) - set(found_endpoints)
            return False, list(missing)
    
    except Exception as e:
        return False, [str(e)]


def main() -> int:
    """Run all validation checks."""
    print_header("META HACKATHON PHASE 1 VALIDATION")
    print(f"{BLUE}Supply Chain Chaos Environment{END}\n")
    
    checks_passed = 0
    checks_failed = 0
    warnings = 0
    
    # =========================================================================
    # 1. File existence checks
    # =========================================================================
    print_header("1. FILE STRUCTURE")
    
    required_files = [
        "inference.py",
        "server.py",
        "env.py",
        "models.py",
        "graders.py",
        "openenv.yaml",
        "Dockerfile",
        "requirements.txt",
        "README.md",
    ]
    
    for file in required_files:
        if check_file_exists(file):
            print_pass(f"File exists: {file}")
            checks_passed += 1
        else:
            print_fail(f"Missing required file: {file}")
            checks_failed += 1
    
    # =========================================================================
    # 2. Python syntax validation
    # =========================================================================
    print_header("2. PYTHON SYNTAX")
    
    python_files = ["inference.py", "server.py", "env.py", "models.py", "graders.py"]
    for file in python_files:
        if check_file_exists(file):
            is_valid, msg = check_python_syntax(file)
            if is_valid:
                print_pass(f"Valid syntax: {file}")
                checks_passed += 1
            else:
                print_fail(f"Syntax error in {file}: {msg}")
                checks_failed += 1
    
    # =========================================================================
    # 3. OpenEnv spec compliance
    # =========================================================================
    print_header("3. OPENENV SPEC COMPLIANCE")
    
    # Check openenv.yaml
    yaml_valid, yaml_info = check_openenv_yaml()
    if yaml_valid is None:
        print_warn(f"openenv.yaml validation skipped: {yaml_info.get('warning')}")
        warnings += 1
    elif yaml_valid:
        print_pass(f"openenv.yaml compliant: {yaml_info}")
        checks_passed += 1
    else:
        print_fail(f"openenv.yaml validation failed: {yaml_info}")
        checks_failed += 1
    
    # Check Pydantic models
    models_valid, models_found = check_models_pydantic()
    if models_valid:
        print_pass(f"Pydantic models found: {', '.join(models_found)}")
        checks_passed += 1
    else:
        print_fail(f"Missing models: {models_found}")
        checks_failed += 1
    
    # Check endpoints
    endpoints_valid, endpoints_found = check_server_endpoints()
    if endpoints_valid:
        print_pass(f"Server endpoints present: {', '.join(endpoints_found)}")
        checks_passed += 1
    else:
        print_fail(f"Missing endpoints: {endpoints_found}")
        checks_failed += 1
    
    # =========================================================================
    # 4. Task graders
    # =========================================================================
    print_header("4. TASK GRADERS (0.0-1.0 SCORES)")
    
    graders_valid, graders_found = check_grader_existence()
    if graders_valid:
        print_pass(f"Grader classes found: {', '.join(graders_found)}")
        checks_passed += 1
    else:
        print_fail(f"Missing grader classes: {graders_found}")
        checks_failed += 1
    
    # =========================================================================
    # 5. Environment variables
    # =========================================================================
    print_header("5. MANDATORY ENVIRONMENT VARIABLES")
    
    env_valid, env_vars = check_env_vars_in_inference()
    if env_valid:
        print_pass(f"All required env vars found: {', '.join(env_vars)}")
        checks_passed += 1
    else:
        print_fail(f"Missing env vars: {', '.join(env_vars)}")
        checks_failed += 1
    
    # =========================================================================
    # 6. Dockerfile
    # =========================================================================
    print_header("6. DOCKER DEPLOYMENT")
    
    docker_valid, docker_msg = check_dockerfile()
    if docker_valid:
        print_pass(f"Dockerfile valid: {docker_msg}")
        checks_passed += 1
    else:
        print_fail(f"Dockerfile issue: {docker_msg}")
        checks_failed += 1
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    print_header("VALIDATION SUMMARY")
    
    total = checks_passed + checks_failed
    print(f"Passed: {GREEN}{checks_passed}{END}/{total}")
    print(f"Failed: {RED}{checks_failed}{END}/{total}")
    if warnings > 0:
        print(f"Warnings: {YELLOW}{warnings}{END}")
    
    if checks_failed == 0:
        print(f"\n{GREEN}✅ Phase 1 Pre-Submission Checks PASSED{END}")
        print(f"{BLUE}Your project is ready for Meta's automated validator.{END}\n")
        return 0
    else:
        print(f"\n{RED}❌ Phase 1 Checks FAILED{END}")
        print(f"{YELLOW}Fix the above issues before submitting.{END}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())

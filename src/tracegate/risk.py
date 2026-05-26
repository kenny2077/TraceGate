import re
from typing import Dict, Any, List
from pydantic import BaseModel

class RiskClassification(BaseModel):
    level: str  # "low", "medium", "high", "critical"
    tags: List[str]

class RiskClassifier:
    def __init__(self):
        # Destructive or risky shell commands
        self.risky_commands = [
            re.compile(r'\brm\s+-r', re.IGNORECASE),
            re.compile(r'\bsudo\b', re.IGNORECASE),
            re.compile(r'curl\s+.*?\|\s*bash', re.IGNORECASE),
            re.compile(r'wget\s+.*?\|\s*bash', re.IGNORECASE),
            re.compile(r'\bmv\s+.*?\s+/dev/null', re.IGNORECASE),
            re.compile(r'\bdd\s+if=', re.IGNORECASE),
            re.compile(r'\beval\b', re.IGNORECASE),
            re.compile(r'\bexec\b', re.IGNORECASE),
        ]
        
        self.privilege_escalation = [
            re.compile(r'\bchmod\s+777\b', re.IGNORECASE),
            re.compile(r'\bchown\b', re.IGNORECASE),
        ]
        
        self.process_manipulation = [
            re.compile(r'\bkill\b', re.IGNORECASE),
            re.compile(r'\bpkill\b', re.IGNORECASE),
        ]
        
        self.git_operations = [
            re.compile(r'\bgit\s+push\s+--force\b', re.IGNORECASE),
            re.compile(r'\bgit\s+reset\s+--hard\b', re.IGNORECASE),
            re.compile(r'\bgit\s+branch\s+-D\b', re.IGNORECASE),
            re.compile(r'\bgit\s+rebase\b', re.IGNORECASE),
        ]
        
        self.package_installs = [
            re.compile(r'\bpip\s+install\b', re.IGNORECASE),
            re.compile(r'\bnpm\s+install\b', re.IGNORECASE),
            re.compile(r'\bcargo\s+install\b', re.IGNORECASE),
            re.compile(r'\bbrew\s+install\b', re.IGNORECASE),
        ]
        
        # Risky file paths
        self.risky_paths = [
            re.compile(r'(?:^|/)\.env(?:$|/)', re.IGNORECASE),
            re.compile(r'(?:^|/)\.ssh/', re.IGNORECASE),
            re.compile(r'(?:^|/)\.aws/', re.IGNORECASE),
            re.compile(r'(?:^|/)\.kube/', re.IGNORECASE),
            re.compile(r'id_rsa', re.IGNORECASE),
            re.compile(r'(?:^|/)\.git/credentials', re.IGNORECASE),
        ]

    def classify(self, tool_name: str, arguments: Dict[str, Any]) -> RiskClassification:
        tags = []
        
        # Collect all string arguments
        all_strings = []
        for v in arguments.values():
            if isinstance(v, str):
                all_strings.append(v)
            elif isinstance(v, list):
                all_strings.extend([str(item) for item in v if isinstance(item, str)])

        # Check command risk across all strings
        for s in all_strings:
            if any(p.search(s) for p in self.risky_commands):
                tags.append("destructive_command")
            if any(p.search(s) for p in self.privilege_escalation):
                tags.append("privilege_escalation")
            if any(p.search(s) for p in self.process_manipulation):
                tags.append("process_manipulation")
            if any(p.search(s) for p in self.git_operations):
                tags.append("risky_git_operation")
            if any(p.search(s) for p in self.package_installs):
                tags.append("package_install")
                
        # Check file path risk across specific path keys and all strings (fallback)
        for key in ["path", "file", "filename", "dir", "directory"]:
            if key in arguments:
                path = str(arguments[key])
                if any(p.search(path) for p in self.risky_paths):
                    tags.append("sensitive_path")
        
        # Also check all strings for sensitive paths just in case
        for s in all_strings:
            if any(p.search(s) for p in self.risky_paths) and "sensitive_path" not in tags:
                tags.append("sensitive_path")
                    
        # Check network risk
        if tool_name in ["fetch", "curl", "wget", "request", "http_request"]:
            tags.append("network")
            
        tags = list(set(tags)) # Deduplicate tags

        # Determine level
        level = "low"
        if "destructive_command" in tags or "sensitive_path" in tags or "privilege_escalation" in tags:
            level = "high"
        elif "process_manipulation" in tags or "risky_git_operation" in tags or "package_install" in tags:
            level = "medium"
        elif "network" in tags:
            level = "medium"
            
        # Escalate to critical if multiple high/medium risk categories are present
        if level == "high" and len(tags) >= 2:
             level = "critical"
        
        if not tags:
            tags.append("safe")
            
        return RiskClassification(level=level, tags=tags)

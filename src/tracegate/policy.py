import yaml
import fnmatch
from enum import Enum
from typing import Dict, Any, List, Optional, DefaultDict
from pydantic import BaseModel, Field, ConfigDict, ValidationError
import collections

class SessionState:
    def __init__(self):
        # Maps rule_id -> count of times it has matched
        self.rule_match_counts: DefaultDict[str, int] = collections.defaultdict(int)
        
    def increment_rule(self, rule_id: str):
        self.rule_match_counts[rule_id] += 1
        
    def get_rule_count(self, rule_id: str) -> int:
        return self.rule_match_counts[rule_id]

class RuleAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"

class PolicyRule(BaseModel):
    id: str
    tool: str
    match_args: Optional[Dict[str, str]] = None
    match_args_contain: Optional[Dict[str, List[str]]] = None
    action: RuleAction
    message: Optional[str] = None
    risk: Optional[str] = None
    tags: Optional[List[str]] = None
    max_calls_per_session: Optional[int] = None

class PolicyConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    version: int
    default_action: RuleAction = Field(default=RuleAction.ASK, alias="defaultAction")
    dlp_enabled: bool = Field(default=True, alias="dlpEnabled")
    max_bytes_returned: Optional[int] = Field(default=None, alias="maxBytesReturned")
    rules: List[PolicyRule] = Field(default_factory=list)

class PolicyVerdict(BaseModel):
    action: RuleAction
    rule_id: Optional[str]
    message: str

class PolicyEngine:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> PolicyConfig:
        try:
            with open(self.config_path, "r") as f:
                data = yaml.safe_load(f)
            
            if not data:
                raise ValueError("Policy file is empty")
                
            return PolicyConfig(**data)
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse policy YAML: {e}")
        except ValidationError as e:
            raise ValueError(f"Policy schema validation failed: {e}")
        except Exception as e:
            raise ValueError(f"Failed to load policy: {e}")

    def reload(self):
        self.config = self._load_config()

    def evaluate(self, tool_name: str, arguments: Dict[str, Any], session_state: Optional[SessionState] = None) -> PolicyVerdict:
        """
        Evaluate a tool call against the loaded policy rules.
        First matching rule wins.
        """
        for rule in self.config.rules:
            if self._matches_rule(rule, tool_name, arguments):
                # Check stateful constraints
                if rule.max_calls_per_session is not None and session_state is not None:
                    count = session_state.get_rule_count(rule.id)
                    if count >= rule.max_calls_per_session:
                        # Rule limit exceeded, block it
                        return PolicyVerdict(
                            action=RuleAction.DENY,
                            rule_id=rule.id,
                            message=f"Rule {rule.id} rate limit exceeded (max {rule.max_calls_per_session} calls per session)"
                        )
                
                # Rule matches and constraints pass
                if session_state is not None:
                    session_state.increment_rule(rule.id)
                    
                return PolicyVerdict(
                    action=rule.action,
                    rule_id=rule.id,
                    message=rule.message or f"Matched rule {rule.id}"
                )
        
        # Default action
        return PolicyVerdict(
            action=self.config.default_action,
            rule_id=None,
            message="No matching rule found. Falling back to default action."
        )

    def _matches_rule(self, rule: PolicyRule, tool_name: str, arguments: Dict[str, Any]) -> bool:
        # Match tool name (supports fnmatch globs like 'git_*')
        if not fnmatch.fnmatch(tool_name, rule.tool):
            return False
            
        # Match arguments if specified (glob)
        if rule.match_args:
            for key, pattern in rule.match_args.items():
                if key not in arguments:
                    return False
                val = str(arguments[key])
                if not fnmatch.fnmatch(val, pattern):
                    return False
                    
        # Match arguments contain if specified (substring)
        if rule.match_args_contain:
            for key, substrings in rule.match_args_contain.items():
                if key not in arguments:
                    return False
                val = str(arguments[key])
                if not any(sub in val for sub in substrings):
                    return False
                    
        return True

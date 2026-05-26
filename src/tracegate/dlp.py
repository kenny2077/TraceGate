import re
import json
from typing import Any

# Regexes to catch common secrets in string payloads
SECRET_PATTERNS = [
    # AWS Keys
    (re.compile(r'(?i)(?:aws)?[_ -]?(?:access)?[_ -]?key[_ -]?(?:id)?[\s:=]+([A-Z0-9]{20})'), r'\1'),
    (re.compile(r'(?i)(?:aws)?[_ -]?(?:secret)?[_ -]?(?:access)?[_ -]?key[\s:=]+([a-zA-Z0-9/+=]{40})'), r'\1'),
    
    # Generic bearer tokens/API keys
    (re.compile(r'(?i)(?:api_key|apikey|bearer_?token|auth_?token|secret|token)[\s:=]+([a-zA-Z0-9_\-\.]{16,})'), r'\1'),
    
    # Private Keys (RSA, ED25519)
    (re.compile(r'-----BEGIN [A-Z ]+PRIVATE KEY-----.+?-----END [A-Z ]+PRIVATE KEY-----', re.DOTALL), r'-----BEGIN [A-Z ]+PRIVATE KEY-----.+?-----END [A-Z ]+PRIVATE KEY-----')
]

# Keys in JSON objects to aggressively redact entirely
SENSITIVE_KEYS = [
    re.compile(r'password', re.IGNORECASE),
    re.compile(r'secret', re.IGNORECASE),
    re.compile(r'token', re.IGNORECASE),
    re.compile(r'api[_-]?key', re.IGNORECASE),
    re.compile(r'auth', re.IGNORECASE),
    re.compile(r'credential', re.IGNORECASE),
    re.compile(r'private[_-]?key', re.IGNORECASE),
]

class RedactionEngine:
    """
    Scans data structures and strings for sensitive patterns and replaces them with [REDACTED].
    """
    
    def redact(self, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: self._redact_dict_value(k, v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.redact(item) for item in data]
        elif isinstance(data, str):
            return self._redact_string(data)
        return data

    def _redact_dict_value(self, key: str, value: Any) -> Any:
        # If the key itself looks like a secret, redact the entire value unconditionally
        if any(p.search(key) for p in SENSITIVE_KEYS):
            # If the value is a complex object, we can just replace it entirely with [REDACTED]
            return "[REDACTED]"
            
        # Otherwise, recurse to find secrets inside strings
        return self.redact(value)
        
    def _redact_string(self, text: str) -> str:
        redacted_text = text
        for pattern, group in SECRET_PATTERNS:
            # We use a callable replacer to only replace the captured group if specified,
            # but for simplicity, if we match the pattern, we replace the captured group with [REDACTED].
            # This requires custom sub logic.
            for match in pattern.finditer(redacted_text):
                if match.groups():
                    # Replace just the captured secret group
                    secret = match.group(1)
                    if secret:
                        redacted_text = redacted_text.replace(secret, "[REDACTED]")
                else:
                    # Replace the entire match (e.g. for private keys)
                    redacted_text = redacted_text.replace(match.group(0), "[REDACTED]")
        return redacted_text

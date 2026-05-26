import pytest
from tracegate.dlp import RedactionEngine

def test_redact_aws_keys():
    engine = RedactionEngine()
    
    # Test Access Key ID
    payload = "Here is my AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE for you."
    redacted = engine.redact(payload)
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted
    assert "Here is my AWS_ACCESS_KEY_ID=[REDACTED] for you." in redacted
    
    # Test Secret Access Key
    payload2 = "aws_secret_access_key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    redacted2 = engine.redact(payload2)
    assert "wJalrXUtnFEMI" not in redacted2
    assert "aws_secret_access_key: [REDACTED]" in redacted2

def test_redact_generic_tokens():
    engine = RedactionEngine()
    
    payload = "BearerToken: abcdefg1234567890_.-"
    redacted = engine.redact(payload)
    assert "abcdefg" not in redacted
    assert "[REDACTED]" in redacted

def test_redact_private_keys():
    engine = RedactionEngine()
    
    payload = """
    Some text before.
    -----BEGIN RSA PRIVATE KEY-----
    MIIEpAIBAAKCAQEA3...
    ...more base64...
    -----END RSA PRIVATE KEY-----
    Some text after.
    """
    redacted = engine.redact(payload)
    assert "MIIEpAIBAAKCAQEA3" not in redacted
    assert "Some text before." in redacted
    assert "Some text after." in redacted
    assert "[REDACTED]" in redacted

def test_redact_json_objects():
    engine = RedactionEngine()
    
    data = {
        "status": "success",
        "api_key": "sk-1234567890abcdef", # Key match
        "message": "Here is a token: AKIAIOSFODNN7EXAMPLE" # Value match
    }
    
    redacted = engine.redact(data)
    
    assert redacted["status"] == "success"
    assert redacted["api_key"] == "[REDACTED]" # Aggressively redacted by key name
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted["message"]
    assert "[REDACTED]" in redacted["message"]

def test_redact_lists():
    engine = RedactionEngine()
    data = [
        "Normal string",
        "aws_access_key_id: AKIAIOSFODNN7EXAMPLE",
        {"password": "my_super_secret_password"}
    ]
    
    redacted = engine.redact(data)
    assert redacted[0] == "Normal string"
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted[1]
    assert redacted[2]["password"] == "[REDACTED]"

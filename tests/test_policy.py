import pytest
import os
from tracegate.policy import PolicyEngine, RuleAction

def test_policy_engine(tmp_path):
    policy_content = """
version: 1
defaultAction: ask
rules:
  - id: allow-safe-fetch
    tool: fetch
    match_args:
      url: "https://api.github.com/*"
    action: allow
    message: "Safe github fetch"
    risk: low
    tags: ["network"]
  - id: deny-rm
    tool: execute_command
    match_args_contain:
      command: ["rm -rf"]
    action: deny
  - id: allow-all-ls
    tool: list_dir
    action: allow
  - id: complex-match
    tool: complex_tool
    match_args:
      target: "*.txt"
    match_args_contain:
      flag: ["--force", "--all"]
    action: deny
"""
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(policy_content)
    
    engine = PolicyEngine(str(policy_path))
    
    # Test match args specific allow
    v1 = engine.evaluate("fetch", {"url": "https://api.github.com/repos/foo/bar"})
    assert v1.action == RuleAction.ALLOW
    assert v1.rule_id == "allow-safe-fetch"
    
    # Test arg mismatch falls through to default
    v2 = engine.evaluate("fetch", {"url": "https://evil.com/"})
    assert v2.action == RuleAction.ASK
    assert v2.rule_id is None
    
    # Test match_args_contain deny rule
    v3 = engine.evaluate("execute_command", {"command": "cd /tmp && rm -rf build"})
    assert v3.action == RuleAction.DENY
    assert v3.rule_id == "deny-rm"
    
    # Test tool only match
    v4 = engine.evaluate("list_dir", {"path": "/tmp"})
    assert v4.action == RuleAction.ALLOW
    assert v4.rule_id == "allow-all-ls"

    # Test combined match_args and match_args_contain
    v5 = engine.evaluate("complex_tool", {"target": "data.txt", "flag": "use --force here"})
    assert v5.action == RuleAction.DENY
    assert v5.rule_id == "complex-match"

    v6 = engine.evaluate("complex_tool", {"target": "data.csv", "flag": "use --force here"})
    assert v6.action == RuleAction.ASK # match_args fails

    v7 = engine.evaluate("complex_tool", {"target": "data.txt", "flag": "use --safe here"})
    assert v7.action == RuleAction.ASK # match_args_contain fails


def test_empty_rules(tmp_path):
    policy_content = """
version: 1
defaultAction: deny
rules: []
"""
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(policy_content)
    
    engine = PolicyEngine(str(policy_path))
    v = engine.evaluate("any_tool", {})
    assert v.action == RuleAction.DENY


def test_malformed_yaml(tmp_path):
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text("this is not: [ valid yaml")
    
    with pytest.raises(ValueError, match="Failed to parse policy YAML"):
        PolicyEngine(str(policy_path))


def test_missing_required_fields(tmp_path):
    policy_content = """
version: 1
defaultAction: ask
rules:
  - tool: fetch # missing id and action
"""
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(policy_content)
    
    with pytest.raises(ValueError, match="Policy schema validation failed"):
        PolicyEngine(str(policy_path))

def test_empty_yaml(tmp_path):
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text("")
    
    with pytest.raises(ValueError, match="Policy file is empty"):
        PolicyEngine(str(policy_path))

def test_stateful_rules(tmp_path):
    from tracegate.policy import SessionState
    policy_content = """
version: 1
defaultAction: ask
rules:
  - id: limit-read
    tool: read_file
    action: allow
    max_calls_per_session: 2
"""
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(policy_content)
    
    engine = PolicyEngine(str(policy_path))
    session = SessionState()
    
    # 1st call - should allow and increment count
    v1 = engine.evaluate("read_file", {}, session)
    assert v1.action == RuleAction.ALLOW
    assert session.get_rule_count("limit-read") == 1
    
    # 2nd call - should allow and increment count
    v2 = engine.evaluate("read_file", {}, session)
    assert v2.action == RuleAction.ALLOW
    assert session.get_rule_count("limit-read") == 2
    
    # 3rd call - should DENY due to rate limit
    v3 = engine.evaluate("read_file", {}, session)
    assert v3.action == RuleAction.DENY
    assert "rate limit exceeded" in v3.message
    # Count should not increment on blocked call
    assert session.get_rule_count("limit-read") == 2

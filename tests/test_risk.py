import pytest
from tracegate.risk import RiskClassifier

def test_risk_classifier():
    classifier = RiskClassifier()
    
    # Test safe command
    res1 = classifier.classify("execute_command", {"command": "ls -la"})
    assert res1.level == "low"
    assert "safe" in res1.tags
    
    # Test destructive command
    res2 = classifier.classify("execute_command", {"command": "rm -rf /tmp/foo"})
    assert res2.level == "high"
    assert "destructive_command" in res2.tags
    
    # Test sensitive path
    res3 = classifier.classify("read_file", {"path": "/home/user/.ssh/id_rsa"})
    assert res3.level == "high"
    assert "sensitive_path" in res3.tags
    
    # Test network tool
    res4 = classifier.classify("fetch", {"url": "https://google.com"})
    assert res4.level == "medium"
    assert "network" in res4.tags

def test_git_operations():
    classifier = RiskClassifier()
    res = classifier.classify("execute_command", {"command": "git push --force origin main"})
    assert "risky_git_operation" in res.tags
    assert res.level == "medium"

def test_package_installs():
    classifier = RiskClassifier()
    res = classifier.classify("execute_command", {"command": "npm install -g evil-package"})
    assert "package_install" in res.tags
    assert res.level == "medium"

def test_privilege_escalation():
    classifier = RiskClassifier()
    res = classifier.classify("execute_command", {"command": "chmod 777 /etc/passwd"})
    assert "privilege_escalation" in res.tags
    assert res.level == "high"

def test_process_manipulation():
    classifier = RiskClassifier()
    res = classifier.classify("execute_command", {"command": "kill -9 1234"})
    assert "process_manipulation" in res.tags
    assert res.level == "medium"

def test_compound_risk_escalation():
    classifier = RiskClassifier()
    # Destructive command + sensitive path
    res = classifier.classify("execute_command", {"command": "rm -r /home/user/.aws/"})
    assert "destructive_command" in res.tags
    assert "sensitive_path" in res.tags
    assert res.level == "critical"

    # Two medium risks (e.g., git and package install) doesn't escalate to critical, 
    # but let's check high + medium
    res2 = classifier.classify("execute_command", {"command": "sudo npm install -g evil"})
    assert "destructive_command" in res2.tags # sudo is considered destructive_command
    assert "package_install" in res2.tags
    assert res2.level == "critical"

def test_false_positive_env():
    classifier = RiskClassifier()
    # Should not flag .environment as .env
    res = classifier.classify("read_file", {"path": "/project/.environment"})
    assert "sensitive_path" not in res.tags
    
    # Should flag actual .env
    res2 = classifier.classify("read_file", {"path": "/project/.env"})
    assert "sensitive_path" in res2.tags

def test_scan_all_strings():
    classifier = RiskClassifier()
    # Command hidden in non-standard argument key
    res = classifier.classify("custom_tool", {"arg1": "safe", "arg2": "sudo rm -r /"})
    assert "destructive_command" in res.tags
    assert res.level == "high"

def test_empty_arguments():
    classifier = RiskClassifier()
    res = classifier.classify("list_dir", {})
    assert "safe" in res.tags
    assert res.level == "low"

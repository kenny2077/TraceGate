from typer.testing import CliRunner
from tracegate.cli import app
import os

runner = CliRunner()


def test_app_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "TraceGate" in result.stdout
    assert "proxy" in result.stdout
    assert "replay" in result.stdout
    assert "check-policy" in result.stdout
    assert "sessions" in result.stdout


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "tracegate" in result.stdout


def test_proxy_no_command():
    """proxy with no server command should fail gracefully."""
    result = runner.invoke(app, ["proxy"])
    assert result.exit_code == 1
    assert "No server command" in result.stderr or "No server command" in result.stdout


def test_check_policy_valid(tmp_path):
    policy = tmp_path / "policy.yaml"
    policy.write_text("""
version: 1
defaultAction: allow
rules:
  - id: test-rule
    tool: "*"
    action: allow
""")
    result = runner.invoke(app, ["check-policy", str(policy)])
    assert result.exit_code == 0
    assert "valid" in result.stdout.lower() or "✅" in result.stdout


def test_check_policy_invalid(tmp_path):
    policy = tmp_path / "bad.yaml"
    policy.write_text("this is not valid yaml: [[[")
    result = runner.invoke(app, ["check-policy", str(policy)])
    assert result.exit_code == 1


def test_sessions_empty(tmp_path):
    """Sessions command with empty directory should not crash."""
    result = runner.invoke(app, ["sessions", "--log-dir", str(tmp_path)])
    assert result.exit_code == 0


def test_sessions_nonexistent_dir():
    result = runner.invoke(app, ["sessions", "--log-dir", "/nonexistent/dir"])
    assert result.exit_code == 0
    assert "No sessions" in result.stdout

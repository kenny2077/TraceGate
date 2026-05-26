import json
import os
from pathlib import Path
from unittest.mock import patch
from tracegate.installer import Installer

def test_install_injects_tracegate(tmp_path):
    config_file = tmp_path / "claude_desktop_config.json"
    config_data = {
        "mcpServers": {
            "sqlite": {
                "command": "uvx",
                "args": ["mcp-server-sqlite", "--db-path", "~/test.db"]
            }
        }
    }
    with open(config_file, "w") as f:
        json.dump(config_data, f)
        
    installer = Installer()
    msg = installer._inject_config(config_file, "TestAgent")
    
    assert "✅" in msg
    assert os.path.exists(str(config_file) + ".tg.bak")
    
    with open(config_file, "r") as f:
        new_config = json.load(f)
        
    server = new_config["mcpServers"]["sqlite"]
    assert server["command"] == "tracegate"
    assert server["args"] == ["proxy", "--", "uvx", "mcp-server-sqlite", "--db-path", "~/test.db"]

def test_install_injects_with_policy(tmp_path):
    config_file = tmp_path / "claude_desktop_config.json"
    config_data = {
        "mcpServers": {
            "sqlite": {
                "command": "uvx",
                "args": ["mcp-server-sqlite"]
            }
        }
    }
    with open(config_file, "w") as f:
        json.dump(config_data, f)
        
    installer = Installer(policy_path="/tmp/my_policy.yaml")
    installer._inject_config(config_file, "TestAgent")
    
    with open(config_file, "r") as f:
        new_config = json.load(f)
        
    server = new_config["mcpServers"]["sqlite"]
    assert server["command"] == "tracegate"
    assert server["args"] == ["proxy", "--policy", "/tmp/my_policy.yaml", "--", "uvx", "mcp-server-sqlite"]

def test_install_skips_already_wrapped(tmp_path):
    config_file = tmp_path / "claude_desktop_config.json"
    config_data = {
        "mcpServers": {
            "sqlite": {
                "command": "tracegate",
                "args": ["proxy", "--", "uvx", "mcp-server-sqlite"]
            }
        }
    }
    with open(config_file, "w") as f:
        json.dump(config_data, f)
        
    installer = Installer()
    msg = installer._inject_config(config_file, "TestAgent")
    
    assert "No servers needed modification" in msg

def test_uninstall_reverts_tracegate(tmp_path):
    config_file = tmp_path / "claude_desktop_config.json"
    config_data = {
        "mcpServers": {
            "sqlite": {
                "command": "tracegate",
                "args": ["proxy", "--", "uvx", "mcp-server-sqlite", "--db-path", "~/test.db"]
            }
        }
    }
    with open(config_file, "w") as f:
        json.dump(config_data, f)
        
    installer = Installer()
    msg = installer._revert_config(config_file, "TestAgent")
    
    assert "✅" in msg
    assert os.path.exists(str(config_file) + ".tg.pre-uninstall.bak")
    
    with open(config_file, "r") as f:
        new_config = json.load(f)
        
    server = new_config["mcpServers"]["sqlite"]
    assert server["command"] == "uvx"
    assert server["args"] == ["mcp-server-sqlite", "--db-path", "~/test.db"]

def test_uninstall_with_policy(tmp_path):
    config_file = tmp_path / "claude_desktop_config.json"
    config_data = {
        "mcpServers": {
            "sqlite": {
                "command": "tracegate",
                "args": ["proxy", "--policy", "/tmp/my_policy.yaml", "--", "uvx", "mcp-server-sqlite"]
            }
        }
    }
    with open(config_file, "w") as f:
        json.dump(config_data, f)
        
    installer = Installer()
    installer._revert_config(config_file, "TestAgent")
    
    with open(config_file, "r") as f:
        new_config = json.load(f)
        
    server = new_config["mcpServers"]["sqlite"]
    assert server["command"] == "uvx"
    assert server["args"] == ["mcp-server-sqlite"]

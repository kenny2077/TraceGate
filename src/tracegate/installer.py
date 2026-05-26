import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Standard locations for Agent MCP configs
def get_claude_desktop_config_path() -> Optional[Path]:
    if sys.platform == "darwin":
        path = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            path = Path(appdata) / "Claude/claude_desktop_config.json"
        else:
            return None
    else:
        path = Path.home() / ".config/Claude/claude_desktop_config.json"
        
    return path if path.exists() else None

def get_cursor_config_path() -> Optional[Path]:
    # Try looking in the current working directory first
    local_path = Path(".cursor/mcp.json")
    if local_path.exists():
        return local_path
    
    # Try looking in the global user directory
    global_path = Path.home() / ".cursor/mcp.json"
    return global_path if global_path.exists() else None

class Installer:
    def __init__(self, policy_path: Optional[str] = None):
        self.policy_path = policy_path

    def install(self) -> List[str]:
        """Scans for configs, injects TraceGate, and returns messages."""
        messages = []
        
        paths_to_check = {
            "Claude Desktop": get_claude_desktop_config_path(),
            "Cursor": get_cursor_config_path()
        }
        
        found_any = False
        for name, path in paths_to_check.items():
            if path:
                found_any = True
                msg = self._inject_config(path, name)
                messages.append(msg)
                
        if not found_any:
            messages.append("No supported agent configurations found automatically.")
            messages.append("You may need to manually wrap your MCP server commands with 'tracegate proxy -- <command>'.")
            
        return messages

    def uninstall(self) -> List[str]:
        """Scans for configs, removes TraceGate injection, and returns messages."""
        messages = []
        
        paths_to_check = {
            "Claude Desktop": get_claude_desktop_config_path(),
            "Cursor": get_cursor_config_path()
        }
        
        found_any = False
        for name, path in paths_to_check.items():
            if path:
                found_any = True
                msg = self._revert_config(path, name)
                messages.append(msg)
                
        if not found_any:
            messages.append("No supported agent configurations found.")
            
        return messages

    def _inject_config(self, path: Path, agent_name: str) -> str:
        try:
            with open(path, "r") as f:
                config = json.load(f)
                
            mcp_servers = config.get("mcpServers", {})
            if not mcp_servers:
                return f"[{agent_name}] Config found at {path}, but no 'mcpServers' defined."
                
            # Create a backup
            backup_path = str(path) + ".tg.bak"
            shutil.copy2(path, backup_path)
            
            modified_count = 0
            for server_name, server_config in mcp_servers.items():
                cmd = server_config.get("command")
                
                # Check if already wrapped
                if cmd == "tracegate" or (cmd and cmd.endswith("tracegate")):
                    continue
                    
                if not cmd:
                    continue # Not a stdio server
                    
                original_args = server_config.get("args", [])
                
                # Construct new arguments
                new_args = ["proxy"]
                if self.policy_path:
                    new_args.extend(["--policy", self.policy_path])
                new_args.append("--")
                new_args.append(cmd)
                new_args.extend(original_args)
                
                # Update config
                server_config["command"] = "tracegate"
                server_config["args"] = new_args
                modified_count += 1
                
            if modified_count > 0:
                with open(path, "w") as f:
                    json.dump(config, f, indent=2)
                return f"✅ [{agent_name}] Injected TraceGate into {modified_count} server(s). Backup saved to {backup_path}"
            else:
                return f"[{agent_name}] No servers needed modification (perhaps already wrapped?)."
                
        except Exception as e:
            return f"❌ [{agent_name}] Failed to modify config: {e}"

    def _revert_config(self, path: Path, agent_name: str) -> str:
        try:
            with open(path, "r") as f:
                config = json.load(f)
                
            mcp_servers = config.get("mcpServers", {})
            if not mcp_servers:
                return f"[{agent_name}] Config found, but no 'mcpServers' defined."
                
            modified_count = 0
            for server_name, server_config in mcp_servers.items():
                cmd = server_config.get("command")
                
                # Check if wrapped by TraceGate
                if cmd == "tracegate" or (cmd and cmd.endswith("tracegate")):
                    args = server_config.get("args", [])
                    
                    # Find the '--' separator
                    try:
                        sep_idx = args.index("--")
                        if sep_idx + 1 < len(args):
                            original_cmd = args[sep_idx + 1]
                            original_args = args[sep_idx + 2:]
                            
                            server_config["command"] = original_cmd
                            server_config["args"] = original_args
                            modified_count += 1
                    except ValueError:
                        pass # Malformed tracegate wrapper, skip
                        
            if modified_count > 0:
                # Create a pre-uninstall backup just in case
                backup_path = str(path) + ".tg.pre-uninstall.bak"
                shutil.copy2(path, backup_path)
                
                with open(path, "w") as f:
                    json.dump(config, f, indent=2)
                return f"✅ [{agent_name}] Removed TraceGate from {modified_count} server(s)."
            else:
                return f"[{agent_name}] No TraceGate wrapped servers found."
                
        except Exception as e:
            return f"❌ [{agent_name}] Failed to revert config: {e}"

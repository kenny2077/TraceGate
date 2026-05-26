#!/usr/bin/env python3
import sys
import json
import asyncio
import os
import tempfile
import time

def run_server():
    """
    A dummy MCP server that blindly executes whatever it's told,
    and happily returns secrets if asked.
    """
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        
        try:
            req = json.loads(line)
        except:
            continue
            
        if req.get("method") == "initialize":
            res = {"jsonrpc": "2.0", "id": req.get("id"), "result": {"serverInfo": {"name": "dummy", "version": "1.0"}}}
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()
            
        elif req.get("method") == "tools/call":
            tool = req.get("params", {}).get("name")
            args = req.get("params", {}).get("arguments", {})
            call_id = req.get("id")
            
            if tool == "execute_command" and "rm -rf" in args.get("command", ""):
                # Malicious command executed!
                res = {"jsonrpc": "2.0", "id": call_id, "result": {"content": "Deleted everything!"}}
            elif tool == "read_file" and ".env" in args.get("path", ""):
                # Leaking a secret!
                res = {"jsonrpc": "2.0", "id": call_id, "result": "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\nDB_PASS=supersecret"}
            else:
                # Normal command
                res = {"jsonrpc": "2.0", "id": call_id, "result": "Safe execution successful."}
                
            # Simulate processing time
            time.sleep(0.5)
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()

async def run_agent():
    """
    Simulates an AI Agent making JSON-RPC calls to TraceGate.
    """
    print("\n\033[1;36m[Demo] TraceGate Interactive Simulation\033[0m")
    print("This demo simulates an AI Agent communicating with a dummy MCP server.")
    print("TraceGate is sitting in the middle, intercepting the traffic.\n")

    # 1. Create a dummy policy
    policy_yaml = """
version: 1
defaultAction: ask
dlpEnabled: true
rules:
  - id: block-rm
    tool: execute_command
    match_args_contain:
      command: ["rm -rf"]
    action: deny
    message: "Destructive command blocked"
    risk: critical
  - id: allow-readme
    tool: read_file
    match_args:
      path: "README.md"
    action: allow
    message: "Safe read"
  - id: read-env
    tool: read_file
    match_args:
      path: "*.env"
    action: allow
    message: "Allowed, but DLP will redact it"
"""
    fd, policy_path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, 'w') as f:
        f.write(policy_yaml)

    # 2. Spawn TraceGate Proxy wrapping our dummy server
    print(f"\033[1;33m[1] Booting TraceGate with strict policy...\033[0m")
    
    # We use the python executable to run this script in server mode
    tracegate_cmd = [
        "tracegate", "proxy", 
        "--policy", policy_path,
        "--",
        sys.executable, __file__, "--server"
    ]
    
    process = await asyncio.create_subprocess_exec(
        *tracegate_cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    async def read_stderr():
        while True:
            line = await process.stderr.readline()
            if not line:
                break
            # Print TraceGate logs in gray
            print(f"\033[90mTraceGate: {line.decode().strip()}\033[0m")

    asyncio.create_task(read_stderr())

    def send_req(req_id, method, params=None):
        req = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params:
            req["params"] = params
        process.stdin.write((json.dumps(req) + "\n").encode())
        
    async def read_res():
        line = await process.stdout.readline()
        if line:
            return json.loads(line.decode())
        return None

    # Initialize
    send_req(1, "initialize")
    await read_res()

    # --- Scenario 1: Safe Tool Call ---
    print("\n\033[1;34m[Scenario 1: Safe Operation]\033[0m")
    print("Agent:   \033[1;37mRunning `read_file` on 'README.md'\033[0m")
    send_req(2, "tools/call", {"name": "read_file", "arguments": {"path": "README.md"}})
    res = await read_res()
    print(f"Server:  \033[1;32m{res.get('result')}\033[0m")

    # --- Scenario 2: Malicious Tool Call ---
    print("\n\033[1;34m[Scenario 2: Malicious Operation]\033[0m")
    print("Agent:   \033[1;37mRunning `execute_command` with 'rm -rf /'\033[0m")
    send_req(3, "tools/call", {"name": "execute_command", "arguments": {"command": "rm -rf /"}})
    res = await read_res()
    # TraceGate should have intercepted and returned an error
    error = res.get("error", {}).get("message", "")
    print(f"Proxy:   \033[1;31mBLOCKED! {error}\033[0m")

    # --- Scenario 3: Data Exfiltration ---
    print("\n\033[1;34m[Scenario 3: Data Exfiltration (DLP)]\033[0m")
    print("Agent:   \033[1;37mRunning `read_file` on '.env'\033[0m")
    print("Note:    \033[90mPolicy allows this, but DLP engine is active\033[0m")
    send_req(4, "tools/call", {"name": "read_file", "arguments": {"path": ".env"}})
    res = await read_res()
    # The server returned secrets, but TraceGate redacted them
    result = res.get("result", "")
    print(f"Proxy:   \033[1;32m{result}\033[0m")
    
    print("\n\033[1;36m[Demo Complete]\033[0m")
    
    # Cleanup
    process.terminate()
    os.remove(policy_path)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--server":
        run_server()
    else:
        asyncio.run(run_agent())

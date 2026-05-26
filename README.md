<div align="center">
  <h1>🛡️ TraceGate</h1>
  <p><strong>The Runtime Firewall for AI Coding Agents.</strong></p>
  <p><em>Wireshark meets fail2ban for the Model Context Protocol (MCP).</em></p>
</div>

---

TraceGate sits seamlessly between an AI coding agent (like Claude Code, Cursor, or any MCP client) and the local tools it executes. 

It intercepts JSON-RPC tool calls, evaluates heuristic risk, enforces stateful YAML policies, provides Data Loss Prevention (DLP), asks for your human approval when needed, and produces a replayable timeline of everything the agent did.

## ✨ Why TraceGate?

AI Agents are powerful, but giving them raw execution access to your file system is terrifying. TraceGate gives you back your peace of mind with **Zero-Trust Observability**:

- **Zero-Friction Proxy**: Transparently proxies MCP stdio and SSE traffic with zero overhead for allowed calls.
- **Risk Classification Engine**: Automatically flags destructive commands (`rm -rf`, `git push --force`), privilege escalation (`sudo`, `chmod`), and sensitive paths (`.env`, `.aws/`).
- **Data Loss Prevention (DLP)**: Surgical in-flight redaction. If an agent runs `cat .env`, TraceGate intercepts the server's response and redacts AWS Keys, passwords, and tokens *before* the agent ever receives them.
- **Stateful Policy Engine**: Write declarative YAML rules using globs and substrings. Enforce rate limits (`max_calls_per_session`) and volume limits (`maxBytesReturned`) to prevent token stuffing.
- **Human-in-the-Loop Approval**: Securely prompts you on `/dev/tty` for risky actions, bypassing MCP streams. Supports "Always" and "Never" memory for uninterrupted sessions.
- **Visual Analytics Dashboard**: A local web UI powered by an embedded SQLite database to inspect agent timelines, risk distributions, and JSON-RPC payloads.

## 🚀 Quick Start

### 1. Install
```bash
pip install tracegate
```

### 2. Auto-Install into your IDE (Cursor / Claude Desktop)
TraceGate can automatically discover your agent configurations and inject its proxy wrapper:
```bash
tracegate install
```
*(To revert to your original configuration, simply run `tracegate uninstall`).*

### 3. Write a Policy
Create a `policy.yaml` file to enforce rules:

```yaml
version: 1
defaultAction: ask
dlpEnabled: true
maxBytesReturned: 50000

rules:
  # Deny recursive deletions outright
  - id: block-rm
    tool: execute_command
    match_args_contain:
      command: ["rm -rf", "rm -r"]
    action: deny
    
  # Allow reading files in your project, but rate-limit to 50 reads
  - id: allow-local-read
    tool: read_file
    match_args:
      path: "/Users/you/projects/*"
    action: allow
    max_calls_per_session: 50
```

### 4. Review Sessions visually
Install the dashboard dependencies and launch the local web UI to view your agent sessions in real-time:

```bash
pip install "tracegate[dashboard]"
tracegate dashboard
```
Open `http://localhost:8080` in your browser.

## 🧩 Advanced Examples & Integrations

TraceGate can be integrated into nearly any agent workflow. See our dedicated guides in the `examples/` directory:

1. **[Cursor / Claude Desktop Integration](examples/cursor_integration/README.md)**: Learn how to manually inject TraceGate into `.cursor/mcp.json`.
2. **[Docker + SSE Isolation](examples/docker_sse/README.md)**: A `docker-compose` example showing how to run a dangerous MCP server inside an isolated container, while TraceGate proxies over HTTP (SSE) to enforce rules on the host.
3. **[Antigravity SDK (Python API)](examples/antigravity_sdk/demo.py)**: Learn how to import TraceGate's `PolicyEngine` and `RedactionEngine` directly into your custom Python agent loops.
4. **[Demo Interactive Server](examples/malicious_server.py)**: Run a standalone terminal demo to see TraceGate intercepting simulated attacks and exfiltrations.

## ⚙️ Manual Usage (Proxy Command)

If you prefer to wrap an MCP server manually, use the `proxy` command. 

**For stdio servers:**
```bash
tracegate proxy --policy policy.yaml -- npx -y @modelcontextprotocol/server-filesystem /tmp
```

**For SSE (HTTP) servers:**
If your target server uses SSE instead of stdio (e.g., remote or Dockerized servers), use the `--mode sse` flag:
```bash
tracegate proxy --mode sse --target http://localhost:8000 --policy policy.yaml
```

## 📖 CLI Reference

- `tracegate install [OPTIONS]`: Auto-discover agent configs and inject wrapper.
- `tracegate uninstall`: Remove TraceGate wrappers.
- `tracegate proxy [OPTIONS] [-- <command> [args...]]`: Run an MCP server through the firewall.
  - `--mode <stdio|sse>`: Transport mode (default: `stdio`).
  - `--target <url>`: Target URL for SSE mode.
  - `--policy <path>`: YAML policy file to apply.
  - `--log-dir <path>`: Directory to save audit logs.
- `tracegate dashboard [OPTIONS]`: Launch the local web dashboard.
- `tracegate sessions`: List all recorded sessions.
- `tracegate replay <session_id> [--filter risk=high]`: Replay a session timeline in the terminal.
- `tracegate check-policy <path>`: Validate your policy syntax.

## 📄 License
MIT License.

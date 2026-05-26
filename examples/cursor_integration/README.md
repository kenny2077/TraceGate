# TraceGate + Cursor Integration Guide

Cursor is one of the most popular AI code editors and supports the Model Context Protocol (MCP) natively. 

By default, when you add an MCP server in Cursor, Cursor communicates directly with that server over stdio. If that server is compromised, it has full access to your local machine.

Here is how you inject TraceGate into Cursor to act as a silent firewall.

## 1. Locate Cursor's MCP Configuration

Cursor stores its MCP configuration in your project's `.cursor/mcp.json` file. 

A standard configuration looks like this:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/me/Projects"]
    }
  }
}
```

## 2. Inject the TraceGate Wrapper

TraceGate acts as a transparent proxy. You just need to prefix the original command with `tracegate wrap --`.

Update your `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "tracegate",
      "args": [
        "wrap", 
        "--", 
        "npx", 
        "-y", 
        "@modelcontextprotocol/server-filesystem", 
        "/Users/me/Projects"
      ]
    }
  }
}
```

*Note: Make sure the `tracegate` executable is in your system PATH, or provide the absolute path to it.*

## 3. Configure Policies

By default, TraceGate looks for a `policy.yaml` file in `~/.tracegate/policy.yaml`. 
If you want to use a project-specific policy, you can specify it in the args:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "tracegate",
      "args": [
        "wrap",
        "--policy",
        "./tracegate_policy.yaml",
        "--", 
        "npx", 
        "-y", 
        "@modelcontextprotocol/server-filesystem", 
        "/Users/me/Projects"
      ]
    }
  }
}
```

## 4. Observe the Traffic

Once configured, Cursor will boot TraceGate, which in turn boots the filesystem server. 

You can now open a terminal and run:

```bash
tracegate dashboard
```

Navigate to `http://localhost:8000` to watch all of Cursor's tool calls in real-time, view risk assessments, and audit the agent's behavior!

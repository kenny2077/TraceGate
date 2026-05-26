# TraceGate Docker + SSE Demo

This example demonstrates how to run an untrusted MCP server inside an isolated Docker container, while running TraceGate on the host machine to enforce policy and audit logs via Server-Sent Events (SSE).

## 1. Start the Isolated Server

First, boot the dummy MCP server inside a Docker container:

```bash
docker-compose up -d
```

The server is now listening on `http://localhost:8000/sse`, but it is completely isolated from your host filesystem!

## 2. Start TraceGate (The Proxy)

Now, run TraceGate on your host machine to proxy traffic to the Docker container. 

```bash
tracegate proxy --mode sse --target http://localhost:8000
```

TraceGate itself will listen on `http://127.0.0.1:8080/sse`.

## 3. Connect your AI Agent

Configure your AI agent (like Claude Desktop or Cursor) to connect to TraceGate instead of the raw Docker container.

For example, in a Cursor `.cursor/mcp.json` or `claude_desktop_config.json`, you would point it to the TraceGate SSE endpoint:

```json
{
  "mcpServers": {
    "docker-isolated-tools": {
      "command": "node",
      "args": ["connect-to-sse.js", "http://127.0.0.1:8080/sse"]
    }
  }
}
```
*(Note: connecting to SSE usually requires a small client script depending on the editor).*

## Result

- The AI Agent thinks it is talking directly to the server.
- The Server runs safely inside Docker, preventing it from secretly modifying your local files.
- TraceGate sits in the middle, evaluating your `policy.yaml` rules, logging every tool call to SQLite, and prompting you for approval if the Docker container tries to do something risky!

## Cleanup

```bash
docker-compose down
```

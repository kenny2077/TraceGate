# ADR 002: Proxy Architecture - Stdio Interception

**Date:** 2026-05-25
**Status:** Accepted

## Context
The Model Context Protocol (MCP) supports multiple transports, primarily `stdio` (Standard I/O) and `SSE` (Server-Sent Events over HTTP). TraceGate needs to intercept tool calls before they reach the server. We must decide how TraceGate integrates into the connection between the Agent and the Server.

## Alternatives Considered
1. **SDK Injection**: Modify the MCP client SDK to include TraceGate middleware.
   - *Pros*: Invisible at the OS level.
   - *Cons*: Requires modifying the agent's source code; doesn't work for closed-source agents (like Claude Desktop or Cursor).
2. **SSE Reverse Proxy**: Run TraceGate as an HTTP reverse proxy and have agents connect via SSE.
   - *Pros*: Standard web architecture.
   - *Cons*: Many agents default to `stdio` for local tools. Setting up SSE requires port management and network boundaries.
3. **Stdio Subprocess Interceptor (Man-in-the-Middle)**: TraceGate acts as a transparent wrapper. The agent executes `tracegate proxy -- python server.py`. TraceGate takes over `stdio`, spawns the real server as a child, and relays traffic.

## Decision
We will build a **Stdio Subprocess Interceptor**. TraceGate will act as a transparent relay for `stdin` and `stdout`, parsing the JSON-RPC chunks in-flight.

## Rationale
- **Universal Compatibility**: Works with *any* agent that supports MCP over stdio (Claude Desktop, Cursor, Windsurf, generic MCP clients) without requiring any code changes to the agent itself. The user simply updates their agent configuration to point to `tracegate` instead of the raw tool executable.
- **Defense-in-Depth**: Because TraceGate controls the actual child process, if TraceGate crashes or encounters an unrecoverable policy error, the child server dies with it, failing secure.
- **Out-of-Band Approval**: Because standard I/O is consumed by the JSON-RPC protocol, TraceGate can still prompt the user for human-in-the-loop approval by opening `/dev/tty` (or Windows `CON`) directly, preventing prompt text from corrupting the MCP stream.

## Consequences
- **Positive**: Zero integration required on the agent side besides modifying the command array in a JSON config.
- **Negative**: Parsing raw JSON-RPC from stdio streams requires careful buffer management to handle partial chunks.
- **Negative**: Windows support for asynchronous stdio and `/dev/tty` equivalents requires OS-specific handling. MVP will target Unix-like systems natively with best-effort Windows support.

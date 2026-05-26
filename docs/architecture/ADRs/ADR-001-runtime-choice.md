# ADR 001: Runtime Choice - Python & Asyncio

**Date:** 2026-05-25
**Status:** Accepted

## Context
TraceGate sits between an AI coding agent and a local MCP tool server. It needs to concurrently read/write high-volume JSON-RPC byte streams (from agent `stdin` to server `stdout`) while also evaluating policies, logging to disk, and occasionally halting traffic to prompt a human via `/dev/tty`. We needed a language and runtime that supports non-blocking I/O, rapid prototyping, and aligns with the AI developer ecosystem.

## Alternatives Considered
1. **TypeScript / Node.js**: Excellent async support. The `agent-wall` reference is written in TS. However, the majority of AI agents, SDKs, and data engineering tools are Python-centric.
2. **Go**: Great for concurrent proxies, single-binary distribution. However, slightly slower for rapid iteration and less familiar to the core AI engineering target audience.
3. **Python (Synchronous / Threading)**: Threads in Python are subject to the GIL and can lead to complex deadlocks when dealing with multiple blocking `sys.stdin`/`sys.stdout` streams.

## Decision
We will use **Python 3.11+ with the `asyncio` standard library** as the core runtime.

## Rationale
- **Ecosystem Alignment**: TraceGate is designed to protect AI agents (like Claude Code, AutoGPT, OpenDevin), the vast majority of which are built with or interact heavily with Python.
- **`asyncio.subprocess`**: The standard library provides robust tools (`create_subprocess_exec`) for spawning the MCP server and asynchronously reading its output streams without deadlocking.
- **Ease of Distribution**: `pip install tracegate` is the expected path for most data/AI practitioners. 

## Consequences
- **Positive**: We can use standard Python libraries (`pydantic` for types, `pyyaml` for policy) and easily integrate with future AI security libraries.
- **Negative**: Async programming in Python can be tricky, especially when dealing with standard I/O streams (e.g., `sys.stdin` is blocking by default; we must use `asyncio.StreamReader` wrappers). Performance is slower than Go/Rust, but JSON-RPC proxying is I/O bound, not CPU bound.

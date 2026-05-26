# Contributing to TraceGate

Thank you for your interest in contributing to TraceGate! 

## Development Setup

1. Clone the repository
2. Run `uv pip install -e ".[dev]"`
3. Run tests with `pytest tests/`

## Architecture

TraceGate operates as a stdio proxy between an AI agent and an MCP server.
See `architecture.md` (or the equivalent artifacts) for design details.

## Pull Requests

1. Please include unit tests for any new policy rules or risk heuristics.
2. Ensure you format the code using `ruff`.

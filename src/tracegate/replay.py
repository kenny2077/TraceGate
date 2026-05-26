import os
import json
from rich.console import Console
from rich.panel import Panel

console = Console()


def replay_session(
    session_id: str,
    log_dir: str = None,
    filter_str: str = None,
):
    """Replay a TraceGate audit session, streaming events line-by-line."""
    from pathlib import Path

    if log_dir is None:
        log_dir = os.path.join(Path.home(), ".tracegate", "sessions")

    log_file = os.path.join(log_dir, f"session_{session_id}.jsonl")

    if not os.path.exists(log_file):
        console.print(f"[bold red]Error:[/] Session log not found at {log_file}")
        console.print("[dim]Hint: use 'tracegate sessions' to list available sessions.[/]")
        return

    # Parse filter
    filter_key, filter_value = None, None
    if filter_str and "=" in filter_str:
        filter_key, filter_value = filter_str.split("=", 1)

    console.print(f"\n[bold blue]TraceGate Replay[/]: Session [cyan]{session_id}[/]\n")

    event_count = 0
    shown_count = 0

    # Stream line-by-line instead of loading entire file
    with open(log_file, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                console.print(f"[dim red]⚠ Skipping malformed line {line_num}[/]")
                continue

            event_count += 1
            event_type = event.get("event_type")
            payload = event.get("payload", {})
            timestamp = event.get("timestamp", "?")

            # Apply filter
            if filter_key and filter_value:
                if filter_key == "risk":
                    if event_type != "policy_decision":
                        continue
                    if payload.get("risk_level") != filter_value:
                        continue
                elif filter_key == "decision":
                    if event_type != "policy_decision":
                        continue
                    if payload.get("action") != filter_value:
                        continue
                elif filter_key == "type":
                    if event_type != filter_value:
                        continue

            shown_count += 1
            _render_event(event_type, payload, timestamp)

    console.print(f"\n[bold blue]End of Replay[/] ({shown_count}/{event_count} events shown)\n")


def _render_event(event_type: str, payload: dict, timestamp: str):
    """Render a single event to the console."""
    if event_type == "session_start":
        server = payload.get("server_command", "?")
        policy = payload.get("policy_path", "none")
        console.print(Panel(
            f"Server: [bold]{server}[/]\nPolicy: {policy}",
            title="[green]Session Started[/]",
            subtitle=timestamp[:19],
            border_style="green",
        ))

    elif event_type == "session_end":
        exit_code = payload.get("exit_code", "?")
        total = payload.get("total_events", "?")
        console.print(Panel(
            f"Exit code: {exit_code} | Total events: {total}",
            title="[blue]Session Ended[/]",
            subtitle=timestamp[:19],
            border_style="blue",
        ))

    elif event_type == "tool_call":
        tool_name = payload.get("name", "?")
        args = payload.get("arguments", {})
        args_str = json.dumps(args, indent=2, default=str)
        if len(args_str) > 300:
            args_str = args_str[:300] + "\n..."
        console.print(Panel(
            f"[bold magenta]Arguments:[/]\n{args_str}",
            title=f"[cyan]→ {tool_name}[/]",
            subtitle=timestamp[:19],
            border_style="cyan",
        ))

    elif event_type == "policy_decision":
        action = payload.get("action", "?")
        message = payload.get("message", "")
        rule = payload.get("rule_id", "default")
        risk = payload.get("risk_level")
        tags = payload.get("risk_tags", [])

        color = "green" if action == "allow" else "red" if action == "deny" else "yellow"
        risk_str = ""
        if risk:
            risk_color = "red" if risk in ("high", "critical") else "yellow" if risk == "medium" else "green"
            risk_str = f" | Risk: [{risk_color}]{risk.upper()}[/] {tags}"
        console.print(
            f"  [{color}]↳ [{color} bold]{action.upper()}[/] "
            f"(rule: {rule}){risk_str} — {message}"
        )

    elif event_type == "human_approval":
        approved = payload.get("approved")
        status = "[bold green]APPROVED[/]" if approved else "[bold red]DENIED[/]"
        console.print(f"  ↳ Human decision: {status}")

    elif event_type == "tool_result":
        error = payload.get("error")
        if error:
            console.print(f"  [red]↳ Error:[/] {error}")
        else:
            console.print(f"  [green]↳ Success[/]")

    elif event_type == "request_duration":
        ms = payload.get("duration_ms", "?")
        console.print(f"  [dim]↳ {ms}ms[/]")

    else:
        console.print(f"  [dim]↳ {event_type}: {payload}[/]")

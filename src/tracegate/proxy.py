import asyncio
import signal
import sys
import os
import logging
import json
from typing import List, Optional

logger = logging.getLogger(__name__)


async def stream_reader(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    name: str,
    audit_logger: Optional['AuditLogger'] = None,
    policy_engine: Optional['PolicyEngine'] = None,
    agent_writer: Optional[asyncio.StreamWriter] = None,
    risk_classifier: Optional['RiskClassifier'] = None,
    pending_requests: Optional[dict] = None,
    session_memory: Optional[dict] = None,
    session_state: Optional['SessionState'] = None,
    dlp_engine: Optional['RedactionEngine'] = None,
):
    """
    Read from `reader` line by line, parse JSON-RPC, evaluate policy, log, and write to `writer`.
    """
    from tracegate.mcp import parse_message, JsonRpcRequest, JsonRpcResponse
    from tracegate.policy import RuleAction

    try:
        while True:
            line = await reader.readline()
            if not line:
                break

            # Try to parse as JSON-RPC
            msg = None
            if audit_logger or policy_engine:
                try:
                    msg = parse_message(line)
                except Exception as e:
                    logger.debug(f"Failed to parse line as JSON-RPC: {e}")

            should_pass = True

            # Check for initialize handshake
            if msg and isinstance(msg, JsonRpcRequest) and msg.method == "initialize":
                if audit_logger:
                    await audit_logger.log_event_async("session_init", {"id": msg.id})
                    
            elif msg and isinstance(msg, JsonRpcRequest) and msg.method == "notifications/initialized":
                if audit_logger:
                    await audit_logger.log_event_async("session_initialized", {})

            # --- Agent → Server direction: intercept tools/call ---
            if msg and isinstance(msg, JsonRpcRequest) and msg.method == "tools/call":
                tool_name = msg.params.get("name", "unknown") if msg.params else "unknown"
                arguments = msg.params.get("arguments", {}) if msg.params else {}
                call_id = msg.id

                # Track pending request for response correlation
                if pending_requests is not None and call_id is not None:
                    import time
                    pending_requests[call_id] = {
                        "tool_name": tool_name,
                        "timestamp": time.time(),
                    }

                # Classify Risk
                risk_level = None
                risk_tags = None
                if risk_classifier:
                    rc = risk_classifier.classify(tool_name, arguments)
                    risk_level = rc.level
                    risk_tags = rc.tags

                # Audit: log tool call
                if audit_logger:
                    await audit_logger.log_tool_call_async(tool_name, arguments, call_id)

                # Evaluate Policy
                if policy_engine:
                    verdict = policy_engine.evaluate(tool_name, arguments, session_state)
                    if audit_logger:
                        await audit_logger.log_policy_decision_async(
                            call_id, tool_name, verdict.action.value,
                            verdict.rule_id, verdict.message,
                            risk_level=risk_level, risk_tags=risk_tags,
                        )

                    # Interception Logic
                    if verdict.action == RuleAction.DENY:
                        logger.warning(f"Blocked tool call '{tool_name}': {verdict.message}")
                        should_pass = False

                    elif verdict.action == RuleAction.ASK:
                        memory_key = f"{verdict.rule_id}:{tool_name}"
                        
                        if session_memory is not None and memory_key in session_memory:
                            decision = session_memory[memory_key]
                            if decision == 'always':
                                should_pass = True
                            else:
                                should_pass = False
                        else:
                            from tracegate.approval import prompt_for_approval
                            response = await prompt_for_approval(
                                tool_name, arguments, verdict.message,
                                risk_level=risk_level,
                            )
                            
                            if response in ('always', 'yes'):
                                logger.info(f"User approved tool call '{tool_name}' ({response})")
                                if audit_logger:
                                    await audit_logger.log_event_async("human_approval", {
                                        "id": call_id, "approved": True, "response": response
                                    })
                                should_pass = True
                                if response == 'always' and session_memory is not None:
                                    session_memory[memory_key] = 'always'
                            else:
                                logger.warning(f"User denied tool call '{tool_name}' ({response})")
                                if audit_logger:
                                    await audit_logger.log_event_async("human_approval", {
                                        "id": call_id, "approved": False, "response": response
                                    })
                                should_pass = False
                                if response == 'never' and session_memory is not None:
                                    session_memory[memory_key] = 'never'

                    # Send synthetic JSON-RPC error for blocked calls
                    if not should_pass:
                        error_response = {
                            "jsonrpc": "2.0",
                            "id": call_id,
                            "error": {
                                "code": -32000,
                                "message": f"TraceGate blocked: {verdict.message}",
                            },
                        }
                        if agent_writer:
                            error_line = json.dumps(error_response) + "\n"
                            agent_writer.write(error_line.encode("utf-8"))
                            await agent_writer.drain()
                        # Remove from pending since we blocked it
                        if pending_requests is not None and call_id in pending_requests:
                            del pending_requests[call_id]

            # --- Server → Agent direction: log responses ---
            elif msg and isinstance(msg, JsonRpcResponse) and msg.id is not None:
                if audit_logger:
                    # Compute duration if we tracked the request
                    duration_ms = None
                    if pending_requests is not None and msg.id in pending_requests:
                        import time
                        req_info = pending_requests.pop(msg.id)
                        duration_ms = round((time.time() - req_info["timestamp"]) * 1000, 1)

                    await audit_logger.log_tool_result_async(
                        call_id=msg.id, result=msg.result, error=msg.error,
                    )
                    if duration_ms is not None:
                        await audit_logger.log_event_async("request_duration", {
                            "id": msg.id, "duration_ms": duration_ms,
                        })

                # Apply DLP and Max Bytes Returned if available
                if policy_engine and policy_engine.config.dlp_enabled and dlp_engine and msg.result:
                    msg.result = dlp_engine.redact(msg.result)
                
                if policy_engine and policy_engine.config.max_bytes_returned and msg.result:
                    # Very simple truncation logic (e.g. stringifying JSON, but let's just do it on strings)
                    if isinstance(msg.result, str) and len(msg.result) > policy_engine.config.max_bytes_returned:
                        msg.result = msg.result[:policy_engine.config.max_bytes_returned] + f"... [truncated to {policy_engine.config.max_bytes_returned} bytes by TraceGate DLP]"
                    elif isinstance(msg.result, dict):
                        # Deep truncation could be done, but for MVP we truncate the string representation if it's too big
                        # Wait, we can't just convert a dict to a string if the agent expects a dict.
                        # MCP results are usually dicts with "content" lists or similar.
                        pass # Need a more robust deep truncator, but this covers basic string responses
                        
                # If we modified the message, we need to rewrite `line`
                if policy_engine and (policy_engine.config.dlp_enabled or policy_engine.config.max_bytes_returned):
                    raw_dict = {
                        "jsonrpc": msg.jsonrpc,
                        "id": msg.id,
                    }
                    if msg.result is not None:
                        raw_dict["result"] = msg.result
                    if msg.error is not None:
                        raw_dict["error"] = msg.error
                    
                    line = (json.dumps(raw_dict) + "\n").encode("utf-8")

            # Pass through if not blocked
            if should_pass:
                writer.write(line)
                await writer.drain()

    except asyncio.CancelledError:
        pass  # Expected during shutdown
    except Exception as e:
        logger.error(f"Error in {name} stream: {e}")


async def run_proxy(command: List[str], policy_path: str = None, log_dir: str = None):
    """
    Spawns the target MCP server subprocess and relays stdio with policy enforcement.
    """
    from tracegate.audit import AuditLogger
    from tracegate.policy import PolicyEngine
    from tracegate.risk import RiskClassifier

    server_cmd_str = " ".join(command)
    logger.info(f"Spawning target server: {server_cmd_str}")

    # Initialize components
    audit_logger = AuditLogger(
        log_dir=log_dir,
        server_command=server_cmd_str,
        policy_path=policy_path,
    )
    risk_classifier = RiskClassifier()
    pending_requests: dict = {}  # JSON-RPC id → {tool_name, timestamp}
    session_memory: dict = {} # rule_id:tool_name → "always" or "never"
    
    from tracegate.policy import SessionState
    session_state = SessionState()

    # Initialize policy engine
    policy_engine = None
    if policy_path:
        logger.info(f"Loading policy from {policy_path}")
        try:
            policy_engine = PolicyEngine(policy_path)
        except Exception as e:
            logger.error(f"Failed to load policy: {e}")
            sys.exit(1)
            
    from tracegate.dlp import RedactionEngine
    dlp_engine = RedactionEngine()

    # Emit session start
    audit_logger.log_session_start()
    logger.info(f"Session: {audit_logger.session_id}")
    logger.info(f"Audit log: {audit_logger.log_file}")

    # Spawn the child process
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=sys.stderr,
    )

    # Setup async stdio for the proxy process itself
    loop = asyncio.get_running_loop()

    agent_reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(agent_reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    agent_writer_transport, agent_writer_protocol = await loop.connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout,
    )
    agent_writer = asyncio.StreamWriter(
        agent_writer_transport, agent_writer_protocol, agent_reader, loop,
    )

    # Create concurrent streaming tasks
    agent_to_server = asyncio.create_task(
        stream_reader(
            reader=agent_reader,
            writer=process.stdin,
            name="agent→server",
            audit_logger=audit_logger,
            policy_engine=policy_engine,
            agent_writer=agent_writer,
            risk_classifier=risk_classifier,
            pending_requests=pending_requests,
            session_memory=session_memory,
            session_state=session_state,
            dlp_engine=dlp_engine,
        )
    )
    server_to_agent = asyncio.create_task(
        stream_reader(
            reader=process.stdout,
            writer=agent_writer,
            name="server→agent",
            audit_logger=audit_logger,
            policy_engine=policy_engine, # Pass policy_engine here to read config!
            agent_writer=None,
            risk_classifier=None,
            pending_requests=pending_requests,
            session_memory=session_memory,
            session_state=session_state,
            dlp_engine=dlp_engine,
        )
    )

    # Signal handling for graceful shutdown
    shutdown_triggered = False

    def handle_signal(sig, _frame):
        nonlocal shutdown_triggered
        if not shutdown_triggered:
            shutdown_triggered = True
            logger.info(f"Received signal {sig}, shutting down...")
            agent_to_server.cancel()
            server_to_agent.cancel()
            if process.returncode is None:
                process.terminate()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Wait for completion
    try:
        done, _pending = await asyncio.wait(
            [agent_to_server, server_to_agent, asyncio.ensure_future(process.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # If the child process exited, cancel the stream tasks
        if process.returncode is not None:
            agent_to_server.cancel()
            server_to_agent.cancel()
        else:
            # A stream ended — wait briefly for the other, then clean up
            await asyncio.sleep(0.1)
            agent_to_server.cancel()
            server_to_agent.cancel()
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()

    except asyncio.CancelledError:
        pass
    finally:
        # Ensure child is cleaned up
        if process.returncode is None:
            process.kill()
            await process.wait()

        exit_code = process.returncode or 0
        audit_logger.log_session_end(exit_code=exit_code)
        logger.info(f"Server exited with code {exit_code}")
        sys.exit(exit_code)

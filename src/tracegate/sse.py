import asyncio
import json
import logging
import sys
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import StreamingResponse
import httpx
from sse_starlette.sse import EventSourceResponse

from tracegate.mcp import parse_message, JsonRpcRequest, JsonRpcResponse
from tracegate.policy import PolicyEngine, RuleAction, SessionState
from tracegate.risk import RiskClassifier
from tracegate.audit import AuditLogger
from tracegate.approval import prompt_for_approval

logger = logging.getLogger(__name__)

app = FastAPI(title="TraceGate SSE Proxy")

# Global state to hold proxy configuration
class ProxyState:
    target_url: str = ""
    policy_engine: Optional[PolicyEngine] = None
    audit_logger: Optional[AuditLogger] = None
    risk_classifier: Optional[RiskClassifier] = None
    session_memory: Dict[str, str] = {}
    pending_requests: Dict[str, Dict[str, Any]] = {}
    client: Optional[httpx.AsyncClient] = None
    session_state: Optional[SessionState] = None
    dlp_engine: Optional['RedactionEngine'] = None

state = ProxyState()

@app.on_event("startup")
async def startup_event():
    # The client needs a long timeout because MCP tools can take a while
    state.client = httpx.AsyncClient(timeout=300.0)

@app.on_event("shutdown")
async def shutdown_event():
    if state.client:
        await state.client.aclose()
    if state.audit_logger:
        state.audit_logger.log_session_end(exit_code=0)

@app.get("/sse")
async def sse_endpoint(request: Request):
    """
    Client initiates SSE connection. We proxy this to the target server,
    but intercept the first 'endpoint' event to rewrite the POST URL.
    """
    if not state.target_url:
        raise HTTPException(status_code=500, detail="Proxy target not configured")

    if state.audit_logger:
        state.audit_logger.log_session_start()
        await state.audit_logger.log_event_async("session_initialized", {"transport": "sse"})

    target_sse_url = f"{state.target_url}/sse"
    
    async def sse_generator():
        try:
            async with state.client.stream("GET", target_sse_url) as response:
                if response.status_code != 200:
                    yield f"event: error\ndata: Failed to connect to target: {response.status_code}\n\n"
                    return

                # Read lines from the SSE stream
                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        event_block, buffer = buffer.split("\n\n", 1)
                        lines = event_block.split("\n")
                        
                        event_type = "message"
                        data = ""
                        
                        for line in lines:
                            if line.startswith("event: "):
                                event_type = line[7:]
                            elif line.startswith("data: "):
                                data = line[6:]
                                
                        # Intercept 'endpoint' event
                        if event_type == "endpoint":
                            # The target server is telling us where to POST messages.
                            # We need to tell the client to POST to US instead.
                            # Usually data contains a relative or absolute URL.
                            # We will save the target's POST endpoint, and give the client our own.
                            state.target_post_url = data
                            
                            # Rewrite the endpoint for the client
                            proxy_host = request.headers.get("host", "localhost:8080")
                            yield f"event: endpoint\ndata: http://{proxy_host}/message\n\n"
                        else:
                            # Forward other events (like JSON-RPC responses) verbatim
                            
                            # Log responses if possible
                            if event_type == "message" and data and state.audit_logger:
                                try:
                                    msg = parse_message(data.encode('utf-8'))
                                    if isinstance(msg, JsonRpcResponse) and msg.id is not None:
                                        duration_ms = None
                                        if msg.id in state.pending_requests:
                                            import time
                                            req_info = state.pending_requests.pop(msg.id)
                                            duration_ms = round((time.time() - req_info["timestamp"]) * 1000, 1)

                                        await state.audit_logger.log_tool_result_async(
                                            call_id=msg.id, result=msg.result, error=msg.error
                                        )
                                        if duration_ms is not None:
                                            await state.audit_logger.log_event_async("request_duration", {
                                                "id": msg.id, "duration_ms": duration_ms
                                            })
                                        
                                        # Apply DLP and Max Bytes Returned
                                        modified = False
                                        if state.policy_engine and state.policy_engine.config.dlp_enabled and state.dlp_engine and msg.result:
                                            msg.result = state.dlp_engine.redact(msg.result)
                                            modified = True
                                        
                                        if state.policy_engine and state.policy_engine.config.max_bytes_returned and msg.result:
                                            if isinstance(msg.result, str) and len(msg.result) > state.policy_engine.config.max_bytes_returned:
                                                msg.result = msg.result[:state.policy_engine.config.max_bytes_returned] + f"... [truncated to {state.policy_engine.config.max_bytes_returned} bytes by TraceGate DLP]"
                                                modified = True
                                                
                                        if modified:
                                            raw_dict = {
                                                "jsonrpc": msg.jsonrpc,
                                                "id": msg.id,
                                            }
                                            if msg.result is not None:
                                                raw_dict["result"] = msg.result
                                            if msg.error is not None:
                                                raw_dict["error"] = msg.error
                                            
                                            data = json.dumps(raw_dict)
                                            event_block = f"event: {event_type}\ndata: {data}"
                                            
                                except Exception:
                                    pass

                            yield f"{event_block}\n\n"
                            
        except Exception as e:
            logger.error(f"SSE proxy error: {e}")
            yield f"event: error\ndata: Proxy connection lost\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")

@app.post("/message")
async def message_endpoint(request: Request):
    """
    Client POSTs JSON-RPC messages here. We evaluate policy,
    and if allowed, forward to the target server's POST endpoint.
    """
    if not hasattr(state, 'target_post_url') or not state.target_post_url:
        raise HTTPException(status_code=400, detail="SSE connection not established yet")

    body = await request.body()
    
    try:
        msg = parse_message(body)
    except Exception as e:
        logger.debug(f"Failed to parse message: {e}")
        # Forward malformed messages verbatim, let target handle it
        return await _forward_to_target(body)

    should_pass = True
    call_id = getattr(msg, "id", None)

    # Agent → Server interception
    if isinstance(msg, JsonRpcRequest) and msg.method == "tools/call":
        tool_name = msg.params.get("name", "unknown") if msg.params else "unknown"
        arguments = msg.params.get("arguments", {}) if msg.params else {}

        if call_id is not None:
            import time
            state.pending_requests[call_id] = {
                "tool_name": tool_name,
                "timestamp": time.time(),
            }

        risk_level = None
        risk_tags = None
        if state.risk_classifier:
            rc = state.risk_classifier.classify(tool_name, arguments)
            risk_level = rc.level
            risk_tags = rc.tags

        if state.audit_logger:
            await state.audit_logger.log_tool_call_async(tool_name, arguments, call_id)

        if state.policy_engine:
            verdict = state.policy_engine.evaluate(tool_name, arguments, state.session_state)
            
            if state.audit_logger:
                await state.audit_logger.log_policy_decision_async(
                    call_id, tool_name, verdict.action.value,
                    verdict.rule_id, verdict.message,
                    risk_level=risk_level, risk_tags=risk_tags,
                )

            if verdict.action == RuleAction.DENY:
                should_pass = False
            elif verdict.action == RuleAction.ASK:
                memory_key = f"{verdict.rule_id}:{tool_name}"
                
                if memory_key in state.session_memory:
                    decision = state.session_memory[memory_key]
                    should_pass = (decision == 'always')
                else:
                    response = await prompt_for_approval(
                        tool_name, arguments, verdict.message, risk_level=risk_level
                    )
                    
                    if response in ('always', 'yes'):
                        if state.audit_logger:
                            await state.audit_logger.log_event_async("human_approval", {
                                "id": call_id, "approved": True, "response": response
                            })
                        should_pass = True
                        if response == 'always':
                            state.session_memory[memory_key] = 'always'
                    else:
                        if state.audit_logger:
                            await state.audit_logger.log_event_async("human_approval", {
                                "id": call_id, "approved": False, "response": response
                            })
                        should_pass = False
                        if response == 'never':
                            state.session_memory[memory_key] = 'never'

            if not should_pass:
                # To simulate a blocked request in SSE, we don't return the error directly
                # in the POST response (which just ACKs the message). We have to send the error
                # down the SSE stream. But injecting into the SSE stream from a POST handler
                # is complex. 
                # For MVP SSE, we return a 403 Forbidden to the POST. Most MCP clients will
                # treat a failed POST as a protocol error.
                if call_id in state.pending_requests:
                    del state.pending_requests[call_id]
                raise HTTPException(status_code=403, detail=f"TraceGate blocked: {verdict.message}")

    if should_pass:
        return await _forward_to_target(body)

async def _forward_to_target(body: bytes) -> Response:
    """Forward the POST request to the target server."""
    # Ensure URL is absolute
    url = state.target_post_url
    if url.startswith("/"):
        url = state.target_url + url
        
    try:
        resp = await state.client.post(url, content=body, headers={"Content-Type": "application/json"})
        return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))
    except Exception as e:
        logger.error(f"Failed to forward message to target: {e}")
        raise HTTPException(status_code=502, detail="Bad Gateway")

def run_sse_proxy(target_url: str, policy_path: Optional[str] = None, log_dir: Optional[str] = None, host: str = "127.0.0.1", port: int = 8000):
    """Start the SSE Proxy server."""
    import uvicorn
    
    state.target_url = target_url.rstrip("/")
    
    if policy_path:
        state.policy_engine = PolicyEngine(policy_path)
    
    state.audit_logger = AuditLogger(
        log_dir=log_dir,
        server_command=f"SSE Target: {target_url}",
        policy_path=policy_path
    )
    state.risk_classifier = RiskClassifier()
    state.session_state = SessionState()
    
    from tracegate.dlp import RedactionEngine
    state.dlp_engine = RedactionEngine()
    
    uvicorn.run(app, host=host, port=port)

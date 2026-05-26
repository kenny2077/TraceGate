import json
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field

class JsonRpcMessage(BaseModel):
    jsonrpc: str = Field(default="2.0")

class JsonRpcRequest(JsonRpcMessage):
    id: Union[str, int, None] = None
    method: str
    params: Optional[Dict[str, Any]] = None

class JsonRpcResponse(JsonRpcMessage):
    id: Union[str, int, None] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None

class ToolCall(BaseModel):
    id: Union[str, int]
    name: str
    arguments: Dict[str, Any]

def parse_message(payload: bytes) -> Optional[Union[JsonRpcRequest, JsonRpcResponse]]:
    """Attempt to parse a raw JSON-RPC byte payload."""
    try:
        data = json.loads(payload)
        if "method" in data:
            return JsonRpcRequest(**data)
        elif "result" in data or "error" in data:
            return JsonRpcResponse(**data)
    except Exception:
        pass
    return None

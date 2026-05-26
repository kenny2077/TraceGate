from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import asyncio
import json

app = FastAPI()

@app.get("/sse")
async def sse(request: Request):
    async def event_stream():
        # First send the endpoint mapping so the client knows where to POST
        yield "event: endpoint\ndata: /message\n\n"
        
        while True:
            # In a real MCP server, this yields responses from a queue.
            # Here we just keep the connection alive.
            if await request.is_disconnected():
                break
            await asyncio.sleep(1)
            
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.post("/message")
async def message(request: Request):
    body = await request.body()
    # In a real server, this processes the JSON-RPC tool call
    # and pushes the response to the SSE stream queue.
    # For this demo, we just echo that we received it.
    print(f"Received: {body}")
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

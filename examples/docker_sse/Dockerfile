FROM python:3.11-slim
WORKDIR /app
RUN pip install fastapi uvicorn sse-starlette
COPY dummy_server.py .
CMD ["python", "dummy_server.py"]

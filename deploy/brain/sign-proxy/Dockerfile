# SUPERVOID MCP signing shim — tiny trusted hop in front of /mcp.
# Self-contained: holds the service token, signs the user-context, forwards.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY sign_proxy.py /app/sign_proxy.py

# Drop privileges — the shim needs no write access and holds only an env secret.
USER nobody

EXPOSE 8092

# Streamable-HTTP / SSE friendly single worker (state is per-request; scale with
# replicas behind the private network if ever needed).
CMD ["uvicorn", "sign_proxy:app", "--host", "0.0.0.0", "--port", "8092"]

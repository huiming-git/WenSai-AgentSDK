FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git bash bubblewrap \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN git clone --depth 1 https://github.com/NousResearch/hermes-agent.git /opt/hermes-agent \
    && pip install --no-cache-dir -e '/opt/hermes-agent[acp]' \
    && hermes --help >/dev/null \
    && python -c 'import acp_adapter'

COPY . .

RUN mkdir -p /data/agent-workspaces /root/.hermes

EXPOSE 8010

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]

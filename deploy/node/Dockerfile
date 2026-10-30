FROM python:3.13-slim
WORKDIR /app
COPY deploy/node/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY barc_node barc_node
RUN mkdir -p /data && chown 10001:10001 /data
ENV BARC_NODE_STATE=/data/node-identity.json
USER 10001:10001
CMD ["python", "-m", "barc_node.agent"]

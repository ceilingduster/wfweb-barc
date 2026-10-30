FROM python:3.13-slim
WORKDIR /app
COPY deploy/node/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY barc_node barc_node
USER 10001:10001
CMD ["python", "-m", "barc_node.agent"]

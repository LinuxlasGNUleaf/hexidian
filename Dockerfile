# syntax = docker/dockerfile:experimental
FROM python:3.10

ADD requirements.txt /tmp/
RUN --mount=type=cache,target=/root/.cache/pip pip install -r /tmp/requirements.txt

ADD src/ /app/

WORKDIR /app

CMD ["python", "main.py", "--config", "/config/config.yaml"]

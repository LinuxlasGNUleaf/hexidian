FROM python:3.10

ADD requirements.txt /tmp/
RUN pip install -r /tmp/requirements.txt

ADD src/ /app/

WORKDIR /app

CMD ["python", "main.py", "--config", "/config/config.yaml"]

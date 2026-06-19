FROM python:3.10-slim

WORKDIR /app

COPY . /app/

RUN pip install --no-cache-dir -e .[anthropic,openai,ollama]

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "agent.agent"]

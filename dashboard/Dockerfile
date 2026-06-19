FROM python:3.10-slim

WORKDIR /app

COPY . /app/

RUN pip install --no-cache-dir -e .

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "dashboard.dashboard"]

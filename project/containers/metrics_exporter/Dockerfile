FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY clock.py app.py ./

# Prometheus scrape endpoint. Keep in sync with METRICS_PORT / terraform var.
EXPOSE 9100

CMD ["python", "-u", "app.py"]

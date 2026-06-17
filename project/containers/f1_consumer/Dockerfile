FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY metrics.py app.py ./

# Long-running worker; no port exposed (SQS consumer only).
CMD ["python", "-u", "app.py"]

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY offchain /app/offchain
COPY data /app/data
COPY web /app/web

EXPOSE 8000

CMD ["uvicorn", "offchain.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

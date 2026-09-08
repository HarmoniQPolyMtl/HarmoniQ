FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY harmoniq/ harmoniq/
COPY data/ data/

COPY pyproject.toml .
RUN pip install --no-cache-dir .

EXPOSE 5000

CMD ["uvicorn", "harmoniq.webserver:app", "--host", "0.0.0.0", "--port", "5000"]

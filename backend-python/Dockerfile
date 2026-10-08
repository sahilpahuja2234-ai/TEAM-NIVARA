FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Seed deterministic synthetic data at build time.
# On first run the named volume is initialised from this directory.
RUN mkdir -p /app/data && python app/db/seed.py

# Run as an unprivileged user (configuration control for the security score).
RUN useradd --system --no-create-home --uid 10001 nivara \
    && chown -R nivara:nivara /app/data
USER nivara

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

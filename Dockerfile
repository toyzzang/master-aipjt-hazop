FROM node:22-slim AS frontend-build

WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci

COPY frontend ./frontend
RUN npm run build

FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY --from=frontend-build /build/app/static ./app/static
COPY scripts ./scripts
COPY README.md ./README.md

RUN mkdir -p /app/data/uploads /app/data/requests /app/samples

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

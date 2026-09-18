FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MOD_DB=/data/mod.sqlite3
WORKDIR /app
COPY server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ ./
RUN mkdir -p /data
EXPOSE 8080
CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:application"]

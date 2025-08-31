FROM python:3.9-slim
RUN mkdir -p /app /config /data
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r /app/requirements.txt
EXPOSE 9009
CMD ["gunicorn", "-b", "0.0.0.0:9009", "--log-level=info", "app:app"]
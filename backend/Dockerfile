FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py app.py db.py report_engine.py manual_engine.py library_engine.py richtext.py iam_engine.py printview.py /app/
RUN useradd --uid 10001 --create-home research && mkdir /data && chown research:research /data
USER research
ENV HOST=0.0.0.0 PORT=8080 DATA_DIR=/data API_ONLY=1 PYTHONUNBUFFERED=1
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/api/bootstrap',timeout=3)"
CMD ["python", "server.py"]

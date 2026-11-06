FROM python:3.11-slim
WORKDIR /app
COPY sample_app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y setuptools wheel
COPY sample_app ./sample_app
CMD ["uvicorn", "sample_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
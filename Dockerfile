FROM python:3.12-slim
RUN pip install --no-cache-dir solders==0.29.0
WORKDIR /app
COPY *.py ./
ENTRYPOINT ["python","itb.py"]

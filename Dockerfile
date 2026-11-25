FROM python:3.12-alpine
WORKDIR /app
COPY server.py .
COPY docs/ static/
ENV PORT=8090 STATIC_DIR=/app/static DATA_FILE=/data/state.json
EXPOSE 8090
CMD ["python", "-u", "server.py"]

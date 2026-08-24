FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY . /app
RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 voicemd

USER 10001
EXPOSE 8765
ENTRYPOINT ["voicemd"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8765", "--path", "/contracts/VOICE.md", "--no-global"]

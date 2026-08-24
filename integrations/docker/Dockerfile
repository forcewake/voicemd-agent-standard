FROM python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --create-home --uid 10001 voicemd

WORKDIR /tmp/voicemd-build
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
RUN python -m pip install --no-cache-dir . \
    && rm -rf /tmp/voicemd-build

WORKDIR /app
USER 10001:10001
EXPOSE 8765
ENTRYPOINT ["voicemd"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8765", "--path", "/contracts/VOICE.md", "--no-global"]

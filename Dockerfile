# Akay.ConvertToMarkdown worker image
#
# Runs as a non-root user, contains only runtime dependencies, and uses
# /tmp/akay for ephemeral conversion data. No HTTP port is exposed.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install runtime dependencies first so this layer is cached until
# pyproject.toml changes; source-code edits only invalidate the app layer below.
COPY pyproject.toml README.md ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Install the application itself (dependencies are already cached).
COPY src ./src
RUN pip install --no-cache-dir --no-deps .

# Dedicated non-root user.
RUN adduser --disabled-password --gecos "" --uid 10001 appuser \
    && mkdir -p /tmp/akay \
    && chown -R appuser:appuser /tmp/akay

USER appuser

ENV TEMP_DIRECTORY=/tmp/akay

ENTRYPOINT ["akay-convert-to-markdown"]

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

# System media tools (FFmpeg/FFprobe) used for audio extraction and probing.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# N12 preserves this legacy mixed image using the union of the two converter
# locks. N13 introduces the three independent images and model prefetching.
COPY pyproject.toml README.md ./
COPY requirements/document-linux.txt requirements/media-linux.txt ./requirements/
RUN pip install --no-cache-dir --require-hashes -r requirements/document-linux.txt -r requirements/media-linux.txt \
    && pip check

# Validate required external tools at build time (versions are surfaced so the
# expected toolchain is explicit in the build log).
RUN ffmpeg -version \
    && ffprobe -version

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

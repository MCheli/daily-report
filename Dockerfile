# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Timezone for the schedule library to fire at the right local time.
# Override at run-time with -e TZ=America/New_York if you want to
# avoid baking it into the image.
ENV TZ=America/New_York \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata curl \
 && ln -fs /usr/share/zoneinfo/${TZ} /etc/localtime \
 && dpkg-reconfigure -f noninteractive tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY daily_report ./daily_report
COPY examples ./examples
COPY README.md DEPLOYMENT.md TODO.md ./

# HTTP API
EXPOSE 8080

# Health check hits the /health endpoint
HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8080/health || exit 1

# Default to running the long-lived service. Override with
#   docker run ... python -m daily_report.cli report
# to do a one-shot print.
CMD ["python", "-m", "daily_report.cli", "service"]

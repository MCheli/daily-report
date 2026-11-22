# syntax=docker/dockerfile:1
# Exact patch + Debian release, matching production, so Dependabot can move it and a retag
# can't silently switch distro.
FROM python:3.12.16-slim-trixie

# Timezone for the schedule library to fire at the right local time.
# Override at run-time with -e TZ=America/New_York if you want to
# avoid baking it into the image.
ENV TZ=America/New_York \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# `upgrade` takes Debian security fixes newer than the base tag. No curl: the healthcheck
# uses Python, and curl_cffi bundles its own libcurl.
RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends tzdata \
 && ln -fs /usr/share/zoneinfo/${TZ} /etc/localtime \
 && dpkg-reconfigure -f noninteractive tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# requirements.txt is the pinned lockfile (compiled from requirements.in), so a rebuild
# never pulls new library versions.
COPY requirements.txt ./
# pip itself is pin-bumped past the base image's copy (pip advisories).
RUN pip install pip==26.3 \
 && pip install -r requirements.txt

COPY daily_report ./daily_report
COPY examples ./examples
COPY README.md DEPLOYMENT.md TODO.md ./

# Run unprivileged. The app only needs outbound TCP (printer :9100, APIs) and :8080; its home
# dir holds the matplotlib/yfinance caches, and /app stays root-owned and read-only to it.
RUN useradd --system --create-home --uid 10001 --user-group app
USER app

# HTTP API
EXPOSE 8080

# Health check hits the /health endpoint
HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4).read()"]

# Default to running the long-lived service. Override with
#   docker run ... python -m daily_report.cli report
# to do a one-shot print.
CMD ["python", "-m", "daily_report.cli", "service"]

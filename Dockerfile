# Версия должна совпадать с playwright в requirements.lock.txt.
FROM mcr.microsoft.com/playwright/python:v1.64.1-noble
WORKDIR /work
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# Allure 2 Commandline, запускаемый Jenkins-плагином, требует Java внутри agent.
RUN apt-get update \
    && apt-get install -y --no-install-recommends make openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock.txt .
RUN python -m pip install -r requirements.lock.txt
ARG INSTALL_SELENOID=false
COPY requirements-selenoid.txt .
RUN if [ "$INSTALL_SELENOID" = "true" ]; then python -m pip install -r requirements-selenoid.txt; fi
COPY . .
CMD ["make", "verify", "PYTHON=python"]

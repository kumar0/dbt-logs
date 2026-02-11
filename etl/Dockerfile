FROM python:3.11-slim

WORKDIR /dbt

# System deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# dbt project files
COPY dbt_project.yml packages.yml ./
COPY profiles_docker.yml profiles.yml
COPY macros/ macros/
COPY models/ models/
COPY publish_metrics.py /dbt/publish_metrics.py

# Install dbt packages
RUN dbt deps --profiles-dir .

# Entrypoint
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]

FROM python:3.11-slim

WORKDIR /dbt

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Install dbt dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy dbt project files
COPY dbt_project.yml .
COPY packages.yml .
COPY profiles.yml .
COPY macros/ macros/
COPY models/ models/

# Install dbt packages
RUN dbt deps --profiles-dir .

# Set default entrypoint
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]

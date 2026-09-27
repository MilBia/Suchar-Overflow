# Shared by docker-compose.local.yml and docker-compose.production.yml (#456).
# The Debian codename is pinned like the Python image's (#437), so a new Debian
# release reaches the database only by an explicit change here.
FROM docker.io/postgres:18-trixie

COPY ./compose/base/postgres/maintenance /usr/local/bin/maintenance
RUN chmod +x /usr/local/bin/maintenance/*
RUN mv /usr/local/bin/maintenance/* /usr/local/bin \
    && rmdir /usr/local/bin/maintenance

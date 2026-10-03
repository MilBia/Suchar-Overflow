# Shared by docker-compose.local.yml and docker-compose.production.yml (#456).
# The Debian codename is pinned like the Python image's (#437), so a new Debian
# release reaches the database only by an explicit change here.
FROM docker.io/postgres:18-trixie

COPY ./compose/base/postgres/maintenance /usr/local/bin/maintenance
RUN chmod +x /usr/local/bin/maintenance/*
RUN mv /usr/local/bin/maintenance/* /usr/local/bin \
    && rmdir /usr/local/bin/maintenance

# Refuse to start when an old-layout volume is mounted on /var/lib/postgresql (#464).
COPY ./compose/base/postgres/volume-guard /usr/local/bin/volume-guard
RUN chmod +x /usr/local/bin/volume-guard
ENTRYPOINT ["volume-guard"]
CMD ["postgres"]

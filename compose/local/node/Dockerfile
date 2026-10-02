# Dev server for the webpack frontend (#466). The tag must match .nvmrc's major
# (tests/test_node_runtime.py); the registry is named because podman does not
# assume Docker Hub for a short name (#456).
FROM docker.io/node:24-trixie-slim

WORKDIR /app

# Dependencies are installed here so they are cached; docker-compose.local.yml mounts the
# source tree over /app and keeps this node_modules in an anonymous volume.
COPY package.json package-lock.json ./
RUN npm ci

# No `USER`: like the django image, the container writes bundles and webpack-stats.json
# into the bind-mounted tree, and must not hit a UID mismatch with the host user.
EXPOSE 3000
CMD ["npm", "run", "dev"]

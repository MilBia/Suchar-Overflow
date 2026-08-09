---
description: Start the local development server using Docker Compose.
---

1. Start the containers in detached mode:
   ```bash
   just up
   ```
   Or, equivalently, with the compose file specified explicitly (required outside
   `just`, which sets `COMPOSE_FILE` for you — a bare `docker compose up -d` fails
   with "no configuration file provided" otherwise):
   ```bash
   docker compose -f docker-compose.local.yml up -d --remove-orphans
   ```

2. View the logs to ensure everything started correctly:
   ```bash
   just logs django
   ```
   (Press Ctrl+C to exit logs, the server will keep running)

3. Access the application:
   - Web App: http://127.0.0.1:8000
   - Mailpit: http://127.0.0.1:8025

4. To stop the server:
   ```bash
   just down
   ```

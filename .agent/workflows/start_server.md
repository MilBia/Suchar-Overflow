---
description: Start the local development server using Docker Compose.
---

1. Start the containers in detached mode:
   ```bash
   docker compose up -d --remove-orphans
   ```

2. View the logs to ensure everything started correctly:
   ```bash
   docker compose logs -f django
   ```
   (Press Ctrl+C to exit logs, the server will keep running)

3. Access the application:
   - Web App: http://127.0.0.1:8000
   - Mailpit: http://127.0.0.1:8025

4. To stop the server:
   ```bash
   docker compose down
   ```

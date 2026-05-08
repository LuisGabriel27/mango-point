# MangoPoint Backlog

This tracks the remaining work we still want after the recent validation,
alerting, treatment, and local database setup improvements.

## Recommended Order

1. Harden auth and production configuration.
   - Require a real `AUTH_SECRET_KEY` outside local development.
   - Warn or block default admin passwords in shared deployments.

2. Introduce database migrations.
   - Add Alembic or a simple migration workflow before the schema changes again.
   - Make local, demo, and future remote databases easier to upgrade safely.

3. Add a shared remote PostgreSQL/PostGIS database for team/demo deployment.
   - Keep native local PostgreSQL/PostGIS for development right now.
   - Later provision one shared PostGIS database so groupmates do not each need
     separate local data for demos.
   - Store credentials only in `.env` or deployment secrets, never in Git.
   - Add backup, role, and connection instructions once the host is chosen.

4. Broaden API and integration tests.
   - Cover simulation, observations, evaluation, alerts, auth, manual weather,
     orchard switching, and alert action workflow.

5. Split the dashboard into smaller modules.
   - Move auth, map, simulation controls, validation, monitoring, alerts,
     tree modal, and charts out of the large `dashboard/app.py`.

6. Continue docs and setup cleanup.
   - Keep setup instructions aligned with native PostgreSQL/PostGIS.
   - Keep validation caveats and weather-source labeling clear for defense.

-- Keep the alert table aligned with the SQLAlchemy model.
ALTER TABLE alert
    ADD COLUMN IF NOT EXISTS suggested_simulation_params JSONB;

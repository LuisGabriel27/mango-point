# MangoPoint Codex instructions

- Use the official, project-scoped `supabase` MCP connection when inspecting or changing the hosted Supabase project.
- Treat `supabase/migrations/*.sql` and `supabase/MangoPoint_Supabase_SQL_Editor.sql` as the source of truth for hosted database changes. Keep both forms aligned whenever the schema changes.
- Validate schema SQL locally before updating Supabase. Then run `python -m scripts.sync_supabase_schema --apply` and report whether the hosted schema changed.
- Never place Supabase database URLs, access tokens, service-role keys, or OAuth credentials in tracked files or frontend environment variables.
- Application code and UI-only changes do not require a Supabase schema update. Local durable data continues to synchronize through the existing cloud-sync service.

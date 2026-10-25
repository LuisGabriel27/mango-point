# Recoverable simulation History deletion

In **History**, choose the red **Delete** action on the saved simulation row.
The confirmation identifies its orchard, pest, engine, duration, date and run ID.
**Cancel**, Escape, Close or the backdrop leave it unchanged. Only the red
**Delete simulation** confirmation sends a deletion request.

Deletion removes the run from shared History, normal run loading, Excel exports
and Overview simulation counts. **Undo delete** restores it while the success
notice is available. Other application users see the same shared History after
refreshing. Browser-only rows require the API to be connected and the server
record to be available before deletion is enabled.

The server retains the simulation row, original request/response, random seed,
model version, weather, maps and timeline. Linked observations and alerts are
not removed. Deleting the currently displayed result clears its result view
without changing orchard or scenario controls. Existing field records remain
available independently. No simulation is automatically run by these actions.

## Persistence and API

- `DELETE /simulation/runs/{run_id}` marks the existing `status` as `deleted`.
- `POST /simulation/runs/{run_id}/restore` restores the original status.
- Both require an active authenticated account and lock the selected row during
  the update. Repeated delete/restore requests are idempotent. Running/pending
  simulations cannot be deleted.
- Existing `result_metadata.history_deletion` records the previous status,
  deletion time/user and later restoration time/user. Model evidence is retained.
- List responses include `deleted_run_ids` so another browser's old cache cannot
  reintroduce a deleted run. Cached results retain a deletion marker and their
  saved output. A missing/deleted server detail cannot fall back to old output.
- After the immediate Undo notice is dismissed/refreshed away, the retained run
  can still be restored through the authenticated restore endpoint by its ID.

No local or hosted schema migration is required: status and metadata columns
already exist. The existing transactional sync trigger queues the updated row
for ordinary cloud backup. This change does not run a manual sync or alter the
sync schedule. Restoring a cloud backup preserves the deleted status.

## Verification

Isolated API/service tests cover authentication, deletion, idempotence, restore,
running/missing runs, retained evidence, History filtering, exports and Overview.
Cache tests cover stale saves, recovery, retained deletion markers and storage
failure reporting. Browser checks use simulated records and responses; they do
not delete real simulations, create field observations, send messages or run a
forecast. They do not constitute a field-validation or model-accuracy result.

The full Python suite passed **988 tests** (one existing Starlette/httpx
deprecation warning), and the frontend unit suite passed **201 tests**. The
frontend production build passed with its existing large-bundle warning.
Evidence is under ignored `outputs/history-soft-delete-2026-10-19/`.

Eight isolated browser checks passed, covering both pests and both engines,
confirmation dismissal/focus, Delete/Undo, reload persistence, request failures,
duplicate-request prevention, cross-device deletion markers, missing details
and browser-storage failures. Desktop and 390 px dialog layouts were checked;
the narrow-layout checks open History through the existing desktop navigation
before resizing, because the current navbar hides its tab strip on phones.

A real PostgreSQL temporary-table check also passed for deletion/restoration,
list/detail filtering and retained evidence. Its transaction was rolled back;
it made no changes to actual simulation records or the database schema.

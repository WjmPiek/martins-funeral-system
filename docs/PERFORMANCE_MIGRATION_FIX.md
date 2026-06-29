# Performance Engine migration fix

This patch replaces `migrations/versions/v66_performance_engine.py`.

The previous migration expected a `permissions.description` column, but the Martins Funeral System database uses:

- `module`
- `action`
- `code`
- `label`
- `sort_order`

This fixed migration now inserts permissions using the existing schema and links them to roles safely.

## Deploy steps

1. Copy `migrations/versions/v66_performance_engine.py` into the project, replacing the existing file.
2. Commit and push to `development`.
3. Wait for Render to redeploy.
4. Run:

```bash
flask db current
flask db upgrade
flask db current
```

Expected final result:

```text
v66_performance_engine
```

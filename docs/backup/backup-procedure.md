# Backup Procedure

Two distinct things get backed up, for two different reasons:

| What | Protects against | Where |
|---|---|---|
| **Source files, before a change** | a bad edit | `C:\tmp\leadpilot-backups\<timestamp>_<label>\` **+** a git anchor commit |
| **The database** | data loss | `pg_dump` / Neon point-in-time restore |

`BACKUP.md` at the repo root covers server-side database backups for the
self-hosted Docker topology. **This file covers the per-change developer
procedure** and the Neon/Render topology actually in use.

---

## Part 1 — Per-change source backups

Run **before** modifying any file. Two independent backups, because they fail
differently: a git commit is worthless if you never made it, and a file copy is
worthless if you delete the directory.

### Why backups go OUTSIDE the repo

`C:\tmp\leadpilot-backups\`, not `./backups/`:

1. `git add -A` would otherwise commit every backup copy into history
   permanently — `.gitignore` does not exclude `*.backup_*`.
2. `.gitignore` **does** exclude `.env.*`, so a backup named `.env.backup`
   would be silently untracked — a backup you believe is in git but is not.
3. Backups are never deleted, so in-repo they accumulate forever.

### Backup 1 — file copies

```bash
TS=$(date +%Y%m%d_%H%M%S)
DEST="/c/tmp/leadpilot-backups/${TS}_<label>"
mkdir -p "$DEST"
for f in <every file you are about to touch>; do
  mkdir -p "$DEST/$(dirname "$f")"
  cp "$f" "$DEST/$f"
done
```

Relative paths are preserved inside `$DEST`, so restoring is a straight copy
back and two files with the same basename never collide.

### Backup 2 — git anchor commit

```bash
git add -A
git commit -m "BACKUP: Pre-<feature> — <timestamp>"
```

If the tree is already clean, make the anchor explicit rather than assuming
`HEAD` is obvious later:

```bash
git commit --allow-empty -m "BACKUP: Pre-<feature> anchor — <timestamp>"
```

### Restoration test — MANDATORY

**A backup that has not been restored is a hypothesis.** Restore every file to
a scratch directory and `diff` it against the original.

```bash
RESTORE="/c/tmp/leadpilot-restore-test/${TS}"
rm -rf "$RESTORE"; mkdir -p "$RESTORE"
FAIL=0
cd "$DEST"
for f in $(find . -type f | sed 's|^\./||'); do
  mkdir -p "$RESTORE/$(dirname "$f")"
  cp "$DEST/$f" "$RESTORE/$f"
  if diff -q "$RESTORE/$f" "<repo-root>/$f" >/dev/null 2>&1; then
    echo "  IDENTICAL  $f"
  else
    echo "  MISMATCH   $f"; FAIL=1
  fi
done
[ "$FAIL" -eq 0 ] && echo "backup is valid and restorable" || echo "BACKUP FAILED — STOP"
```

**If it fails: stop. Do not modify anything.**

### Restoring

```bash
# one file
cp "/c/tmp/leadpilot-backups/<TS>_<label>/app/api/auth.py" app/api/auth.py

# everything from that backup
cd "/c/tmp/leadpilot-backups/<TS>_<label>" && cp -r . "<repo-root>/"

# or via git
git reset --hard <anchor-commit>
```

### Existing backups

| Timestamp | Label | Anchor commit | Files |
|---|---|---|---|
| `20260829_170115` | `pre-email-verification` | `bd7d54c` | 16 — `app/config.py`, `app/db/models.py`, `app/api/auth.py`, `app/services/auth.py`, `app/core/production_guard.py`, `.env`, `.env.example`, `.env.production.example`, `render.yaml`, `requirements.txt`, `tests/integration/conftest.py`, and 5 frontend files. All diff-verified. |
| `20260829_183822` | `pre-tutorial-section` | `f307b68` | 5 — `app/main.py`, `app/db/models.py`, `app/api/admin.py`, `frontend/src/components/shell/nav.ts`, `frontend/src/lib/api/types.ts`. All diff-verified. |
| `20260829_212808` | `pre-ai-support-chat` | `5e5777a` | 12 — `app/main.py`, `app/config.py`, `app/core/config.py`, `app/db/models.py`, `app/api/admin.py`, `app/workers/celery_app.py`, `app/services/tutorials.py`, `tests/conftest.py`, `tests/test_celery_routing.py`, and 3 frontend files. All diff-verified. |
| `20260830_024655` | `pre-offline-activation` | *(see Feature 3 commit)* | 18 — `app/config.py`, `app/core/config.py`, `app/db/models.py`, `app/api/admin.py`, `app/api/tutorials.py`, `app/api/support.py`, `app/services/tutorials.py`, `app/services/support_chat.py`, `app/main.py`, `tests/test_tutorials.py`, `tests/test_support_chat.py`, `tests/conftest.py`, `frontend/e2e/tutorials.spec.ts`, and 5 more. 18/18 diff-verified. Covers the DB-backed tutorial catalogue (0018), mock AI mode, and the activation script. |

---

## Part 2 — Database backups

### Current topology

| Component | Host | Backup mechanism |
|---|---|---|
| PostgreSQL | **Neon** (free) | Neon's own history/PITR **+** manual `pg_dump` |
| Redis | **Upstash** (free) | none needed — cache/queue only |
| API + worker | Render (free) | stateless; redeploy from git |
| Frontend | Vercel | stateless static export |

Redis is deliberately not backed up: Celery replays pending tasks on restart
and the cache repopulates. **Rate-limit counters reset**, which is harmless.

> **Neon free tier has a limited history window.** Do not treat it as your only
> backup. Take a manual dump before any schema change.

### Manual dump — always before a migration

```bash
TS=$(date +%Y%m%d_%H%M%S)
pg_dump "<DIRECT (non-pooled) Neon URL>" -Fc -f "leadpilot_${TS}.dump"

# verify it is readable and non-trivial before trusting it
pg_restore --list "leadpilot_${TS}.dump" | head
ls -lh "leadpilot_${TS}.dump"
```

Use the **DIRECT** endpoint (no `-pooler` in the host), the same one
`MIGRATION_DATABASE_URL` points at. Long-running operations through PgBouncer
behave differently.

Store dumps **outside the repo** — they contain every user's data. `pg_dump`
requires PostgreSQL client tools; on Windows they ship with the PostgreSQL
installer or `choco install postgresql`.

### Restore

```bash
pg_restore --clean --if-exists -d "<DIRECT Neon URL>" "leadpilot_<TS>.dump"
```

`--clean --if-exists` drops existing objects first. **This overwrites the
target database.** Restore into a scratch database first and check row counts.

### Verifying a restore

```sql
SELECT version_num FROM alembic_version;                     -- expected revision
SELECT count(*) FROM users;                                  -- matches pre-dump
SELECT count(*) FROM users WHERE email_verified = false;     -- expected unverified
SELECT count(*) FROM strategies;
SELECT count(*) FROM leads;
```

---

## Part 3 — Migration rollback

Migrations are the one change that a source rollback alone cannot undo.

### Before any migration

1. `pg_dump` (above) — **verify the dump file**, do not just create it.
2. Note the current revision:
   ```sql
   SELECT version_num FROM alembic_version;
   ```
3. Read the migration's `downgrade()` and confirm it is not lossy. If it is,
   the docstring must say so.

### Applying

```bash
python -m app.db.migrate       # advisory-locked; safe with multiple replicas
```

The lock only serialises on the **DIRECT** endpoint. Measured 2026-08-20
against live Neon: through the pooler, a second migrator acquired a lock the
first was holding.

### Rolling back one revision

```bash
alembic downgrade <previous_revision_id>
```

### Verified rollbacks

| Revision | Downgrade | Lossy? |
|---|---|---|
| `0015_email_verification` | Verified on PostgreSQL 16 and SQLite: drops `users.email_verified`, `users.email_verified_at`, `email_verification_tokens`; all user rows intact. | **Yes.** Discards *which* users had verified — the old schema has nowhere to keep it. Re-upgrading backfills everyone to verified again: safe (nobody locked out) but not the same data. |
| `0016_tutorial_progress` | Verified on PostgreSQL 16: drops `tutorial_progress`; `users` and every other table intact. | **Yes.** Discards all tutorial watch progress and therefore every earned badge (badges are derived from progress, so there is nothing else to lose). |
| `0017_ai_support_chat` | Verified on PostgreSQL 16: drops `chat_sessions`, `chat_messages`, `support_tickets`; `tutorial_progress` and `users` intact. | **Yes, and worse than the others.** Discards all chat history **and every support ticket, including open ones a user is waiting on**. Take a dump first. |
| `0018_tutorial_catalogue` | Verified on PostgreSQL 16 (2026-08-30): full `0001 -> 0018` chain, then `downgrade 0017`, then forward again. Drops `tutorial_catalogue`; `tutorial_progress` and `users` intact, and the re-upgrade re-seeds all 9 rows. | **Yes.** The seed comes back, but every edit made through the admin UI does not: `youtube_id`s, retitled tutorials, publish state and any tutorial created after the migration live nowhere except this table. Progress rows survive (keyed by slug, no FK) and re-associate on re-upgrade. Take a dump first. |

---

## Part 4 — Emergency levers

Ordered by cost. Try them in this order.

| # | Situation | Action | Cost |
|---|---|---|---|
| 1 | Users locked out by email verification | `REQUIRE_EMAIL_VERIFICATION=false` in the Render dashboard, restart | seconds, zero data change |
| 2 | Bad code deploy | `git revert` / `git reset --hard <anchor>`, redeploy | one deploy |
| 3 | Bad migration, data intact | `alembic downgrade <prev>` | minutes |
| 4 | Data loss | `pg_restore` from the last verified dump | everything since the dump |

**Always try 1 before 3, and 3 before 4.**

---

## Checklist

Before any change:

- [ ] Backup 1 — file copies to `C:\tmp\leadpilot-backups\<TS>_<label>\`
- [ ] Backup 1 restoration test — every file `diff`s IDENTICAL
- [ ] Backup 2 — git anchor commit, hash recorded
- [ ] If the change includes a migration: verified `pg_dump` taken
- [ ] Current alembic revision recorded
- [ ] Rollback procedure written down **before** the change, not after

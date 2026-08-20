# Releasing the clienthunter SDK

CI does almost everything. Your manual steps are three lines.

---

## Prerequisites (one-time setup)

1. **TestPyPI account** with `TWINE_TOKEN_TESTPYPI` secret in GitHub → Settings → Secrets.
2. **PyPI account** with `TWINE_TOKEN_PYPI` secret in GitHub → Settings → Secrets.
3. Both accounts have the `clienthunter` package name claimed.

---

## Release process (every time)

```bash
# 1. Decide what kind of change this is (patch / minor / major)
python scripts/bump_version.py patch

# 2. Review the commit that was just created
git log -1

# 3. Push the tag — this triggers the CI workflow
git push origin release/sdk-v<version>
```

That's it. CI runs four jobs in sequence:

| Job | What it does |
|---|---|
| build | `python -m build`, `twine check dist/*` |
| publish-testpypi | Uploads to test.pypi.org |
| smoke-test | Clean venv, installs from TestPyPI, runs `clienthunter --help` |
| publish-pypi | Uploads to pypi.org, creates GitHub Release |

---

## If a job fails

- **build fails** → fix the package structure, re-run `bump_version.py`.
- **smoke-test fails** → the package installs or CLI is broken. Fix, bump patch again, re-release.
- **publish-pypi fails** after smoke-test passes → token issue or PyPI rate limit. Re-run the failed job from the GitHub Actions UI.

CI never auto-pushes the git commit, so a failed release does not pollute the main branch.

---

## Versioning policy

```
MAJOR.MINOR.PATCH
  │      │     └─ bug fix, documentation, test-only change
  │      └─────── new feature (backward-compatible)
  └────────────── breaking API change
```

The SDK version tracks the backend API version. If a backend migration removes or renames an endpoint, bump MAJOR.

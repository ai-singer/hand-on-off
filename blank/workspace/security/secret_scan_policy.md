# Secret Scan Policy

## Security invariant

Creator Agent source, Git history, source archives, and deployable artifacts must
never contain live credentials or reusable authenticated session material.
Credentials are supplied only by the approved runtime secret store after an
artifact has passed release validation.

## Forbidden files

The following must not enter the repository or a deployment artifact:

- `.env` and environment-specific `.env.*` files; `.env.example` is allowed
  only when it contains placeholders and non-secret configuration;
- credential, secret, token, password, cookie, or session files;
- private keys, including PEM, OpenSSH, PKCS#12, and similar key material;
- nested `.git` directories or Git object databases;
- opaque workspace snapshots that have not passed recursive archive scanning.

## Forbidden content

The release scanner rejects common private-key blocks, API-key and access-token
formats, GitHub tokens, AWS access-key IDs, JWTs, and non-placeholder assignments
to security-sensitive variables such as `API_KEY`, `TOKEN`, `SECRET`,
`PASSWORD`, `GITHUB_KEY`, `COOKIE`, and `SESSION`.

The scanner reports only the path, rule, and line number. It must never print
the matching secret value.

## Required release checks

Two scan scopes are mandatory, because the workspace scope alone is not enough:
the repository root can carry untracked-by-policy snapshots that never appear
under `blank/workspace/`.

```powershell
# Scope 1 - the deployable workspace
python security/secret_scan.py .

# Scope 2 - the whole repository, including history snapshot directories
python security/secret_scan.py <repository-root>

python -m unittest discover -s tests -v
python -m compileall .
```

Scope 2 is the check that catches a tracked archive such as
`new/workspace.tar.gz`. Any `*.tar.gz` or `*.zip` runtime snapshot reachable from
the repository root must be treated as a release input and must pass a full
recursive scan before a tag or a source archive is published.

`scripts/package_workspace.ps1` runs the scanner before packaging and scans the
completed archive again. Any finding or unscannable archive member fails the
release. A failed post-package scan removes the newly generated unsafe artifact.

## Distribution surfaces

A tag is a distribution surface, not only a label. GitHub's automatic source
archive for a tag
(`https://github.com/<owner>/<repo>/archive/refs/tags/<tag>.tar.gz`) contains the
entire repository tree at that commit. Therefore:

- a deployment entry must not point at a tag source archive while the repository
  root holds unscanned snapshots;
- prefer exporting the deployable subtree (`blank/workspace/`) or publishing an
  artifact that has passed the package scan and has a recorded SHA-256;
- `.gitignore` never protects an already tracked file; removing a tracked secret
  requires `git rm --cached` plus an authorized history rewrite, and history
  cleanup still never substitutes for credential rotation.

## Incident response

When a secret reaches Git or a release surface:

1. revoke and rotate the credential or session before relying on repository
   cleanup;
2. identify every branch, tag, release asset, cache, and clone that contains it;
3. remove the file from current state and rewrite affected history under an
   explicitly authorized coordinated procedure;
4. replace affected remote refs and invalidate cached or published artifacts;
5. rerun the scanner and record the cleaned commit, tag, and artifact hashes.

History cleanup does not revoke a credential and must not be reported as a
substitute for rotation.


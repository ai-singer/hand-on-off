# Release Security Gate

This gate exists because of a real incident: a tracked workspace snapshot
(`new/workspace.tar.gz`) containing plaintext credentials, reusable session
material and nested Git history was published on `main` and on the
`creator-agent-template-v0.1.0` tag. The repository was later cleaned and the tag
rebuilt, but the purged objects remained retrievable from GitHub by direct SHA.

Two lessons drive the rules below:

1. A secret scan that only covers the working tree cannot prove the
   **distribution surface** is clean.
2. Rewriting history is not the same as deleting data. A purge must be
   **verified**, not assumed.

The gate is fail-closed: any failing check blocks the release. It is a
documentation and process gate; it deliberately adds no runtime code.

```text
Gate 1  Current Tree Scan            -> what we are about to ship
Gate 2  Artifact Scan                -> what we actually built
Gate 3  Historical Exposure Probe    -> what we thought we removed
Gate 4  Deployment Source Validation -> where consumers get it from
```

## 1. Current Tree Scan

**Purpose:** no credential-bearing file is tracked or present in the tree that
is about to be tagged.

Scan the whole repository, not only the deployable workspace. The repository
root can carry snapshot directories that never appear under `blank/workspace/`.

```powershell
cd blank\workspace
python security/secret_scan.py .                          # deployable workspace
python security/secret_scan.py <repository-root>          # whole repository
python -m unittest discover -s tests -v
python -m compileall .
```

Also confirm no opaque snapshot is tracked without a passing recursive scan:

```bash
git ls-files | grep -E '\.(tar|tar\.gz|tgz|zip)$'
```

| Check | Pass criteria | Fail action |
| --- | --- | --- |
| Workspace scan | `Secret scan PASS`, exit 0 | Block release |
| Repository-root scan | `Secret scan PASS`, exit 0 | Block release; untrack and purge the offending path |
| Unit tests | `OK` | Block release |
| Compile check | exit 0 | Block release |
| Tracked archives | Every listed archive passes a recursive scan and is a declared release input | Block release |

Rules:

- `.gitignore` never protects an already tracked file. Untracking requires
  `git rm --cached` **plus** an authorized history rewrite.
- A tracked `*.tar.gz` runtime snapshot is treated as a release input and must
  pass a full recursive scan before a tag is created.
- Nested `.git` directories, `.env` files, cookie/session files and private
  keys are forbidden everywhere, including inside archives.

## 2. Artifact Scan

**Purpose:** the thing consumers download has been inspected, not just the
source it was built from.

```powershell
pwsh -File scripts/package_workspace.ps1
```

`package_workspace.ps1` already scans before packaging and again after, and
deletes the artifact if the post-package scan fails. Verify and record:

| Check | Pass criteria | Fail action |
| --- | --- | --- |
| Pre-package scan | `PASS` | Block packaging |
| Post-package scan | `PASS` | Delete artifact, block release |
| Artifact SHA-256 | Recorded in the release notes | Block release |
| Artifact content | Contains only the deployable subtree | Block release |

Every published artifact must have its SHA-256 recorded. An artifact without a
recorded hash is not a released artifact.

## 3. Historical Exposure Probe

**Purpose:** a previous purge is only closed when the purged objects are
demonstrably no longer retrievable. This is the check that Phase 5.2 lacked.

For every object recorded as purged, probe it. Run all three vectors; they can
disagree.

```bash
# 3a. raw file access by old commit SHA (HEAD only; do not download the body)
curl -sI "https://github.com/<owner>/<repo>/raw/<old-sha>/<path>"
curl -sI "https://raw.githubusercontent.com/<owner>/<repo>/<old-sha>/<path>"

# 3b. object metadata via the GitHub API
curl -s "https://api.github.com/repos/<owner>/<repo>/git/blobs/<old-blob>"

# 3c. can the old commit still be fetched by SHA?
git fetch origin <old-sha>
```

| Check | Pass criteria | Fail action |
| --- | --- | --- |
| 3a raw URL | `404` for every purged path | Open a cache-exposure item; see below |
| 3b blob API | `404` | Open a cache-exposure item |
| 3c fetch by SHA | Fails | Open a cache-exposure item |

If any vector returns `200`, the exposure is **still open**. A forced push does
not remove unreachable objects; GitHub documents that these commits "may still be
accessible elsewhere", including "directly via their SHA-1 hashes in cached
views", and that only GitHub Support can permanently remove cached views.

Escalation order, highest value first:

1. **Rotate the affected credentials.** The affected secrets must stop working;
   this is the only mitigation fully under the owner's control.
2. **Contact GitHub Support** to invalidate cached views and run server-side
   garbage collection. GitHub Support only assists with sensitive data where the
   risk cannot be mitigated by rotating the affected credentials, so state
   plainly whether rotation is possible.
3. **Delete and recreate the repository.** The only owner-side way to purge
   cached views definitively. Destructive: verify first that the repository has
   no forks, pull requests, issues or stars worth preserving.

Never report a history rewrite as "data removed" until this probe passes.

## 4. Deployment Source Validation

**Purpose:** consumers must never deploy a raw repository source archive.

A repository source archive (including GitHub's automatic
`/archive/refs/tags/<tag>.tar.gz`) contains the **entire tree at that commit** —
every snapshot directory, every non-deployable artifact. Distributing it means
distributing whatever the repository root happens to hold.

Required:

- Deployment sources must be either
  1. a **validated artifact** produced by `scripts/package_workspace.ps1` with a
     recorded SHA-256, or
  2. an explicit **deployable subtree export**:

     ```bash
     git archive --format=tar.gz --prefix=workspace/ \
       -o creator-agent-workspace.tar.gz \
       <tag>:blank/workspace
     ```

- A whole-repository tag archive may be used **only** after the repository-root
  scan in Gate 1 passes, and its SHA-256 must be recorded.

| Check | Pass criteria | Fail action |
| --- | --- | --- |
| Deployment entry document | Points at an artifact or subtree export | Block release |
| Source archive use | Only with a passing repository-root scan and recorded hash | Block release |
| Published hash | Matches the artifact the consumer receives | Block release |

Deployment documents must state the expected commit SHA, and that SHA must
resolve. After an authorized history rewrite, every recorded SHA changes and all
release documents must be updated in the same change.

## 5. Pre-Release Checklist

```text
[ ] Gate 1  workspace scan PASS
[ ] Gate 1  repository-root scan PASS
[ ] Gate 1  unit tests PASS and compile check PASS
[ ] Gate 1  every tracked archive is a declared, scanned release input
[ ] Gate 2  pre-package scan PASS
[ ] Gate 2  post-package scan PASS
[ ] Gate 2  artifact SHA-256 recorded
[ ] Gate 3  historical exposure probe returns no 200 for purged objects
[ ] Gate 4  deployment entry points at an artifact or subtree export
[ ] Gate 4  all commit/tag SHAs in release documents resolve
[ ] Tag created only after all of the above
```

Any unchecked or failing item blocks the tag. Incidents are recorded as a new
dated status document under `docs/`; do not silently edit a prior incident
report — mark it superseded and keep its findings intact.

## References

- `secret_scan_policy.md` — scanner scope, forbidden files and content, incident
  response order
- `../docs/CACHE_EXPOSURE_STATUS.md` — current cache-exposure state
- `../docs/CREDENTIAL_ROTATION_FINAL_STATUS.md` — rotation tracking
- `../docs/BACKUP_DISPOSAL_STATUS.md` — on-disk copy disposal

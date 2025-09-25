# Git cleanup reference — ignore IDE indices and remove .vs

A compact reference you can keep in the repo. Follow these steps to stop committing Visual Studio indices and other local DBs, remove any tracked IDE state if needed, and commit a clean .gitignore.

---

## 1. Inspect current repo state

Purpose: see what Git currently sees (tracked vs untracked) and detect any IDE/index files currently tracked.

PowerShell commands (run from repo root):
```powershell
# Show concise status
git status --porcelain=v1

# List tracked files that match common IDE/index patterns (prints a message if none)
git ls-files | Select-String -Pattern '\.vs|CopilotIndices|FileContentIndex|\.db|\.db-shm|\.db-wal' || Write-Host "No matching tracked items"
```

What to look for:
- Lines prefixed with `??` = untracked (safe to ignore or add)
- Any output from the `git ls-files` line = those items are tracked and need removal from the index

---

## 2. Create or update .gitignore

Purpose: ensure local IDE state is never staged or committed again.

PowerShell command (creates or replaces .gitignore in repo root):
```powershell
@"
# Ignore Visual Studio local state
.vs/
.vscode/
*.vsix

# Ignore IDE index/cache DBs and Copilot indices
**/CopilotIndices/
**/FileContentIndex/
*.db
*.db-shm
*.db-wal

# OS and editor temp files
Thumbs.db
.DS_Store
*.log
"@ | Set-Content -Path .gitignore -Encoding UTF8
```

Why these patterns:
- `.vs/` and `.vscode/` are local IDE state folders; they change frequently and are environment-specific.
- `CopilotIndices` / `FileContentIndex` and `*.db*` are local caches and indexes that should not be in VCS.
- OS/editor temp files and logs are noise and often contain sensitive or ephemeral data.

---

## 3. Add and commit .gitignore (and desired files)

Purpose: apply the ignore rules and commit other intended changes (e.g., docs).

PowerShell commands:
```powershell
git add .gitignore
git commit -m "chore: ignore IDE indices and local DBs (.vs, CopilotIndices, DB files)"

# If you want to add a specific file (example: docs/logging_standard.md)
git add docs/logging_standard.md
git commit -m "docs: add logging_standard"
```

Notes:
- If `git add .gitignore` shows no changes, the file may already exist with the same contents.
- Only commit files you intend to keep under version control.

---

## 4. Verify and push

Purpose: confirm the repo is clean and push changes to remote.

PowerShell commands:
```powershell
git status --porcelain=v1

# Confirm no IDE/index files are tracked
git ls-files | Select-String -Pattern '\.vs|CopilotIndices|FileContentIndex|\.db' || Write-Host "No IDE/index files tracked"

# Push commit(s)
git push origin main
```

What success looks like:
- `git status` shows no unintended tracked IDE files.
- The `git ls-files` check prints the fallback message ("No IDE/index files tracked").

---

## 5. If IDE/index files are already tracked (remove from index only)

Purpose: remove tracked IDE/index files from history going forward but keep them on disk.

Run these only if `git ls-files` in step 1 listed tracked items under `.vs` or similar.

PowerShell commands:
```powershell
# Remove tracked .vs folder from index only (keeps files locally)
git rm --cached -r .vs
git commit -m "chore: remove tracked .vs IDE files from repo (retain locally)"

# Generic removal for matched tracked items (safe: uses --ignore-unmatch)
git ls-files | Select-String -Pattern 'CopilotIndices|FileContentIndex|\.db(\b|-shm|-wal)?' |
  ForEach-Object { git rm --cached --ignore-unmatch -- "$($_.ToString().Trim())" }

git commit -m "chore: remove tracked IDE index/db files from repo (retain locally)"
```

Caveats:
- These commands do not delete local files; they only stop them being tracked by Git.
- If large binaries were committed historically and you need them removed from repo history, use `git filter-repo` or BFG — this rewrites history and requires coordination with collaborators.

---

## 6. Handling permission or file-lock errors

Symptoms: `Permission denied` when accessing files in `.vs` (or errors when staging/removing).

Steps:
1. Close Visual Studio and any related background processes (language servers, indexers).
2. Retry the git commands. If still locked:
   - Reboot, or
   - Use Sysinternals Process Explorer to find and close the process holding the handle.
3. Check file/folder permissions:
   - Right-click → Properties → Security; ensure your user has Read/Write.
4. Temporarily disable antivirus or exclude the `.vs` folder if it interferes.

---

## 7. Optional: if you accidentally committed large DBs and want to purge them

This is advanced and destructive for history—coordinate with collaborators.

Suggested tools: `git filter-repo` (recommended) or `BFG Repo-Cleaner`.

High-level steps (do not run without reading docs and coordinating):
- Install filter-repo
- Rewrite history to remove patterns (e.g., `.vs/`, `*.db`)
- Force-push rewritten branches
- Notify collaborators to re-clone or rebase against rewritten history

---

## 8. Troubleshooting checklist

- Are you in the repo root? Run `pwd` (PowerShell) to confirm.
- Is Visual Studio open? Close it before git operations to avoid locking files.
- Did `git ls-files` show tracked items? If not, .gitignore is sufficient.
- If GitHub Desktop shows staged files but Git CLI doesn’t, ensure both are pointed at the same working folder and branch.

---

# tools/ — vendored third-party tooling (NOT committed)

This directory holds external security tools (nmap, nuclei, ffuf, gobuster,
sqlmap, dirsearch, wordlists, ...). **Their binaries and data are intentionally
git-ignored** and must be provisioned locally — they are not stored in the repo.

History note: these binaries (~163MB, e.g. `nuclei.exe` ~95MB) were previously
committed and were purged from git history via `git filter-repo` to slim the
repository (`.git` 103MB → ~11MB). Only this README is tracked under `tools/`
(see the `/tools/` + `!/tools/README.md` rules in `.gitignore`).

## Provisioning

Fetch the tools into this directory using your platform's package manager or the
upstream release downloads, e.g.:

- nmap        — https://nmap.org/download.html
- nuclei      — https://github.com/projectdiscovery/nuclei/releases
- ffuf        — https://github.com/ffuf/ffuf/releases
- gobuster    — https://github.com/OJ/gobuster/releases
- sqlmap      — https://github.com/sqlmapproject/sqlmap
- dirsearch   — https://github.com/maurosoria/dirsearch

Python helper deps for the local tool wrappers live in
`requirements-local-tools.txt` / the `[localtools]` extra in `pyproject.toml`.

# Secure Notes API — CI/CD Pipeline Demo

A minimal **FastAPI** application used as a vehicle for demonstrating a
security-first CI/CD pipeline built on **GitHub Actions**.

The application itself is intentionally simple (a CRUD notes service backed by
an in-memory store) so that the pipeline structure, not the business logic, is
the focus. Every workflow file is heavily commented to explain *why* each
decision was made, not just *what* it does.

---

## Table of contents

1. [Application overview](#application-overview)
2. [Pipeline overview](#pipeline-overview)
3. [Security choices and rationale](#security-choices-and-rationale)
4. [Running locally](#running-locally)
5. [Running the pipeline yourself](#running-the-pipeline-yourself)
6. [Repository structure](#repository-structure)

---

## Application overview

`app/main.py` exposes a small REST API:

| Method   | Path              | Description          |
|----------|-------------------|----------------------|
| `GET`    | `/health`         | Liveness probe       |
| `POST`   | `/notes`          | Create a note        |
| `GET`    | `/notes`          | List all notes       |
| `GET`    | `/notes/{id}`     | Fetch a single note  |
| `DELETE` | `/notes/{id}`     | Delete a note        |

Input is validated via **Pydantic** models (field lengths enforced, no raw
dict access), and the app never logs user-supplied content — just internal IDs.

---

## Pipeline overview

Three workflow files live in `.github/workflows/`. They run on every push and
on every pull request targeting `main`.

```
Push / PR
    │
    ├─► ci.yml ──────────────────────────────────────────────────────────────┐
    │     │                                                                   │
    │     ├─ [lint]             ruff — style, import order, type hints        │
    │     ├─ [test]             pytest + coverage (≥ 80 % enforced)           │
    │     ├─ [sast]             bandit — Python AST security checks           │
    │     ├─ [dependency-audit] pip-audit — CVE scan of all pip deps          │
    │     └─ [secret-scan]      gitleaks — full-history secret detection      │
    │                                                                         │
    ├─► codeql.yml ──────────────────────────────────────────────────────────┤
    │     └─ GitHub's CodeQL engine — semantic security analysis              │
    │        Also runs on a weekly schedule (new queries, unchanged code)     │
    │                                                                         │
    └─► container.yml ───────────────────────────────────────────────────────┘
          ├─ Build Docker image (multi-stage, non-root user)
          ├─ Trivy — OS + library CVE scan (fails on CRITICAL/HIGH)
          └─ Trivy — Dockerfile misconfiguration scan
```

All SARIF results (bandit, CodeQL, Trivy) are uploaded to the repository's
**Security → Code scanning** tab so findings have a permanent, reviewable home
rather than disappearing into log noise.

---

## Security choices and rationale

### Why multiple tools instead of one?

No single tool covers the entire threat surface. Each tool here targets a
distinct layer:

| Tool       | Layer                      | What it catches                                               |
|------------|----------------------------|---------------------------------------------------------------|
| **ruff -S**| Source code (fast path)    | Obvious anti-patterns: `exec`, `subprocess(shell=True)`, etc. |
| **bandit** | Source code (deep SAST)    | Hardcoded passwords, insecure hash use, SQL injection patterns |
| **CodeQL** | Semantic / data-flow       | Taint flows across function calls; harder-to-find injection paths |
| **pip-audit** | Dependencies (SCA)      | Known CVEs in third-party packages via OSV + PyPI advisory DB |
| **gitleaks** | Git history              | Secrets accidentally committed (and later "deleted") in history |
| **Trivy**  | Container OS + libs        | CVEs in Debian packages and pip packages baked into the image |

### Why SARIF uploads?

SARIF (Static Analysis Results Interchange Format) is a vendor-neutral schema
that GitHub's Security tab understands natively. Uploading SARIF means:

- Findings persist across runs and are trackable over time.
- Each finding links directly to the offending line of code.
- Results from different tools are unified in one place, not scattered across
  individual job logs.

### Why fail on CRITICAL/HIGH in the container scan but not in the SCA audit?

The Trivy container scan exits with code 1 on CRITICAL or HIGH so the pipeline
**blocks merges** when a patchable OS or library CVE ships inside the image.

The `pip-audit` step uses `|| true` and uploads a report artifact instead.
This is intentional: during development, a transitive dependency may be
temporarily vulnerable without a fix available. Hard-failing in that case
would make the build permanently red through no fault of the application code.
The report is still surfaced as an artifact every run so it cannot be ignored —
it just does not block unrelated work while a fix is pending upstream.

In a production setup you would also add a vuln-allowlist file to `pip-audit`
to explicitly acknowledge known-and-accepted findings, rather than suppressing
them silently.

### Why gitleaks scans full history (`fetch-depth: 0`)?

A shallow clone (`fetch-depth: 1`) only sees the tip commit. If a secret was
committed three months ago and then "deleted" in a subsequent commit, it still
exists in the git object store and can be extracted. Full-depth scanning
catches historical leaks that a shallow scan would miss entirely.

### Why a multi-stage Dockerfile with a non-root user?

- **Multi-stage build**: The `builder` stage installs pip dependencies; the
  `runtime` stage copies only the installed packages and application source.
  Build tools (`gcc`, `pip`, etc.) never ship in the production layer, reducing
  the attack surface and image size.
- **Non-root user**: If the container is ever compromised, the attacker lands
  as `appuser` (UID 1001) with no shell and no home directory — not as root.
  This limits lateral movement within the container and makes container escape
  harder.
- **`--no-cache-dir`** on `pip install` avoids caching packages in the image
  layer, reducing image size without affecting functionality.

### Why `permissions: contents: read` at the workflow level?

GitHub Actions tokens are over-permissioned by default. By declaring the
minimum permissions each workflow needs, we follow the principle of least
privilege: a compromised third-party action can only read code, not push
commits or modify releases.

---

## Running locally

**Prerequisites:** Python 3.12+, Docker (optional).

### Install and run the API

```bash
# Clone the repo
git clone https://github.com/<your-username>/secure-cicd-pipeline-demo.git
cd secure-cicd-pipeline-demo

# Create a virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Start the development server
uvicorn app.main:app --reload
# → API running at http://127.0.0.1:8000
# → Interactive docs at http://127.0.0.1:8000/docs
```

### Run the tests

```bash
pytest
# Coverage report is printed to the terminal and written to coverage.xml
```

### Run the security tools locally

```bash
# Static analysis
bandit -r app/ --configfile pyproject.toml --severity-level medium

# Lint + format check
ruff check .
ruff format --check .

# Dependency audit
pip-audit --requirement requirements.txt

# Secret scan (requires gitleaks binary: https://github.com/gitleaks/gitleaks)
gitleaks detect --source . --verbose
```

### Build and run with Docker

```bash
docker build -t secure-notes:local .
docker run --rm -p 8000:8000 secure-notes:local
# → API running at http://localhost:8000

# Scan the image locally with Trivy
# (requires trivy: https://github.com/aquasecurity/trivy)
trivy image --severity CRITICAL,HIGH secure-notes:local
```

---

## Running the pipeline yourself

1. **Fork this repository** on GitHub (the Actions tab is disabled by default
   on forks; enable it under *Settings → Actions → Allow all actions*).
2. **Push any commit** to any branch — all three workflows trigger immediately.
3. View results:
   - **Actions tab** → select a workflow run to see per-job logs.
   - **Security tab → Code scanning** → bandit, CodeQL, and Trivy SARIF
     results appear here after their respective jobs complete.
   - **Actions tab → Artifacts** → download `coverage-xml` and
     `pip-audit-reports` from any run.

No secrets or external credentials are needed. The only token used is the
automatically-provisioned `GITHUB_TOKEN`, which is scoped to the repository.

---

## Repository structure

```
.
├── app/
│   ├── __init__.py
│   └── main.py              # FastAPI application
├── tests/
│   ├── __init__.py
│   └── test_main.py         # pytest test suite
├── .github/
│   └── workflows/
│       ├── ci.yml           # Lint · Test · SAST · SCA · Secret scan
│       ├── codeql.yml       # GitHub CodeQL semantic analysis
│       └── container.yml    # Docker build + Trivy image/config scan
├── Dockerfile               # Multi-stage, non-root runtime image
├── .dockerignore
├── .gitignore
├── pyproject.toml           # Tool config (ruff, bandit, pytest, coverage)
├── requirements.txt         # Runtime dependencies (pinned)
├── requirements-dev.txt     # Dev/test dependencies (pinned)
└── README.md                # You are here
```

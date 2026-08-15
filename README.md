# Call Analysis — Contact Center Intelligence

End-to-end contact center platform on the **NVIDIA free AI stack** (hosted NIM via [build.nvidia.com](https://build.nvidia.com)):

**Ingest → ASR (Whisper) → multi-speaker diarization → PII scrub → multi-agent analysis → NVIDIA-themed dashboard**

## ��� Features

### Core Pipeline
- **Audio Ingestion**: Upload `.m4a`, `.wav`, `.mp3`, `.ogg`, `.flac` recordings
- **ASR (Speech-to-Text)**: faster-whisper with GPU→CPU fallback (tiny/base/small/medium/large-v3)
- **Speaker Diarization**: Heuristic turn-taking (2-4 speakers) with optional pyannote.audio integration
- **PII Detection & Redaction**: Regex + ML-based detection for emails, phones, credit cards, SSN, Aadhaar, account numbers
- **Multi-Agent Analysis**: 6 specialized AI agents powered by NVIDIA NIM (Llama-3.1-8B-Instruct)
- **Interactive Dashboard**: Real-time waveform, sentiment charts, scorecards, interactive transcript, RAG copilot

### AI Agents
| Agent | Role |
|--------|------|
| **QA Scorecard** | Agent performance scoring (0-100) & coaching tips |
| **Compliance & Risk** | Policy/privacy/risk flags with severity levels |
| **Sentiment & Emotion** | Emotional vectors + timeline chart |
| **Root Cause & Intent** | Why the customer called + resolution tracking |
| **CRM Action Items** | Follow-ups ready for CRM sync |
| **Call Copilot (RAG)** | Supervisor Q&A grounded in the call |

### Production Features
- ��� **Authentication**: JWT + API Keys with RBAC (Admin/Analyst/Viewer)
- ��� **Multi-tenancy**: Organizations with isolated data
- ��� **Observability**: OpenTelemetry tracing, Prometheus metrics, Grafana dashboards
- ��� **Async Processing**: Celery + Redis job queue with retries & circuit breakers
- ������ **Database**: PostgreSQL with Alembic migrations
- ������ **Security**: Rate limiting, CORS, security headers, input validation
- ��� **Containerization**: Docker + Docker Compose with full stack
- ��� **Windows Installer**: PyInstaller + NSIS for standalone EXE

## ��� Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- ffmpeg (for audio conversion)
- NVIDIA API key (free at [build.nvidia.com](https://build.nvidia.com))

### 1. Clone & Configure
```powershell
git clone <repo>
cd call-analysis-project
copy .env.example .env
# Edit .env with your NVIDIA_API_KEY and database credentials
```

### 2. Install Dependencies
```powershell
python -m pip install -r requirements.txt
python -m pip install -e ".[prod]"
```

### 3. Initialize Database
```powershell
python -m call_analysis.init_db
# Or run migrations:
python -m call_analysis.migrate upgrade head
```

### 4. Start Services
```powershell
# Terminal 1: API Server
python -m call_analysis.serve

# Terminal 2: Celery Worker
python -m call_analysis.worker

# Terminal 3: Celery Beat (scheduler)
celery -A call_analysis.celery_app beat --loglevel=INFO
```

### 5. Access Dashboard
Open http://127.0.0.1:8787/ — upload a recording, **Import 1 sample**, or **Import batch (3)**.

## ��� Docker Deployment (Recommended)

```yaml
# docker-compose.yml includes:
# - PostgreSQL
# - Redis
# - API (4 workers)
# - Celery Workers (2 replicas)
# - Celery Beat
# - OpenTelemetry Collector
# - Prometheus + Grafana
```

```powershell
# Set required environment variables
$env:NVIDIA_API_KEY = "nvapi-..."
$env:DB_PASSWORD = "secure-password"
$env:AUTH_SECRET_KEY = "your-32-char-secret"

docker-compose up -d
```

Access:
- Dashboard: http://localhost:8787
- Grafana: http://localhost:3000 (admin/admin)
- Prometheus: http://localhost:9090

## ��� Configuration

Key environment variables (see `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| `NVIDIA_API_KEY` | NVIDIA NIM API key | *required* |
| `DB_HOST` | PostgreSQL host | `localhost` |
| `DB_PASSWORD` | PostgreSQL password | `changeme` |
| `REDIS_HOST` | Redis host | `localhost` |
| `AUTH_SECRET_KEY` | JWT signing key (32+ chars) | *auto-generated* |
| `ENVIRONMENT` | `development` \| `staging` \| `production` | `development` |
| `ASR_MODEL_SIZE` | Whisper model | `base` |
| `DIARIZATION_PROVIDER` | `heuristic` \| `pyannote` | `heuristic` |

## ��� API Endpoints

### Authentication
```
POST   /api/auth/login          - Get JWT token
GET    /api/auth/me             - Current user info
```

### Organizations (Admin)
```
POST   /api/organizations       - Create organization
GET    /api/organizations       - List organizations
GET    /api/organizations/{id}  - Get organization
PATCH  /api/organizations/{id}  - Update organization
```

### Users (Admin)
```
POST   /api/users               - Create user
GET    /api/users               - List users
```

### API Keys (Analyst+)
```
POST   /api/api-keys            - Create API key (returns secret once)
GET    /api/api-keys            - List API keys
DELETE /api/api-keys/{id}       - Revoke API key
```

### Calls
```
GET    /api/analytics           - Fleet analytics
GET    /api/calls               - List calls (paginated)
GET    /api/calls/{id}          - Get call details
POST   /api/calls/upload        - Upload recording
POST   /api/calls/import-local  - Import from local path
POST   /api/calls/{id}/analyze  - Re-analyze call
POST   /api/calls/{id}/copilot  - Ask copilot question
DELETE /api/calls/{id}          - Delete call
```

### Webhooks (Admin)
```
POST   /api/webhooks            - Create webhook
GET    /api/webhooks            - List webhooks
DELETE /api/webhooks/{id}       - Delete webhook
```

## ��� Testing

```powershell
# Unit tests
python -m pytest tests/ -v

# With coverage
python -m pytest tests/ --cov=call_analysis --cov-report=html

# Integration tests (requires services)
python -m pytest tests/ -m integration -v
```

## ������ Windows Desktop App (Python + Electron)

Ship the full dashboard as a native Windows app: an **Electron shell** that spawns
the **Python backend** as a child process, waits for `/api/health`, then loads the
NVIDIA-themed dashboard in a desktop window.

```
┌───────────────────────────────────────────────┐
│  Electron shell (main.js)                     │
│  ├─ spawns Python backend (uvicorn on 127.0.0.1)
│  ├─ polls /api/health until ready             │
│  └─ loads dashboard in BrowserWindow          │
└───────────────────────────────────────────────┘
```

### Run in development

```powershell
# Terminal 1: Electron app (spawns the backend automatically)
cd electron
npm install
npm start
```

Requires `python` on `PATH` (or set `CALL_ANALYSIS_PYTHON`). The app finds a
free port, starts the server, and stores data under the OS user-data folder
(`%APPDATA%\Call Analysis\data`).

### Build the installer (NSIS)

```powershell
# Full pipeline: icon → PyInstaller backend → electron-builder NSIS
python build_electron.py

# Unpacked dir only (faster iteration)
python build_electron.py --dir

# Reuse an existing backend build / node_modules
python build_electron.py --skip-backend --skip-npm
```

Output:
- Backend bundle: `dist/backend/CallAnalysisBackend/`
- App + installer: `dist/desktop/CallAnalysis-Setup-<version>.exe`

### Configuration in the desktop app

- **NVIDIA API key**: set `NVIDIA_API_KEY` in your environment, or drop a `.env`
  file next to the packaged backend (`%APPDATA%\Call Analysis\backend-cwd\.env`).
  Get a free key at https://build.nvidia.com
- **Data location**: `%APPDATA%\Call Analysis\data` (uploads, calls, audio).
- **First launch** may take a minute while the Whisper model downloads and
  ffmpeg warms up — the splash screen streams backend logs so you can watch.

### Why Electron + Python?

| Layer | Role |
|-------|------|
| **Electron** | Native window, taskbar/tray integration, offline-friendly shell |
| **Python (uvicorn)** | ASR (Whisper), diarization, PII scrub, NVIDIA NIM agents, file store |
| **Dashboard** | Waveform viewer, sentiment charts, agent scorecards, interactive transcript, RAG copilot |

## ������ Building Windows Installer (standalone EXE, no Electron)

```powershell
# Install build dependencies
pip install pyinstaller

# Build executable
python build_windows.py

# Output: dist/CallAnalysis.exe
# Run: dist/CallAnalysis.exe

# Create NSIS installer (requires NSIS installed)
makensis installer.nsi
# Output: CallAnalysis-Setup-0.4.0.exe
```

## ��� Project Structure

```
call-analysis-project/
├── src/call_analysis/
│   ├── api/              # FastAPI REST API
│   ├── audio/            # ASR, diarization, preprocessing
│   ├── agents/           # AI agents (QA, compliance, sentiment, etc.)
│   ├── pipeline/         # End-to-end processing runner
│   ├── pii/              # PII detection & redaction
│   ├── web/              # Dashboard (HTML/CSS/JS)
│   ├── alembic/          # Database migrations
│   ├── tasks.py          # Celery background tasks
│   ├── celery_app.py     # Celery configuration
│   ├── auth.py           # JWT + API key authentication
│   ├── config.py         # Pydantic Settings config
│   ├── database.py       # SQLAlchemy + async session
│   ├── logging_config.py # Structured logging
│   ├── telemetry.py      # OpenTelemetry setup
│   ├── redis_client.py   # Redis utilities
│   ├── models.py         # SQLAlchemy ORM models
│   ├── schemas.py        # Pydantic API schemas
│   ├── serve.py          # Server entry point
│   ├── worker.py         # Celery worker entry point
│   ├── init_db.py        # DB initialization
│   ├── migrate.py        # Alembic wrapper
│   └── cli.py            # CLI tools
├── tests/                # Unit & integration tests
├── grafana/              # Grafana dashboards & datasources
├── Dockerfile            # Multi-stage production image
├── docker-compose.yml    # Full stack deployment
├── pyproject.toml        # Modern Python packaging
├── requirements.txt      # Production dependencies
├── build_windows.py      # PyInstaller build script
├── build_electron.py     # Desktop app build (backend + Electron NSIS)
├── installer.nsi         # NSIS installer script
├── electron/             # Electron desktop shell (main, preload, renderer)
├── tools/                # Icon generator
├── start.ps1 / start.bat # Windows launchers
��── .env.example          # Configuration template
```

## ��� Security Considerations

- **Never commit `.env`** — contains secrets
- **Rotate `AUTH_SECRET_KEY`** periodically in production
- **Use HTTPS** in production (reverse proxy with TLS)
- **Restrict CORS origins** to your domains
- **Enable rate limiting** to prevent abuse
- **Audit logs** via `call_events` table
- **PII is redacted** before LLM processing

## ��� Monitoring

The platform exposes Prometheus metrics at `/metrics`:
- `calls_processed_total` — Counter by status
- `call_processing_duration_seconds` — Histogram
- `api_requests_total` — Counter by method/path/status
- `api_request_duration_seconds` — Histogram
- `active_jobs` — Gauge
- `queue_depth` — Gauge per queue
- `system_cpu_percent`, `system_memory_percent` — System metrics

Grafana dashboard included at `grafana/dashboards/call-analysis-platform.json`.

## ��� Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Run `ruff check . && mypy src/ && pytest`
5. Submit a PR

## ��� License

MIT License — see LICENSE file for details.

## ��� Acknowledgments

- [NVIDIA NIM](https://build.nvidia.com) for free hosted LLMs
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) for efficient ASR
- [FastAPI](https://fastapi.tiangolo.com) for the web framework
- [Celery](https://docs.celeryq.dev) for distributed task processing
# MSM — Sistema MIP de Productividad y Reconocimiento Comercial

[![CI](https://github.com/seguramoises-creator/MIP/actions/workflows/ci.yml/badge.svg)](https://github.com/seguramoises-creator/MIP/actions/workflows/ci.yml)

Aplicación web empresarial multipaís para medir, gestionar y reconocer el desempeño
de la fuerza de ventas farmacéutica (Representantes Médicos y Gerentes de Distrito).

> 📘 La documentación técnica completa está en [`CLAUDE.md`](CLAUDE.md).

## Stack

| Capa | Tecnología |
|------|------------|
| Backend | Python 3.13 · FastAPI · SQLAlchemy 2.0 · Alembic · SQL Server (pymssql) |
| Frontend | React 18 · TypeScript · Vite · Material UI v6 · Zustand · React Query |
| Auth | JWT (python-jose) · RBAC por roles |

## Módulos

Dashboard ejecutivo · Productividad · Cobertura Predictiva (4DX) · Coaching ·
Categorización Médica · Ranking RM/Gerentes · Reconocimientos · LSII · **Exámenes** ·
ETL · Reportes (Excel/PDF) · Administración.

## Cómo correr (desarrollo)

### Backend
```powershell
cd backend
.\venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```powershell
cd frontend
npm install
npm run dev
```

- Backend: http://localhost:8000 · Swagger: http://localhost:8000/api/v1/docs
- Frontend: http://localhost:3000

## Tests

```powershell
cd backend && python -m pytest -q
cd frontend && npm run build
```

El pipeline de CI (GitHub Actions) corre ambos en cada `push` a `master`.
El badge de arriba muestra el estado del último run.

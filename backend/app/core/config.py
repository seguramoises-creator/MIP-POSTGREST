"""
SCGCPR — Configuración Central
Carga y valida todas las variables de entorno usando Pydantic Settings.
FIX C-09: field_validator corregido a sintaxis Pydantic v2 (ValidationInfo).
FIX C-05: JWT_SECRET_KEY validado en startup — no permite el valor por defecto en producción.
"""
from functools import lru_cache
from typing import List
from pydantic import field_validator, ValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    # ── Aplicación
    APP_NAME: str = "SCGCPR"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_PREFIX: str = "/api/v1"

    # ── Servidor
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 1

    # ── Base de Datos
    DB_SERVER: str = "localhost"
    DB_PORT: int = 1433
    DB_NAME: str = "SCGCPR"
    DB_USER: str = "sa"
    DB_PASSWORD: str = ""
    DATABASE_URL: str = ""

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def build_db_url(cls, v: str, info: ValidationInfo) -> str:
        """FIX C-09: usa info.data (Pydantic v2) en lugar de values.data (v1)."""
        if v:
            return v
        data = info.data  # Pydantic v2: ValidationInfo.data
        return (
            f"mssql+pymssql://{data.get('DB_USER')}:{data.get('DB_PASSWORD')}"
            f"@{data.get('DB_SERVER')}:{data.get('DB_PORT')}/{data.get('DB_NAME')}"
        )

    @property
    def DB_ENGINE(self) -> str:
        """Dialecto de BD derivado del DATABASE_URL: 'postgres' o 'mssql'.
        Usado por las (pocas) ramas de SQL crudo que aún dependen del dialecto."""
        url = (self.DATABASE_URL or "").lower()
        return "postgres" if ("postgres" in url or "psycopg" in url) else "mssql"

    # ── JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str, info: ValidationInfo) -> str:
        """FIX C-05: Rechaza el secreto por defecto en producción."""
        env = info.data.get("APP_ENV", "development")
        if env == "production" and v in ("change-me-in-production", "", "secret"):
            raise ValueError(
                "JWT_SECRET_KEY inseguro en producción. "
                "Defina una clave de al menos 32 caracteres en .env"
            )
        if len(v) < 16:
            raise ValueError("JWT_SECRET_KEY debe tener al menos 16 caracteres.")
        return v

    # ── CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "https://sistemamip.com",
        "https://www.sistemamip.com",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json
                return json.loads(v)
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    # ── Hosts permitidos (TrustedHostMiddleware, solo aplica en producción)
    # Debe incluir el dominio público servido por IIS/nginx (proxy inverso).
    ALLOWED_HOSTS: List[str] = [
        "sistemamip.com",
        "www.sistemamip.com",
        "localhost",
        "127.0.0.1",
    ]

    @field_validator("ALLOWED_HOSTS", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json
                return json.loads(v)
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    # ── Proxy inverso (IIS/ARR, nginx) — usado por los scripts de arranque
    # para indicarle a uvicorn que confíe en los encabezados X-Forwarded-*
    # enviados por el proxy. No es leído directamente por uvicorn desde aquí;
    # ver start_produccion.ps1 / msm-backend.service (--proxy-headers).
    FORWARDED_ALLOW_IPS: str = "127.0.0.1"
    PUBLIC_BASE_URL: str = "https://sistemamip.com"

    # ── Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Mail (sección 18 CLAUDE.md — pendiente "Notificaciones por correo")
    # MAIL_SERVER vacío = notificaciones deshabilitadas (no se intenta conectar).
    # Esto permite que el resto del sistema funcione normalmente en entornos
    # de desarrollo/pruebas sin SMTP configurado — ver notification_service.
    MAIL_SERVER: str = ""
    MAIL_PORT: int = 587
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_FROM: str = "noreply@empresa.com"
    MAIL_FROM_NAME: str = "Sistema MIP — SCGCPR"
    MAIL_TLS: bool = True
    MAIL_SSL: bool = False

    # ── ETL dirs
    ETL_UPLOAD_DIR: str = "uploads"
    ETL_PROCESSED_DIR: str = "processed"
    ETL_ERROR_DIR: str = "errors"
    ETL_MAX_FILE_SIZE_MB: int = 50

    # ── Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/scgcpr.log"

    # ── Archivos
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # ── Reportes
    REPORTS_DIR: str = "reports"

    # ── Módulo de Exámenes — IA (Fase 3)
    ANTHROPIC_API_KEY: str = ""
    EXAM_AI_MODEL: str = "claude-sonnet-4-6"
    # Modo DEMO: genera preguntas localmente (sin llamar a Claude ni gastar API).
    # Útil para probar el flujo completo sin créditos. Apagar (false) en producción.
    EXAMEN_IA_DEMO: bool = False

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Odoo PO Kanban"
    database_url: str = "sqlite:///./po_kanban.db"
    webhook_allowed_ips: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def allowed_ip_list(self) -> list[str]:
        return [ip.strip() for ip in self.webhook_allowed_ips.split(",") if ip.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()

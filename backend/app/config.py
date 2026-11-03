from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Odoo PO Kanban"
    database_url: str = "sqlite:///./po_kanban.db"
    webhook_allowed_ips: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Odoo JSON-RPC connection (set these in your .env or server environment)
    odoo_url: str = ""          # e.g. https://mycompany.odoo.com/jsonrpc
    odoo_db: str = ""           # Odoo database name
    odoo_user_id: int = 0       # Odoo numeric user ID
    odoo_api_key: str = ""      # Odoo API key (replaces password)

    @property
    def odoo_configured(self) -> bool:
        return bool(self.odoo_url and self.odoo_db and self.odoo_user_id and self.odoo_api_key)

    @property
    def allowed_ip_list(self) -> list[str]:
        return [ip.strip() for ip in self.webhook_allowed_ips.split(",") if ip.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()

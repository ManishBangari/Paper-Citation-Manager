from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_hostname: str 
    database_port: str 
    database_password: str 
    database_name: str 
    database_username: str 
    secret_key: str 
    algorithm: str
    access_token_expire_minutes: int
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = ""      # comma separated, e.g. "https://myapp.example.com"; empty means no browser origin is allowed

    model_config = SettingsConfigDict(env_file=".env")


    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

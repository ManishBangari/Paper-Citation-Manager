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

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()

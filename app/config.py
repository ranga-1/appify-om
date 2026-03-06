"""Configuration management for Appify Object Modeler Service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Service Configuration
    api_version: str = "v1"
    log_level: str = "INFO"
    environment: str = "development"
    
    # AWS Configuration
    aws_region: str = "us-west-1"
    aws_profile: str = "appify-unshackle"
    
    # Database Configuration
    db_secret_id: str = "appify/unshackle/tenants/admin"
    db_name: str = "tenants"  # Database containing tenant schemas
    core_db_secret_id: str = "appify/unshackle/core/db"  # unshackle_core database
    
    # Credential Cache Configuration (in seconds)
    credential_cache_ttl: int = 3600  # 1 hour
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# Global settings instance
settings = Settings()

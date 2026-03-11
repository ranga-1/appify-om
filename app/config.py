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
    use_local_credentials: bool = False  # Toggle for local development mode
    
    # Local Tenants Database Configuration (used when use_local_credentials=True)
    tenants_db_host: str = ""
    tenants_db_port: int = 5432
    tenants_db_name: str = ""
    tenants_db_username: str = ""
    tenants_db_password: str = ""
    
    # Local Core Database Configuration (used when use_local_credentials=True)
    core_db_host: str = ""
    core_db_port: int = 5432
    core_db_name: str = ""
    core_db_username: str = ""
    core_db_password: str = ""
    
    # AWS Secrets Manager Configuration (used when use_local_credentials=False)
    db_secret_id: str = "appify/unshackle/tenants/admin"
    db_name: str = "tenants"  # Database containing tenant schemas
    core_db_secret_id: str = "appify/unshackle/core/db"  # unshackle_core database
    
    # Credential Cache Configuration (in seconds)
    credential_cache_ttl: int = 3600  # 1 hour
    
    # Redis Configuration
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    redis_ssl: bool = False
    permission_cache_ttl: int = 300  # 5 minutes for permissions
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# Global settings instance
settings = Settings()

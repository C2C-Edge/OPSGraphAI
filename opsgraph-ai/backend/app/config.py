"""
Configuration settings for OpsGraph AI backend.
Uses Pydantic Settings for environment variable management.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # API Configuration
    app_name: str = "OpsGraph AI Service"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 5000
    
    # CORS Configuration
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000,*",
        description="Allowed CORS origins"
    )
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = Field(default=["*"])
    cors_allow_headers: list[str] = Field(default=["*"])
    
    # Gemini AI Configuration
    gemini_api_key: Optional[str] = Field(
        default=None,
        description="Google Gemini API key for AI parsing"
    )
    gemini_model: str = "gemini-3.6-flash"
    
    # Supabase Configuration
    supabase_url: Optional[str] = Field(
        default=None,
        description="Supabase project URL"
    )
    supabase_anon_key: Optional[str] = Field(
        default=None,
        description="Supabase anonymous key"
    )
    
    # Optimization Parameters
    cluster_radius_km: float = 1.5
    gap_radius_km: float = 5.0
    critical_severity_threshold: int = 4
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()

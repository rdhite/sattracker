from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Holds the application settings.
    Values can be loaded from environment variables.
    """
    tle_url: str = Field(
        "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle",
        description="URL for the TLE data source."
    )
    cache_dir: str = Field("cache", description="Directory to store cached files.")
    tle_cache_file: str = Field("starlink.tle", description="Filename for the TLE cache.")
    cache_expiration_hours: int = Field(24, description="Cache validity duration in hours.")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# Create a single, importable instance of the settings
settings = Settings()

"""Application configuration loaded from the environment."""

from functools import lru_cache
from importlib.metadata import version as package_version

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__version__ = package_version("permits")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PERMITS_", extra="ignore")

    version: str = __version__
    repo_url: str
    database_url: str = Field(validation_alias="DB_CONNECTION_STRING")
    cors_origins: str
    enrich_timeout: float
    backup_s3_uri: str = ""
    wikidata_sparql_api_url: str
    osm_sparql_api_url: str

    @property
    def user_agent(self) -> str:
        """Custom User-Agent with a link to the repo, used for every outbound call."""
        return f"permits/{self.version} ({self.repo_url})"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

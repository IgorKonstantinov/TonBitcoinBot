from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    API_ID: int
    API_HASH: str

    MIN_AVAILABLE_ENERGY: int = 100
    SLEEP_BY_MIN_ENERGY: list[int] = [1200, 3600]

    RANDOM_TAPS_COUNT: list[int] = [50, 100]
    SLEEP_BETWEEN_TAP: list[int] = [5, 10]

    USE_PROXY_FROM_FILE: bool = False

settings = Settings()



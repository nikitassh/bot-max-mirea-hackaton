from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MAX_BOT_TOKEN: str
    DATABASE_URL: str
    OPENROUTER_API_KEY: str
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini"

    class Config:
        env_file = ".env"


settings = Settings()

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    postgres_user: str
    postgres_password: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str
    postgres_schema: str = "smart tutor"

    class Config:
        env_file = ".env"

    @property
    def sqlalchemy_database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

settings = Settings()
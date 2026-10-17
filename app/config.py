from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    postgres_user: str
    postgres_password: str
    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_db: str
    postgres_schema: str = "smarttutor"
    image_base_path: str = r"E:\smart-tutor\images"
    ollama_url: str = "http://localhost:11434"
    chroma_path: str = "chroma_data"

    class Config:
        env_file = ".env"

    @property
    def sqlalchemy_database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

settings = Settings()
from typing import Optional

from pydantic import BaseSettings, BaseModel, AnyHttpUrl


class OAuth(BaseModel):
    client_id: str
    client_secret: str
    redirect_uri: AnyHttpUrl


class Redis(BaseModel):
    host: str = 'localhost'
    port: int = 6379
    db: Optional[int] = None


class Settings(BaseSettings):
    api_token: str
    log_level: str = 'DEBUG'

    yc_oauth_token: Optional[str] = None
    yc_folder_id: Optional[str] = None
    oauth: Optional[OAuth] = None

    redis: Redis = Redis()
    chat_id_permitted_list: list[int] = []

    class Config:
        env_file = '.env'
        env_nested_delimiter = '__'


settings = Settings()

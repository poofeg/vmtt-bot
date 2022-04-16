from pydantic import BaseSettings


class Settings(BaseSettings):
    api_token: str
    log_level: str = 'DEBUG'

    yc_oauth_token: str
    yc_folder_id: str

    chat_id_permitted_list: list[int] = []

    class Config:
        env_file = '.env'


settings = Settings()

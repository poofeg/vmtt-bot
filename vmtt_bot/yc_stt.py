import io
from datetime import datetime, timezone
from typing import Optional, Awaitable, Union

import aiohttp
from aiohttp import hdrs
from pydantic import BaseModel


def to_camel(snake_str: str) -> str:
    first, *others = snake_str.split('_')
    return ''.join([first.lower(), *map(str.title, others)])


class YcBaseModel(BaseModel):
    class Config:
        alias_generator = to_camel
        allow_population_by_field_name = True


class IamToken(YcBaseModel):
    iam_token: str
    expires_at: datetime


class RecognizeAnswer(YcBaseModel):
    result: str


class YcStt:
    def __init__(self, oauth_token: str, folder_id: str) -> None:
        self.__session = aiohttp.ClientSession()
        self.__oauth_token = oauth_token
        self.__folder_id = folder_id
        self.__iam_token: Optional[IamToken] = None

    def close(self) -> Awaitable:
        return self.__session.close()

    async def __get_authorization(self) -> str:
        def format_authorization() -> str:
            return f'Bearer {self.__iam_token.iam_token}'
        if self.__iam_token and self.__iam_token.expires_at > datetime.now(timezone.utc):
            return format_authorization()
        body = {'yandexPassportOauthToken': self.__oauth_token}
        async with self.__session.post('https://iam.api.cloud.yandex.net/iam/v1/tokens', json=body) as response:
            response.raise_for_status()
            data = await response.json()
        self.__iam_token = IamToken.parse_obj(data)
        return format_authorization()

    async def recognize(self, data: Union[bytes, io.BytesIO]) -> str:
        headers = {
            hdrs.AUTHORIZATION: await self.__get_authorization(),
            hdrs.CONTENT_TYPE: 'audio/ogg',
        }
        params = {
            'topic': 'general',
            'folderId': self.__folder_id,
            'lang': 'ru-RU',
        }
        async with self.__session.post('https://stt.api.cloud.yandex.net/speech/v1/stt:recognize',
                                       headers=headers, params=params, data=data) as response:
            response.raise_for_status()
            data = await response.json()
        answer = RecognizeAnswer.parse_obj(data)
        return answer.result

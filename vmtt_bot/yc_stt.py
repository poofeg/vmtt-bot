import io
from collections.abc import Iterator
from datetime import datetime, timezone, timedelta
from typing import Optional

from aiohttp import hdrs
from yarl import URL

import aiohttp
import grpc
from pydantic import BaseModel

from vmtt_bot.settings import OAuth
from yandex.cloud.ai.stt.v3 import stt_pb2, stt_service_pb2_grpc

CHUNK_SIZE = 4000
OAUTH_SERVER = URL('https://oauth.yandex.ru')
YC_RESOURCE_MANAGER = URL('https://resource-manager.api.cloud.yandex.net/resource-manager/v1')


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


class ComputeMetadataToken(BaseModel):
    access_token: str
    expires_in: int
    token_type: str


class OAuthTokenSuccessfulResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: Optional[int] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None


class YcStt:
    def __init__(self, folder_id: str = None, oauth_token: str = None, oauth: OAuth = None) -> None:
        self.__session = aiohttp.ClientSession()
        self.__channel = grpc.aio.secure_channel(
            'stt.api.cloud.yandex.net:443', grpc.ssl_channel_credentials()
        )
        self.__oauth_token = oauth_token
        self.__oauth = oauth
        self.__folder_id = folder_id
        self.__iam_token: Optional[IamToken] = None

    async def close(self) -> None:
        await self.__session.close()
        await self.__channel.close()

    def get_authorization_url(self, device_id: str, device_name: str, state: str = '') -> str:
        if not self.__oauth:
            raise Exception('OAuth not configured')
        url = (OAUTH_SERVER / 'authorize').with_query({
            'response_type': 'code',
            'device_id': device_id,
            'device_name': device_name,
            'client_id': self.__oauth.client_id,
            'redirect_uri': self.__oauth.redirect_uri,
            'scope': 'cloud:auth',
            'state': state,
        })
        return str(url)

    async def get_access_token(self, code: str) -> str:
        if not self.__oauth:
            raise Exception('OAuth not configured')
        url = OAUTH_SERVER / 'token'
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': self.__oauth.client_id,
            'client_secret': self.__oauth.client_secret,
        }
        async with self.__session.post(url, data=data) as response:
            if response.status >= 400:
                raise Exception(await response.json())
            response_data = OAuthTokenSuccessfulResponse.parse_obj(await response.json())
        return response_data.access_token

    async def revoke_token(self, access_token: str) -> str:
        if not self.__oauth:
            raise Exception('OAuth not configured')
        url = OAUTH_SERVER / 'revoke_token'
        data = {
            'access_token': access_token,
            'client_id': self.__oauth.client_id,
            'client_secret': self.__oauth.client_secret,
        }
        async with self.__session.post(url, data=data) as response:
            response_data = await response.json()
            if response.status >= 400:
                raise Exception(response_data)
            return response_data

    async def get_folders(self, yc_oauth_token: str) -> dict[str, str]:
        headers = {
            hdrs.AUTHORIZATION: await self.__get_authorization(yc_oauth_token)
        }
        async with self.__session.get(YC_RESOURCE_MANAGER / 'clouds', headers=headers) as response:
            clouds_data = await response.json()
            if response.status >= 400:
                raise Exception(clouds_data)
        result: dict[str, str] = {}
        if 'clouds' not in clouds_data:
            return result
        for cloud in clouds_data['clouds']:
            async with self.__session.get(YC_RESOURCE_MANAGER / 'folders',
                                          params={'cloudId': cloud['id']}, headers=headers) as response:
                folders_data = await response.json()
                if response.status >= 400:
                    raise Exception(clouds_data)
            if 'folders' not in folders_data:
                continue
            for folder in folders_data['folders']:
                result[folder['id']] = f'{cloud["name"]} - {folder["name"]}'
        return result

    async def __get_authorization(self, yc_oauth_token: str = None) -> str:
        def format_authorization() -> str:
            return f'Bearer {self.__iam_token.iam_token}'

        now = datetime.now(timezone.utc)
        if self.__iam_token and self.__iam_token.expires_at > now + timedelta(minutes=1):
            return format_authorization()
        oauth_token = yc_oauth_token or self.__oauth_token
        if oauth_token:
            body = {'yandexPassportOauthToken': oauth_token}
            async with self.__session.post(
                'https://iam.api.cloud.yandex.net/iam/v1/tokens', json=body
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self.__iam_token = IamToken.parse_obj(data)
        else:
            headers = {'Metadata-Flavor': 'Google'}
            async with self.__session.get(
                'http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token', headers=headers
            ) as response:
                response.raise_for_status()
                data = await response.json()
            cmt = ComputeMetadataToken.parse_obj(data)
            self.__iam_token = IamToken(
                iam_token=cmt.access_token,
                expires_at=now + timedelta(seconds=cmt.expires_in),
            )
        return format_authorization()

    async def recognize(self, audio_file: io.BytesIO, audio: bool = False,
                        yc_oauth_token: str = None, yc_folder_id: str = None) -> str:
        def request_iterator() -> Iterator[stt_pb2.StreamingRequest]:
            recognition_model_options = stt_pb2.RecognitionModelOptions(
                audio_format=stt_pb2.AudioFormatOptions(
                    container_audio=stt_pb2.ContainerAudio(
                        container_audio_type=stt_pb2.ContainerAudio.MP3 if audio else stt_pb2.ContainerAudio.OGG_OPUS,
                    ),
                ),
                text_normalization=stt_pb2.TextNormalizationOptions(
                    text_normalization=stt_pb2.TextNormalizationOptions.TEXT_NORMALIZATION_ENABLED,
                    literature_text=True,
                ),
            )
            streaming_options = stt_pb2.StreamingOptions(recognition_model=recognition_model_options)
            yield stt_pb2.StreamingRequest(session_options=streaming_options)

            audio_file.seek(0)
            data = audio_file.read(CHUNK_SIZE)
            while data != b'':
                yield stt_pb2.StreamingRequest(chunk=stt_pb2.AudioChunk(data=data))
                data = audio_file.read(CHUNK_SIZE)

        stub = stt_service_pb2_grpc.RecognizerStub(self.__channel)
        response_iterator = stub.RecognizeStreaming(request_iterator(), metadata=(
            ('authorization', await self.__get_authorization(yc_oauth_token)),
            ('x-folder-id', yc_folder_id or self.__folder_id),
        ))

        parts: list[str] = []
        try:
            async for response in response_iterator:  # type: stt_pb2.StreamingResponse
                if response.HasField('final_refinement'):
                    parts.append(response.final_refinement.normalized_text.alternatives[0].text)
        except grpc.aio.AioRpcError as exc:
            return exc.details()
        return ' '.join(parts)

import io
from collections.abc import Iterator
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiohttp
import grpc
from pydantic import BaseModel

from yandex.cloud.ai.stt.v3 import stt_pb2, stt_service_pb2_grpc

CHUNK_SIZE = 4000


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


class YcStt:
    def __init__(self, folder_id: str, oauth_token: str = None) -> None:
        self.__session = aiohttp.ClientSession()
        self.__channel = grpc.aio.secure_channel(
            'stt.api.cloud.yandex.net:443', grpc.ssl_channel_credentials()
        )
        self.__oauth_token = oauth_token
        self.__folder_id = folder_id
        self.__iam_token: Optional[IamToken] = None

    async def close(self) -> None:
        await self.__session.close()
        await self.__channel.close()

    async def __get_authorization(self) -> str:
        def format_authorization() -> str:
            return f'Bearer {self.__iam_token.iam_token}'

        now = datetime.now(timezone.utc)
        if self.__iam_token and self.__iam_token.expires_at > now + timedelta(minutes=1):
            return format_authorization()
        if self.__oauth_token:
            body = {'yandexPassportOauthToken': self.__oauth_token}
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

    async def recognize(self, audio_file: io.BytesIO, audio: bool = False) -> str:
        def request_iterator() -> Iterator[stt_pb2.StreamingRequest]:
            recognition_model_options = stt_pb2.RecognitionModelOptions(
                audio_format=stt_pb2.AudioFormatOptions(
                    container_audio=stt_pb2.ContainerAudio(
                        container_audio_type=stt_pb2.ContainerAudio.MP3 if audio else stt_pb2.ContainerAudio.OGG_OPUS,
                    ),
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
            ('authorization', await self.__get_authorization()),
            ('x-folder-id', self.__folder_id),
        ))

        parts: list[str] = []
        async for response in response_iterator:  # type: stt_pb2.StreamingResponse
            if response.HasField('final'):
                parts.append(response.final.alternatives[0].text)
        return ' '.join(parts)

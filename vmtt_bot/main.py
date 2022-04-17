import io
import logging
from typing import Optional

from aiogram import Bot, Dispatcher, executor, types

from vmtt_bot.settings import settings
from vmtt_bot.yc_stt import YcStt

logging.basicConfig(level=settings.log_level)

bot = Bot(token=settings.api_token)
dp = Dispatcher(bot)

yc_stt: Optional[YcStt] = None


@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message) -> None:
    await message.answer('Добавь меня в группу или перешли мне сообщение')


async def process_voice_or_audio(message: types.Message, audio: bool = False) -> None:
    if message.chat.id not in settings.chat_id_permitted_list:
        await message.reply(f'Чат с ID {message.chat.id} не в списке разрешенных')
        return
    await message.answer_chat_action('typing')
    file: types.File
    if audio:
        file = await message.audio.get_file()
    else:
        file = await message.voice.get_file()
    voice_data = io.BytesIO()
    await message.bot.download_file(file.file_path, voice_data)
    await message.answer_chat_action('typing')
    text = await yc_stt.recognize(voice_data, audio)
    await message.reply(text)


@dp.message_handler(content_types=types.ContentType.VOICE)
async def process_voice(message: types.Message) -> None:
    await process_voice_or_audio(message, audio=False)


@dp.message_handler(chat_type=types.ChatType.PRIVATE, content_types=types.ContentType.AUDIO)
async def process_audio(message: types.Message) -> None:
    await process_voice_or_audio(message, audio=True)


def run() -> None:
    async def on_startup(dispatcher: Dispatcher) -> None:
        global yc_stt
        yc_stt = YcStt(settings.yc_folder_id, settings.yc_oauth_token)

    async def on_shutdown(dispatcher: Dispatcher) -> None:
        await yc_stt.close()

    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown, skip_updates=True)


if __name__ == '__main__':
    run()

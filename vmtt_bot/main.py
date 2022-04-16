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


@dp.message_handler(content_types=types.ContentType.VOICE)
async def process_voice(message: types.Message) -> None:
    if message.chat.id not in settings.chat_id_permitted_list:
        await message.reply(f'Чат с ID {message.chat.id} не в списке разрешенных')
        return
    voice = message.voice
    if voice.duration > 30:
        await message.reply('Слишком длинное сообщение')
        return
    file: types.File = await voice.get_file()
    voice_data = io.BytesIO()
    await voice.bot.download_file(file.file_path, voice_data)
    text = await yc_stt.recognize(voice_data)
    await message.reply(text)


def run() -> None:
    async def on_startup(dispatcher: Dispatcher) -> None:
        global yc_stt
        yc_stt = YcStt(settings.yc_oauth_token, settings.yc_folder_id)

    async def on_shutdown(dispatcher: Dispatcher) -> None:
        await yc_stt.close()

    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown, skip_updates=True)


if __name__ == '__main__':
    run()

import io
import logging
from typing import Optional

from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.deep_linking import decode_payload

from vmtt_bot.settings import settings
from vmtt_bot.yc_stt import YcStt

logging.basicConfig(level=settings.log_level)

bot = Bot(token=settings.api_token)
storage = RedisStorage2(
    settings.redis.host,
    settings.redis.port,
    db=settings.redis.db
)
dp = Dispatcher(bot, storage=storage)

yc_stt: Optional[YcStt] = None


class AuthStates(StatesGroup):
    welcome = State()
    wait_code = State()
    authorized = State()


async def process_voice_or_audio(message: types.Message, state: FSMContext, audio: bool = False) -> None:
    async with state.proxy() as data:
        yc_oauth_token = data.get('yc_oauth_token')
        yc_folder_id = data.get('yc_folder_id')
    await message.answer_chat_action('typing')
    file: types.File
    if audio:
        file = await message.audio.get_file()
    else:
        file = await message.voice.get_file()
    voice_data = io.BytesIO()
    await message.bot.download_file(file.file_path, voice_data)
    await message.answer_chat_action('typing')
    text = await yc_stt.recognize(voice_data, audio, yc_oauth_token, yc_folder_id)
    await message.reply(text)


@dp.message_handler(state=AuthStates.authorized, content_types=types.ContentType.VOICE)
async def process_voice(message: types.Message, state: FSMContext) -> None:
    await process_voice_or_audio(message, state, audio=False)


@dp.message_handler(state=AuthStates.authorized, chat_type=types.ChatType.PRIVATE,
                    content_types=types.ContentType.AUDIO)
async def process_audio(message: types.Message, state: FSMContext) -> None:
    await process_voice_or_audio(message, state, audio=True)


@dp.message_handler(state=AuthStates.authorized, commands=['logout'])
async def logout(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        yc_oauth_token = data.pop('yc_oauth_token')
    try:
        await yc_stt.revoke_token(yc_oauth_token)
    except Exception:
        logging.exception('Revoke token error')
    await AuthStates.welcome.set()
    await message.answer('Авторизация удалена')


@dp.message_handler(state=AuthStates.authorized, content_types=types.ContentType.ANY)
async def send_welcome(message: types.Message) -> None:
    await message.answer('Добавь меня в группу или перешли мне сообщение.')


def get_folders_markup(folders: dict[str, str], selected_folder_id: str) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(
                f'✅ {folder_name}' if folder_id == selected_folder_id else folder_name,
                callback_data=folder_id
            )
        ] for folder_id, folder_name in folders.items()
    ])


@dp.callback_query_handler(state=AuthStates.authorized)
async def select_catalog(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    selected_folder_id = callback_query.data
    async with state.proxy() as data:
        data['yc_folder_id'] = selected_folder_id
        yc_oauth_token = data['yc_oauth_token']
    await callback_query.answer('Каталог выбран')
    folders = await yc_stt.get_folders(yc_oauth_token)
    await callback_query.message.edit_reply_markup(
        reply_markup=get_folders_markup(folders, selected_folder_id)
    )


@dp.message_handler(state='*', commands=['start'])
@dp.message_handler(state='*', content_types=types.ContentType.ANY, chat_type=types.ChatType.PRIVATE)
async def send_welcome(message: types.Message, state: FSMContext) -> None:
    args = message.get_args()
    if args:
        payload = decode_payload(args)
        token = await yc_stt.get_access_token(payload)
        await AuthStates.authorized.set()
        folders = await yc_stt.get_folders(token)
        selected_folder_id = next(iter(folders))
        async with state.proxy() as data:
            data['yc_oauth_token'] = token
            data['yc_folder_id'] = selected_folder_id
        await message.answer(f'Авторизация успешна. Доступные каталоги (выбранный отмечен галочкой):',
                             reply_markup=get_folders_markup(folders, selected_folder_id))
    elif message.chat.id not in settings.chat_id_permitted_list:
        await AuthStates.wait_code.set()
        url = yc_stt.get_authorization_url(
            device_id=str(message.from_user.id),
            device_name=f'@{message.from_user.username}' if message.from_user.username
                        else message.from_user.first_name,
            state=str(message.chat.id),
        )
        markup = types.InlineKeyboardMarkup(inline_keyboard=[
            [
                types.InlineKeyboardButton('Авторизоваться', url=url)
            ],
        ])
        await message.answer(
            'Для использования бота необходимо авторизоваться в Яндекс.Облаке',
            reply_markup=markup,
        )
        return
    await AuthStates.authorized.set()
    if message.chat.type == types.ChatType.PRIVATE:
        await message.answer('Добавь меня в группу или перешли мне сообщение.')
    else:
        await message.answer('Готов.')


def run() -> None:
    async def on_startup(dispatcher: Dispatcher) -> None:
        global yc_stt
        yc_stt = YcStt(settings.yc_folder_id, settings.yc_oauth_token, settings.oauth)

    async def on_shutdown(dispatcher: Dispatcher) -> None:
        await dispatcher.storage.close()
        await dispatcher.storage.wait_closed()
        await yc_stt.close()

    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown, skip_updates=True)


if __name__ == '__main__':
    run()

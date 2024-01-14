import os
import re
import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

config = load_dotenv('.env')

storage = MemoryStorage()
bot = Bot(token=os.getenv('API_TOKEN'))
dp = Dispatcher(bot, storage=storage)


class PredictBatchSG(StatesGroup):
    file = State()

class RateSG(StatesGroup):
    rate = State()


def cancel():
    return ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton('/cancel'))


@dp.message_handler(commands=['cancel'], state='*')
async def cancel_cmd(message: types.Message, state: FSMContext):
    await message.answer("Отмена", reply_markup=ReplyKeyboardRemove())
    await state.finish()


@dp.message_handler(commands=['start'])
async def process_start_command(message: types.Message, state, raw_state):
    await message.reply("Готов к работе!")


@dp.message_handler(commands=['help'])
async def process_help_command(message: types.Message):
    await message.reply(\
        "Список доступных комманд:\n\n"
        "/predict [lat], [long] - предсказание по координатам\n"
        "/predict_batch - предсказания по нескольким парам координат\n"
        "/history - история запросов\n"
        "/rate - оставить обратную связь\n\n"
        "Пример:\n"
        "/predict 60.56805, 45.04305")


@dp.message_handler(commands=['history'])
async def process_history_command(message: types.Message):
    user_id = int(message.from_id)
    async with aiohttp.ClientSession() as session:
        async with session.get(f'https://atm-project.onrender.com/history/{user_id}') as res:
            history = await res.json()

    if len(history) != 0:
        msg = '\n'.join([f"({pred['lat']}, {pred['long']}): {pred['prediction']}" for pred in history])
        await message.answer(msg)
    else:
        await message.answer('Нет истории')


@dp.message_handler(commands=['rate'])
async def process_rate_command(message: types.Message):
    await message.reply("Оставьте отзыв", reply_markup=cancel())
    await RateSG.rate.set()

    
@dp.message_handler(state=RateSG.rate)
async def process_rate_text(message: types.Message,  state: FSMContext):
    user_id = int(message.from_id)
    text = message.text
    async with aiohttp.ClientSession() as session:
        async with session.post('https://atm-project.onrender.com/feedback',
                                json={'id_user': user_id,
                                      'feedback': text}):
            pass
    
    await message.reply("Спасибо!")
    await state.finish()


@dp.message_handler(commands=['predict'])
async def process_predict_command(message: types.Message):
    user_id = int(message.from_id)

    coordinates = re.split('[^\w.]+', message.text.removeprefix('/predict').strip())

    try:
        lat, long = coordinates
    except ValueError:
        return await message.reply(f"Некорректные данные")

    async with aiohttp.ClientSession() as session:
        async with session.post('https://atm-project.onrender.com/predict',
                                json={'id_user': user_id, 'lat':lat, 'long':long}) as res:
            if res.status == 200:
                prediction = await res.json()
                await message.reply(f"{prediction['prediction']}")
            else:
                await message.reply(f"Некорректные данные")


@dp.message_handler(commands=['predict_batch'])
async def process_predict_batch_command(message: types.Message):
    await PredictBatchSG.file.set()

    await message.answer("Введите координаты (каждая пара координат с новой строки)",
                         reply_markup=cancel())


@dp.message_handler(state=PredictBatchSG.file)
async def process_send_batch(message: types.File, state: FSMContext):
    user_id = int(message.from_id)
    coords = list(map(float, re.split('[^\w.]+', message.text.strip())))
    lats = coords[::2]
    longs = coords[1::2]
    n_rows = len(message.text.split('\n'))
    if len(coords)/2 != n_rows:
        return await message.reply(f"Некорректные данные")


    async with aiohttp.ClientSession() as session:
        async with session.post('https://atm-project.onrender.com/predict_batch',
                                json={'id_user': user_id, 'lat':lats, 'long':longs}) as res:
            if res.status == 200:
                predictions = await res.json()
                msg = '\n'.join([f"({pred['lat']}, {pred['long']}): {pred['prediction']}" for pred in predictions])
                await message.reply(msg)
                await state.finish()
            else:
                await message.reply(f"Некорректные данные")
    
    
if __name__ == '__main__':
    
    executor.start_polling(dp, skip_updates=False)
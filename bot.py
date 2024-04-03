import os
import re
import aiohttp
import asyncio
from dotenv import load_dotenv
from aiogram import F
from aiogram import Bot, Dispatcher
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

config = load_dotenv('.env')

bot = Bot(token=os.getenv('API_TOKEN'))

storage = MemoryStorage()
dp = Dispatcher(storage=storage)

banks = ['ВТБ', 'АЛЬФА-БАНК', 'РОСБАНК', 'РОССЕЛЬХОЗБАНК', 'ГАЗПРОМБАНК', 'АК БАРС', 'УРАЛСИБ БАНК']


class PredictBatchSG(StatesGroup):
    batch = State()


class RateSG(StatesGroup):
    rate = State()


def cancel():
    kb = [
        [
            KeyboardButton(text='Отмена'),
        ],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


@dp.message(F.text, Command('cancel'))
@dp.message(F.text.lower() == "отмена")
async def cmd_cancel(message: Message, state: FSMContext):
    await message.answer("Отмена", reply_markup=ReplyKeyboardRemove())
    await state.clear()


@dp.message(F.text, Command('start'))
async def cmd_start(message: Message):
    await message.reply("Готов к работе!")


@dp.message(F.text, Command('help'))
async def cmd_help(message: Message):
    await message.reply(
        "Список доступных комманд:\n\n"
        "/banks - список доступных банков\n"
        "/predict [lat], [long], [bank] - предсказание по координатам\n"
        "/predict_batch - предсказания по нескольким парам координат\n"
        "/history - история запросов\n"
        "/rate - оставить обратную связь\n\n"
        "Пример:\n"
        "/predict 60.56805, 45.04305, ВТБ")


@dp.message(F.text, Command('banks'))
async def cmd_banks(message: Message):
    await message.reply("Список доступных банков:\n\n"
                        "ВТБ\n"
                        "АЛЬФА-БАНК\n"
                        "РОСБАНК\n"
                        "РОССЕЛЬХОЗБАНК\n"
                        "ГАЗПРОМБАНК\n"
                        "АК БАРС\n"
                        "УРАЛСИБ БАНК\n")


@dp.message(F.text, Command('history'))
async def cmd_history(message: Message):
    user_id = int(message.from_user.id)
    async with aiohttp.ClientSession() as session:
        async with session.get(f'https://atmapi-dahy.onrender.com/history/{user_id}') as res:
            history = await res.json()

    if len(history) != 0:
        msg = '\n'.join([f"({pred['lat']}, {pred['long']}, {pred['atm_group']}): {pred['prediction']}" for pred in history])
        await message.answer(msg)
    else:
        await message.answer('Нет истории')


@dp.message(StateFilter(None), F.text, Command('rate'))
async def cmd_rate(message: Message, state: FSMContext):
    await message.reply("Оставьте отзыв", reply_markup=cancel())
    await state.set_state(RateSG.rate)


@dp.message(F.text, RateSG.rate)
async def rate_text(message: Message,  state: FSMContext):
    user_id = int(message.from_user.id)
    text = message.text
    async with aiohttp.ClientSession() as session:
        async with session.post('https://atmapi-dahy.onrender.com/feedback',
                                json={'id_user': user_id,
                                      'feedback': text}):
            pass

    await message.reply("Спасибо!", reply_markup=ReplyKeyboardRemove())
    await state.clear()


@dp.message(F.text, Command('predict'))
async def cmd_predict(message: Message):
    user_id = int(message.from_user.id)

    try:
        lat, long, atm_group = message.text.removeprefix('/predict').strip().split(', ')
    except ValueError:
        return await message.reply("Некорректные данные")
    
    if not atm_group in banks:
        return await message.reply("Некорректные данные")

    async with aiohttp.ClientSession() as session:
        async with session.post('https://atmapi-dahy.onrender.com/predict',
                                json={'id_user': user_id, 'lat': lat, 'long': long, 'atm_group': atm_group}) as res:
            if res.status == 200:
                prediction = await res.json()
                await message.reply(f"{prediction['prediction']}")
            else:
                await message.reply("Некорректные данные")


@dp.message(F.text, Command('predict_batch'))
async def cmd_predict_batch(message: Message, state: FSMContext):
    await state.set_state(PredictBatchSG.batch)

    await message.answer("Введите координаты и наименование банка (информация о каждом банкомате с новой строки)",
                         reply_markup=cancel())


@dp.message(F.text, PredictBatchSG.batch)
async def send_batch(message: Message, state: FSMContext):
    user_id = int(message.from_user.id)
    try:
        rows = message.text.strip().split('\n')
        data = [list(map(float, row.split(', ')[:2])) + [row.split(', ')[2]]  for row in rows]
    except (ValueError, IndexError):
        return await message.reply("Некорректные данные")
    lats = [row[0] for row in data]
    longs = [row[1] for row in data]
    atm_groups = [row[2] for row in data]

    for atm_group in atm_groups:
        if not atm_group.upper() in banks:
            return await message.reply("Некорректные данные")

    async with aiohttp.ClientSession() as session:
        async with session.post('https://atmapi-dahy.onrender.com/predict_batch',
                                json={'id_user': user_id, 'lat': lats, 'long': longs, 'atm_group': atm_groups}) as res:
            if res.status == 200:
                predictions = await res.json()
                msg = '\n'.join([f"({pred['lat']}, {pred['long']}, {pred['atm_group']}): {pred['prediction']}" for pred in predictions])
                await message.reply(msg, reply_markup=ReplyKeyboardRemove())
                await state.clear()
            else:
                await message.reply("Некорректные данные")


async def main():
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())

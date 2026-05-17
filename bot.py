import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# ===== Basic setup =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_CHAT_ID = 6413238670 

# Render предоставляет URL вашего сервиса
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://client-survey-bot.onrender.com")
WEBHOOK_PATH = "/webhook"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ===== Text placeholders =====
QUESTION_1 = "Здравствуйте, я бот от frankaiaz02. Чем могу вам помочь?"
QUESTION_2 = "Для чего вам нужен бот"
QUESTION_3 = "Сколько планируете заплатить за бота"
QUESTION_4 = "Нужна ли вам помощь с установкой бота на сервер?"
QUESTION_5 = "Напишите свой номер телефона для дальнейшей связи"
FINAL_RESPONSE = "Спасибо за ваш ответ! Мы свяжемся с вами в ближайшее время."


# ===== FSM states =====
class SurveyStates(StatesGroup):
    Q1 = State()
    Q2 = State()
    Q3 = State()
    Q4 = State()
    Q5 = State()


# ===== Keyboards =====
def q1_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Телеграм бот", callback_data="q2_optA"),
                InlineKeyboardButton(text="WhatsApp бот", callback_data="q2_optB"),
                InlineKeyboardButton(text="Другое", callback_data="skip_to_q5"),
            ]
        ]
    )


def q3_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="0-5000", callback_data="to_q4_one"),
                InlineKeyboardButton(text="5000-10000", callback_data="to_q4_two"),
                InlineKeyboardButton(text="10000-35000", callback_data="to_q4_three"),
            ]
        ]
    )


def q4_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Нет, помощь не нужна", callback_data="to_q5_a"),
                InlineKeyboardButton(text="Да, помощь нужна", callback_data="to_q5_b"),
                InlineKeyboardButton(text="Наш сервер(разработка)", callback_data="disabled"),
            ]
        ]
    )


# ===== Start survey =====
@dp.message(CommandStart())
async def start_survey(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(SurveyStates.Q1)
    await message.answer(QUESTION_1, reply_markup=q1_keyboard())


# ===== Q1 (callback only): route to Q2 or skip to Q5 =====
@dp.callback_query(SurveyStates.Q1, F.data.in_(["q2_optA", "q2_optB", "skip_to_q5"]))
async def handle_q1_buttons(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(answer_1=callback.data)

    if callback.data == "skip_to_q5":
        await state.update_data(
            answer_2="SKIPPED",
            answer_3="SKIPPED",
            answer_4="SKIPPED",
        )
        await state.set_state(SurveyStates.Q5)
        await callback.message.answer(QUESTION_5)
        return

    await state.set_state(SurveyStates.Q2)
    await callback.message.answer(QUESTION_2)


# ===== Q2 (open text): auto to Q3 =====
@dp.message(SurveyStates.Q2, F.text)
async def handle_question_2(message: Message, state: FSMContext):
    await state.update_data(answer_2=message.text)
    await state.set_state(SurveyStates.Q3)
    await message.answer(QUESTION_3, reply_markup=q3_keyboard())


# ===== Q3 (callback only): all options go to Q4 =====
@dp.callback_query(SurveyStates.Q3, F.data.in_(["to_q4_one", "to_q4_two", "to_q4_three"]))
async def handle_q3_buttons(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(answer_3=callback.data)
    await state.set_state(SurveyStates.Q4)
    await callback.message.answer(QUESTION_4, reply_markup=q4_keyboard())


# ===== Q4 (callback only): 2 active + 1 disabled/no-op =====
@dp.callback_query(SurveyStates.Q4, F.data.in_(["to_q5_a", "to_q5_b"]))
async def handle_q4_active_buttons(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(answer_4=callback.data)
    await state.set_state(SurveyStates.Q5)
    await callback.message.answer(QUESTION_5)


@dp.callback_query(SurveyStates.Q4, F.data == "disabled")
async def handle_q4_disabled_button(callback: CallbackQuery):
    await callback.answer("This option is disabled.", show_alert=False)


# ===== Q5 (open text): finalize survey =====
@dp.message(SurveyStates.Q5, F.text)
async def handle_question_5(message: Message, state: FSMContext):
    await state.update_data(answer_5=message.text)

    # Get all answers from FSM storage
    survey_answers = await state.get_data()
    # Example structure:
    # {
    #   "answer_1": "...",
    #   "answer_2": "...",
    #   "answer_3": "...",
    #   "answer_4": "...",
    #   "answer_5": "..."
    # }

    # Forward collected answers to bot owner
    owner_report = (
        "New survey response:\n"
        f"User ID: {message.from_user.id}\n"
        f"Username: @{message.from_user.username}\n"
        f"Q1: {survey_answers.get('answer_1')}\n"
        f"Q2: {survey_answers.get('answer_2')}\n"
        f"Q3: {survey_answers.get('answer_3')}\n"
        f"Q4: {survey_answers.get('answer_4')}\n"
        f"Q5: {survey_answers.get('answer_5')}"
    )
    await bot.send_message(chat_id=OWNER_CHAT_ID, text=owner_report)

    await state.clear()
    await message.answer(FINAL_RESPONSE)

    # Optional: print answers in console
    logger.info(f"Survey answers: {survey_answers}")


# ===== Webhook and Health Check (для Render) =====
async def on_startup(bot: Bot):
    webhook_url = f"{RENDER_URL}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url)
    logger.info(f"Вебхук установлен на {webhook_url}")

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    logger.info("Вебхук удален")

# Health check для Render
async def health(request):
    return web.Response(text="OK")


# ===== Run bot =====
async def main():
    # Настройка вебхуков
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Создаем aiohttp приложение
    app = web.Application()
    app.router.add_get("/", health)
    
    # Настройка вебхук обработчика
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    # Запускаем веб-сервер
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
    await site.start()
    
    logger.info("Бот запущен и слушает вебхуки...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())

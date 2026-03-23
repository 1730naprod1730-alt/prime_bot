import asyncio
import random
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, ChatMemberUpdated,
    InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
)
from aiogram.filters import ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "8788528245:AAFRuivbg0QI2l9JYmYSmxBBfkqPoBQxucU"
TIMEOUT_SECONDS = 120  # 2 минуты на прохождение проверки

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.update.outer_middleware()
async def log_middleware(handler, event, data):
    logging.info(f"INCOMING UPDATE: {event}")
    return await handler(event, data)

# Хранилище: user_id -> {"answer": int, "message_id": int, "chat_id": int, "task": asyncio.Task}
pending: dict = {}


def generate_question():
    a = random.randint(1, 10)
    b = random.randint(1, 10)
    correct = a + b
    wrong = random.sample([x for x in range(1, 21) if x != correct], 3)
    options = wrong + [correct]
    random.shuffle(options)
    return f"{a} + {b} = ?", options, correct


def build_keyboard(user_id: int, options: list) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=str(opt), callback_data=f"verify:{user_id}:{opt}")
        for opt in options
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


async def kick_on_timeout(chat_id: int, user_id: int):
    await asyncio.sleep(TIMEOUT_SECONDS)
    if user_id in pending:
        data = pending.pop(user_id)
        try:
            await bot.ban_chat_member(chat_id, user_id)
            await bot.unban_chat_member(chat_id, user_id)
            await bot.delete_message(chat_id, data["message_id"])
            await bot.send_message(chat_id, "⏰ Пользователь не прошёл проверку и был удалён.")
        except Exception as e:
            logging.warning(f"Ошибка при кике {user_id}: {e}")


@dp.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_user_join(event: ChatMemberUpdated):
    user = event.new_chat_member.user
    chat_id = event.chat.id

    if user.is_bot:
        return

    # Ограничиваем — не может писать
    try:
        await bot.restrict_chat_member(
            chat_id, user.id,
            permissions=ChatPermissions(can_send_messages=False)
        )
    except Exception as e:
        logging.warning(f"Не удалось ограничить {user.id}: {e}")

    question, options, correct = generate_question()

    msg = await bot.send_message(
        chat_id,
        f"👋 Привет, {user.first_name}!\n\n"
        f"Для входа в группу реши пример:\n\n"
        f"<b>{question}</b>\n\n"
        f"У тебя есть {TIMEOUT_SECONDS // 60} минуты.",
        parse_mode="HTML",
        reply_markup=build_keyboard(user.id, options)
    )

    task = asyncio.create_task(kick_on_timeout(chat_id, user.id))

    pending[user.id] = {
        "answer": correct,
        "message_id": msg.message_id,
        "chat_id": chat_id,
        "task": task
    }


@dp.callback_query(F.data.startswith("verify:"))
async def on_verify(callback: CallbackQuery):
    parts = callback.data.split(":")
    user_id = int(parts[1])
    chosen = int(parts[2])

    if callback.from_user.id != user_id:
        await callback.answer("Это не твоя проверка!", show_alert=True)
        return

    if user_id not in pending:
        await callback.answer("Проверка уже завершена.", show_alert=True)
        return

    data = pending.pop(user_id)
    data["task"].cancel()
    chat_id = data["chat_id"]

    if chosen == data["answer"]:
        await bot.restrict_chat_member(
            chat_id, user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        await callback.message.edit_text(
            f"✅ {callback.from_user.first_name} прошёл проверку и теперь может писать!"
        )
        await asyncio.sleep(60)
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        try:
            await bot.ban_chat_member(chat_id, user_id)
            await bot.unban_chat_member(chat_id, user_id)
            await callback.message.edit_text(
                f"❌ {callback.from_user.first_name} не прошёл проверку и был удалён."
            )
        except Exception as e:
            logging.warning(f"Ошибка при кике {user_id}: {e}")

    await callback.answer()





async def main():
    await dp.start_polling(bot, allowed_updates=["chat_member", "callback_query", "message"])


if __name__ == "__main__":
    asyncio.run(main())

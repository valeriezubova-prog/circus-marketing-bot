"""
Entry point for the Circus and Marketing bot.

This module sets up an aiogram Dispatcher, registers handlers for
commands, callback queries and text searches, and runs the bot.

It uses long polling via `start_polling`, which is suitable for
deployment on Render.com or running locally.
"""

import asyncio
import os
import re
from typing import List

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

from . import content
from .storage import PhotoStore

# Load environment variables from .env if present
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USERNAMES = {u.strip().lower() for u in os.getenv("ADMIN_USERNAMES", "").split(",") if u.strip()}
STORAGE_PATH = os.getenv("STORAGE_PATH", "./data/bot.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# aiogram >= 3.7: parse_mode задаём через DefaultBotProperties
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher()
store = PhotoStore(STORAGE_PATH)


def main_menu_kb() -> InlineKeyboardMarkup:
    """Construct the inline keyboard for the main menu."""
    kb = InlineKeyboardBuilder()
    kb.button(text="👥 Люди", callback_data="menu:people")
    kb.button(text="📚 Материалы", callback_data="menu:materials")
    kb.button(text="📝 Как ставить задачи", callback_data="menu:tasking")
    kb.button(text="❓ FAQ", callback_data="menu:faq")
    kb.button(text="🔍 Поиск", callback_data="menu:search")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def people_list_kb() -> InlineKeyboardMarkup:
    """Keyboard listing all people in the department."""
    kb = InlineKeyboardBuilder()
    for slug, name, *_ in content.PEOPLE:
        kb.button(text=name, callback_data=f"person:{slug}")
    kb.button(text="⬅️ В меню", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


def person_card_caption(name: str, title: str, desc: str, team: str, leader: str, tg_user: str) -> str:
    """Build the Markdown caption for a person's card."""
    # Escape underscores to avoid Markdown formatting issues
    def esc(s: str) -> str:
        return s.replace("_", "\\_")

    cap = f"*{esc(name)}*\n_{esc(title)}_\n\n{desc}\n\n*Команда:* {esc(team)}\n*Руководитель:* {esc(leader)}"
    cap += f"\n\n[Написать в Telegram](https://t.me/{tg_user})"
    return cap


def faq_text() -> str:
    """Format FAQ entries as a Markdown list."""
    lines = ["*FAQ*"]
    for q, label, url in content.FAQ:
        lines.append(f"• *{q}*\n  👉 [{label}]({url})")
    return "\n\n".join(lines)


def materials_text() -> str:
    """Format materials list as Markdown."""
    lines = ["> всё, что чаще всего ищут (и спрашивают у нас в панике 🔥):"]
    for label, url in content.MATERIALS:
        lines.append(f"• [{label}]({url})")
    return "\n".join(lines)


def tasking_text() -> str:
    """Return the tasking instructions."""
    return content.TASKING_TEXT


def search_people(query: str) -> List[str]:
    """Return slugs of people matching the search query."""
    q = query.lower()
    hits = []
    for slug, name, title, desc, team, leader, tg in content.PEOPLE:
        hay = " ".join([name, title, desc, team, leader, tg]).lower()
        if q in hay:
            hits.append(slug)
    return hits[:20]


def is_admin(msg: Message) -> bool:
    """Check if the message author is an admin by username."""
    if not msg.from_user or not msg.from_user.username:
        return False
    return msg.from_user.username.lower() in ADMIN_USERNAMES


# Handlers

@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Send the start menu."""
    await message.answer(f"*{content.BOT_NAME}*\n\n{content.START_TEXT}", reply_markup=main_menu_kb())


@dp.callback_query(F.data == "menu:home")
async def cb_home(callback: CallbackQuery) -> None:
    """Return to the main menu."""
    await callback.message.edit_text(
        f"*{content.BOT_NAME}*\n\n{content.START_TEXT}", reply_markup=main_menu_kb()
    )


@dp.callback_query(F.data == "menu:people")
async def cb_people(callback: CallbackQuery) -> None:
    """List people."""
    await callback.message.edit_text("выбирай персонажа:", reply_markup=people_list_kb())


@dp.callback_query(F.data == "menu:materials")
async def cb_materials(callback: CallbackQuery) -> None:
    """Show materials list."""
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ В меню", callback_data="menu:home")
    await callback.message.edit_text(
        materials_text(), reply_markup=kb.as_markup()
    )


@dp.callback_query(F.data == "menu:tasking")
async def cb_tasking(callback: CallbackQuery) -> None:
    """Show tasking instructions."""
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ В меню", callback_data="menu:home")
    await callback.message.edit_text(tasking_text(), reply_markup=kb.as_markup())


@dp.callback_query(F.data == "menu:faq")
async def cb_faq(callback: CallbackQuery) -> None:
    """Show FAQ."""
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ В меню", callback_data="menu:home")
    await callback.message.edit_text(faq_text(), reply_markup=kb.as_markup())


@dp.callback_query(F.data == "menu:search")
async def cb_search(callback: CallbackQuery) -> None:
    """Explain how to use search."""
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ В меню", callback_data="menu:home")
    await callback.message.edit_text(
        "напиши мне имя, роль или ключевое слово — я найду человека. Введи: `поиск <запрос>`",
        reply_markup=kb.as_markup(),
    )


@dp.message(F.text.regexp(r"^\s*поиск\s+(.+)$"))
async def text_search(message: Message) -> None:
    """Handle text search queries."""
    query = re.findall(r"^\s*поиск\s+(.+)$", message.text, flags=re.I)[0]
    slugs = search_people(query)
    if not slugs:
        await message.answer(
            "ничего не нашла. попробуй по имени или по роли (например: «бренд», «трейд», «исследование»)."
        )
        return
    kb = InlineKeyboardBuilder()
    for slug in slugs:
        name = next(p[1] for p in content.PEOPLE if p[0] == slug)
        kb.button(text=name, callback_data=f"person:{slug}")
    kb.button(text="⬅️ В меню", callback_data="menu:home")
    kb.adjust(1)
    await message.answer("нашла вот что:", reply_markup=kb.as_markup())


@dp.callback_query(F.data.startswith("person:"))
async def cb_person(callback: CallbackQuery) -> None:
    """Show a person's card."""
    slug = callback.data.split(":", 1)[1]
    person = next((p for p in content.PEOPLE if p[0] == slug), None)
    if not person:
        await callback.answer("карточка не найдена", show_alert=True)
        return

    _, name, title, desc, team, leader, tg_user = person
    caption = person_card_caption(name, title, desc, team, leader, tg_user)
    file_id = await store.get_file_id(slug)

    # Навигация
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Люди", callback_data="menu:people")
    kb.button(text="🏠 В меню", callback_data="menu:home")
    kb.adjust(2)

    if file_id:
        # Если есть сохранённый file_id — пробуем редактировать/прислать фото
        try:
            if callback.message.photo:
                # Редактируем существующее медиа
                await callback.message.edit_media(
                    InputMediaPhoto(media=file_id, caption=caption),
                    reply_markup=kb.as_markup(),
                )
            else:
                # В сообщении нет фото — присылаем новое
                await bot.send_photo(
                    chat_id=callback.message.chat.id,
                    photo=file_id,
                    caption=caption,
                    reply_markup=kb.as_markup(),
                )
        except Exception:
            # Резерв: просто текст
            await callback.message.edit_text(caption, reply_markup=kb.as_markup())
    else:
        # Нет кэша — только текст
        await callback.message.edit_text(caption, reply_markup=kb.as_markup())


# Admin handlers: uploading photos

@dp.message(F.photo & F.caption.regexp(r"^/photo\s+([a-z0-9\-]+)$"))
async def admin_photo_caption(message: Message) -> None:
    """Handle admin uploading a photo with a caption '/photo <slug>'."""
    if not is_admin(message):
        await message.reply("нужны права админа.")
        return
    slug = re.findall(r"^/photo\s+([a-z0-9\-]+)$", message.caption.strip())[0]
    file_id = message.photo[-1].file_id
    await store.set_file_id(slug, file_id)
    await message.reply(f"🔐 фото сохранено для `{slug}`")


@dp.message(Command("photo"))
async def admin_photo_help(message: Message) -> None:
    """Explain how to upload a photo for admins."""
    if not is_admin(message):
        await message.reply("нужны права админа.")
        return
    await message.reply(
        "пришли фото с подписью `/photo <slug>`\nнапример: `/photo polina-tikhonenko`"
    )


async def main() -> None:
    """Initialise storage and start polling."""
    await store.init()
    # Use uvloop if available on non-Windows platforms
    try:
        import uvloop  # type: ignore
        uvloop.install()
    except Exception:
        pass

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())

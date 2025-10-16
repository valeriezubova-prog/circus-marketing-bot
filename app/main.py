"""
Entry point for the Circus and Marketing bot.

Sets up aiogram Dispatcher, registers handlers and runs long polling.
Suitable for Render.com or local runs.
"""

import asyncio
import os
import re
from typing import List, Tuple

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

# ---- Setup & config ---------------------------------------------------------

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USERNAMES = {
    u.strip().lower() for u in os.getenv("ADMIN_USERNAMES", "").split(",") if u.strip()
}
STORAGE_PATH = os.getenv("STORAGE_PATH", "/data/bot.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# aiogram 3.7+: parse_mode задаётся через default=DefaultBotProperties(...)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()
store = PhotoStore(STORAGE_PATH)

# Hotfix 1: если вдруг в контенте остались тильды зачёркивания из MarkdownV2 — уберём
CLEAN_START_TEXT = (content.START_TEXT or "").replace("~~", "")

# Hotfix 2: гарантированно правим username у Полины (если в контенте он иной)
_fixed_people = []
for item in content.PEOPLE:
    if len(item) != 7:
        _fixed_people.append(item)
        continue
    slug, name, title, desc, team, leader, tg = item
    if slug == "polina-tikhonenko":
        tg = "polina_tikhonenko"  # ← нужный логин с подчёркиванием
    _fixed_people.append((slug, name, title, desc, team, leader, tg))
content.PEOPLE = _fixed_people  # type: ignore


# ---- Keyboards --------------------------------------------------------------

def main_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👥 Люди", callback_data="menu:people")
    kb.button(text="📚 Материалы", callback_data="menu:materials")
    kb.button(text="📝 Как ставить задачи", callback_data="menu:tasking")
    kb.button(text="❓ FAQ", callback_data="menu:faq")
    kb.button(text="🔍 Поиск", callback_data="menu:search")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def people_list_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for slug, name, *_ in content.PEOPLE:
        kb.button(text=name, callback_data=f"person:{slug}")
    kb.button(text="⬅️ В меню", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


# ---- Rendering helpers ------------------------------------------------------

def person_card_caption(
    name: str, title: str, desc: str, team: str, leader: str, tg_user: str
) -> str:
    """Markdown caption for a person's card (экраним подчёркивания)."""
    def esc(s: str) -> str:
        return s.replace("_", "\\_")

    cap = (
        f"*{esc(name)}*\n_{esc(title)}_\n\n"
        f"{desc}\n\n"
        f"*Команда:* {esc(team)}\n"
        f"*Руководитель:* {esc(leader)}"
    )
    cap += f"\n\n[Написать в Telegram](https://t.me/{tg_user})"
    return cap


def faq_text() -> str:
    lines = ["*FAQ*"]
    for q, label, url in content.FAQ:
        lines.append(f"• *{q}*\n  👉 [{label}]({url})")
    return "\n\n".join(lines)


def materials_text() -> str:
    lines = ["> всё, что чаще всего ищут (и спрашивают у нас в панике 🔥):"]
    for label, url in content.MATERIALS:
        lines.append(f"• [{label}]({url})")
    return "\n".join(lines)


def tasking_text() -> str:
    return content.TASKING_TEXT


# ---- Search helpers ---------------------------------------------------------

def search_people(query: str) -> List[str]:
    """Return slugs of people matching the search query."""
    q = query.lower()
    hits: List[str] = []
    for slug, name, title, desc, team, leader, tg in content.PEOPLE:
        hay = " ".join([name, title, desc, team, leader, tg]).lower()
        if q in hay:
            hits.append(slug)
    return hits[:20]


def search_materials(query: str) -> List[Tuple[str, str]]:
    """Return (label, url) where query occurs in label."""
    q = query.lower()
    hits: List[Tuple[str, str]] = []
    for label, url in content.MATERIALS:
        if q in label.lower():
            hits.append((label, url))
    return hits[:20]


def is_admin(msg: Message) -> bool:
    if not msg.from_user or not msg.from_user.username:
        return False
    return msg.from_user.username.lower() in ADMIN_USERNAMES


# ---- Handlers ---------------------------------------------------------------

@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        f"*{content.BOT_NAME}*\n\n{CLEAN_START_TEXT}",
        reply_markup=main_menu_kb(),
    )


@dp.callback_query(F.data == "menu:home")
async def cb_home(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        f"*{content.BOT_NAME}*\n\n{CLEAN_START_TEXT}",
        reply_markup=main_menu_kb(),
    )


@dp.callback_query(F.data == "menu:people")
async def cb_people(callback: CallbackQuery) -> None:
    await callback.message.edit_text("выбирай персонажа:", reply_markup=people_list_kb())


@dp.callback_query(F.data == "menu:materials")
async def cb_materials(callback: CallbackQuery) -> None:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ В меню", callback_data="menu:home")
    await callback.message.edit_text(materials_text(), reply_markup=kb.as_markup())


@dp.callback_query(F.data == "menu:tasking")
async def cb_tasking(callback: CallbackQuery) -> None:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ В меню", callback_data="menu:home")
    await callback.message.edit_text(tasking_text(), reply_markup=kb.as_markup())


@dp.callback_query(F.data == "menu:faq")
async def cb_faq(callback: CallbackQuery) -> None:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ В меню", callback_data="menu:home")
    await callback.message.edit_text(faq_text(), reply_markup=kb.as_markup())


@dp.callback_query(F.data == "menu:search")
async def cb_search(callback: CallbackQuery) -> None:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ В меню", callback_data="menu:home")
    await callback.message.edit_text(
        "напиши мне имя, роль или ключевое слово — я найду человека или материал. "
        "Можно так: `поиск <запрос>` или просто пришли слово.",
        reply_markup=kb.as_markup(),
    )


# Старый «командный» поиск: "поиск что-то"
@dp.message(F.text.regexp(r"^\s*поиск\s+(.+)$"))
async def text_search(message: Message) -> None:
    query = re.findall(r"^\s*поиск\s+(.+)$", message.text, flags=re.I)[0]
    await run_combined_search(message, query)


# Новый «умный» свободный поиск по любому тексту
@dp.message(F.text)
async def smart_text_lookup(message: Message) -> None:
    q = (message.text or "").strip()
    if not q or q.startswith("/"):
        return
    # Простые синонимы
    synonyms = {
        "ббук": "брендбук",
        "гайдбук": "брендбук",
        "гайд": "гайд",
        "шрифты": "шрифт",
        "цвета": "цвет",
    }
    for k, v in synonyms.items():
        if k in q.lower():
            q = v
            break
    await run_combined_search(message, q)


async def run_combined_search(message: Message, query: str) -> None:
    """Сначала ищем материалы, затем людей; если пусто — подсказка."""
    # 1) Материалы
    mats = search_materials(query)
    if mats:
        lines = ["*нашла материалы:*"]
        for label, url in mats:
            lines.append(f"• [{label}]({url})")
        await message.answer("\n".join(lines))
        return

    # 2) Люди
    slugs = search_people(query)
    if slugs:
        kb = InlineKeyboardBuilder()
        for slug in slugs:
            name = next(p[1] for p in content.PEOPLE if p[0] == slug)
            kb.button(text=name, callback_data=f"person:{slug}")
        kb.button(text="⬅️ В меню", callback_data="menu:home")
        kb.adjust(1)
        await message.answer("нашла людей:", reply_markup=kb.as_markup())
        return

    # 3) Подсказка
    await message.answer(
        "ничего не нашла. попробуй по ключевому слову (например: «гайд», «брендбук», «шрифты») "
        "или нажми «🔍 Поиск» и введи `поиск <слово>`."
    )


@dp.callback_query(F.data.startswith("person:"))
async def cb_person(callback: CallbackQuery) -> None:
    slug = callback.data.split(":", 1)[1]
    person = next((p for p in content.PEOPLE if p[0] == slug), None)
    if not person:
        await callback.answer("карточка не найдена", show_alert=True)
        return
    _, name, title, desc, team, leader, tg_user = person
    caption = person_card_caption(name, title, desc, team, leader, tg_user)

    file_id = await store.get_file_id(slug)

    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Люди", callback_data="menu:people")
    kb.button(text="🏠 В меню", callback_data="menu:home")
    kb.adjust(2)

    if file_id:
        try:
            if callback.message.photo:
                await callback.message.edit_media(
                    InputMediaPhoto(media=file_id, caption=caption, parse_mode=ParseMode.MARKDOWN),
                    reply_markup=kb.as_markup(),
                )
            else:
                await bot.send_photo(
                    chat_id=callback.message.chat.id,
                    photo=file_id,
                    caption=caption,
                    reply_markup=kb.as_markup(),
                    parse_mode=ParseMode.MARKDOWN,
                )
        except Exception:
            await callback.message.edit_text(caption, reply_markup=kb.as_markup())
    else:
        await callback.message.edit_text(caption, reply_markup=kb.as_markup())


# ---- Admin: upload photos ---------------------------------------------------

@dp.message(F.photo & F.caption.regexp(r"^/photo\s+([a-z0-9\-]+)$"))
async def admin_photo_caption(message: Message) -> None:
    if not is_admin(message):
        await message.reply("нужны права админа.")
        return
    slug = re.findall(r"^/photo\s+([a-z0-9\-]+)$", message.caption.strip())[0]
    file_id = message.photo[-1].file_id
    await store.set_file_id(slug, file_id)
    await message.reply(f"🔐 фото сохранено для `{slug}`")


@dp.message(Command("photo"))
async def admin_photo_help(message: Message) -> None:
    if not is_admin(message):
        await message.reply("нужны права админа.")
        return
    await message.reply("пришли фото с подписью `/photo <slug>`\nнапример: `/photo polina-tikhonenko`")


# ---- Entry point ------------------------------------------------------------

async def main() -> None:
    await store.init()
    try:
        import uvloop  # type: ignore
        uvloop.install()
    except Exception:
        pass
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())

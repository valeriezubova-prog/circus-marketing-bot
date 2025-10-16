"""
Entry point для бота «Цирк и маркетинг».

HTML-разметка вместо Markdown — так корректнее работают подчёркивания
в ссылках и не «слетают» звёздочки/курсив.
"""

import asyncio
import html
import os
import re
from typing import List

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
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

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USERNAMES = {
    u.strip().lower() for u in os.getenv("ADMIN_USERNAMES", "").split(",") if u.strip()
}
STORAGE_PATH = os.getenv("STORAGE_PATH", "/data/bot.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# ВАЖНО: используем HTML как parse_mode по умолчанию
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
store = PhotoStore(STORAGE_PATH)


# ---------- UI helpers ----------

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


def person_card_caption(
    name: str, title: str, desc: str, team: str, leader: str, tg_user: str
) -> str:
    """
    HTML-подписка к карточке сотрудника.
    Все пользовательские строки экранируем для безопасности.
    """
    esc = html.escape
    parts = [
        f"<b>{esc(name)}</b>",
        f"<i>{esc(title)}</i>",
        "",
        esc(desc),
        "",
        f"<b>Команда:</b> {esc(team)}",
        f"<b>Руководитель:</b> {esc(leader)}",
        "",
        f'<a href="https://t.me/{tg_user}">Написать в Telegram</a>',
    ]
    return "\n".join(parts)


def faq_text() -> str:
    rows = ["<b>FAQ</b>"]
    for q, label, url in content.FAQ:
        rows.append(f"• <b>{html.escape(q)}</b>\n  👉 <a href=\"{url}\">{html.escape(label)}</a>")
    return "\n\n".join(rows)


def materials_text() -> str:
    rows = ["> всё, что чаще всего ищут (и спрашивают у нас в панике 🔥):"]
    for label, url in content.MATERIALS:
        rows.append(f"• <a href=\"{url}\">{html.escape(label)}</a>")
    return "\n".join(rows)


def tasking_text() -> str:
    return html.escape(content.TASKING_TEXT)


def search_people(query: str) -> List[str]:
    q = query.lower()
    hits: List[str] = []
    for slug, name, title, desc, team, leader, tg in content.PEOPLE:
        hay = " ".join([name, title, desc, team, leader, tg]).lower()
        if q in hay:
            hits.append(slug)
    return hits[:20]


def is_admin(msg: Message) -> bool:
    if not msg.from_user or not msg.from_user.username:
        return False
    return msg.from_user.username.lower() in ADMIN_USERNAMES


# ---------- Handlers ----------

@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        f"<b>{html.escape(content.BOT_NAME)}</b>\n\n{html.escape(content.START_TEXT)}",
        reply_markup=main_menu_kb(),
    )


@dp.callback_query(F.data == "menu:home")
async def cb_home(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        f"<b>{html.escape(content.BOT_NAME)}</b>\n\n{html.escape(content.START_TEXT)}",
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
        "напиши мне имя, роль или ключевое слово — я найду человека. "
        "Формат: <code>поиск &lt;запрос&gt;</code>",
        reply_markup=kb.as_markup(),
    )


@dp.message(F.text.regexp(r"^\s*поиск\s+(.+)$"))
async def text_search(message: Message) -> None:
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


# Свободный текст — быстрые ответы на популярные слова
@dp.message(F.text.func(lambda t: isinstance(t, str)))
async def quick_replies(message: Message) -> None:
    t = message.text.lower()

    def matches(route: str) -> bool:
        return any(key in t for key in content.KEYWORD_ROUTES.get(route, set()))

    if matches("materials"):
        await message.answer(materials_text())
        return
    if matches("tasking"):
        await message.answer(tasking_text())
        return
    if matches("faq"):
        await message.answer(faq_text())
        return
    # если ничего не подошло — не перехватываем другие обработчики
    # но чтобы пользователь получил фидбек:
    if re.fullmatch(r"\s*[а-яa-z0-9 _\-]{1,32}\s*", t, flags=re.I):
        await message.answer(
            "я не уверена, что поняла. Можешь написать «поиск Иван», "
            "или попробовать слова: «гайд», «брендбук», «Ева», «FAQ»."
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

    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Люди", callback_data="menu:people")
    kb.button(text="🏠 В меню", callback_data="menu:home")
    kb.adjust(2)

    file_id = await store.get_file_id(slug)
    if file_id:
        try:
            if callback.message.photo:
                await callback.message.edit_media(
                    InputMediaPhoto(media=file_id, caption=caption, parse_mode=ParseMode.HTML),
                    reply_markup=kb.as_markup(),
                )
            else:
                await bot.send_photo(
                    chat_id=callback.message.chat.id,
                    photo=file_id,
                    caption=caption,
                    reply_markup=kb.as_markup(),
                    parse_mode=ParseMode.HTML,
                )
        except Exception:
            await callback.message.edit_text(caption, reply_markup=kb.as_markup())
    else:
        await callback.message.edit_text(caption, reply_markup=kb.as_markup())


# ---------- Admin: загрузка фото ----------

@dp.message(F.photo & F.caption.regexp(r"^/photo\s+([a-z0-9\-]+)$"))
async def admin_photo_caption(message: Message) -> None:
    if not is_admin(message):
        await message.reply("нужны права админа.")
        return
    slug = re.findall(r"^/photo\s+([a-z0-9\-]+)$", message.caption.strip())[0]
    file_id = message.photo[-1].file_id
    await store.set_file_id(slug, file_id)
    await message.reply(f"🔐 фото сохранено для <code>{html.escape(slug)}</code>")


@dp.message(Command("photo"))
async def admin_photo_help(message: Message) -> None:
    if not is_admin(message):
        await message.reply("нужны права админа.")
        return
    await message.reply(
        "пришли фото с подписью <code>/photo &lt;slug&gt;</code>\n"
        "например: <code>/photo polina-tikhonenko</code>"
    )


# ---------- Run ----------

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

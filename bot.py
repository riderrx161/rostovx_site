"""
KITESTORE — Telegram Bot с полной админ-панелью
Поддержка: фото, цвета, размеры с ценами, удаление/редактирование.

pip install python-telegram-bot
python bot.py
"""

import logging, json, os, shutil, asyncio
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)

# ═══════════════════════════════════════════
#  НАСТРОЙКИ — читаются из переменных среды
#  Локально: задайте их в .env или прямо здесь
#  На Railway: задайте в Variables в интерфейсе
# ═══════════════════════════════════════════
BOT_TOKEN         = os.environ.get("BOT_TOKEN",         "YOUR_BOT_TOKEN_HERE")
WEBAPP_URL        = os.environ.get("WEBAPP_URL",        "https://your-login.github.io/kitestore/shop_miniapp.html")
ADMIN_CHAT_ID     = int(os.environ.get("ADMIN_CHAT_ID", "123456789"))
PUBLIC_PHOTOS_URL = os.environ.get("PUBLIC_PHOTOS_URL", "https://your-login.github.io/kitestore/photos")
PRODUCTS_FILE     = "products.json"
PHOTOS_DIR        = Path("photos")
# ═══════════════════════════════════════════

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
PHOTOS_DIR.mkdir(exist_ok=True)

# ── Состояния диалога ─────────────────────
(
    ADD_NAME, ADD_PRICE, ADD_OLD_PRICE, ADD_CATEGORY,
    ADD_BADGE, ADD_DESC, ADD_TAGS,
    ADD_COLORS, ADD_SIZES, ADD_PHOTOS,
    EDIT_CHOOSE_FIELD, EDIT_VALUE,
) = range(12)

CATEGORIES = {
    "kites":       "🪁 Кайты",
    "boards":      "🏄 Доски",
    "harnesses":   "🦺 Трапеции",
    "accessories": "🎒 Аксессуары",
}

# ═══════════════════════════════════════════
#  ХРАНИЛИЩЕ
# ═══════════════════════════════════════════

def load_products() -> list:
    if not os.path.exists(PRODUCTS_FILE):
        save_products([])
        return []
    with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_products(products: list):
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

def next_id(products):
    return max((p["id"] for p in products), default=0) + 1

def is_admin(update: Update):
    return update.effective_user.id == ADMIN_CHAT_ID

# ═══════════════════════════════════════════
#  /start
# ═══════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    kb = [
        [InlineKeyboardButton("🛍 Открыть магазин", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("📦 Мои заказы", callback_data="my_orders"),
         InlineKeyboardButton("ℹ️ О нас",      callback_data="about")],
    ]
    if is_admin(update):
        kb.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin_panel")])
    await update.message.reply_text(
        f"🌊 Привет, {user.first_name}!\n\n"
        "🪁 Добро пожаловать в *KITESTORE*\n\n"
        "Профессиональное снаряжение для кайтсёрфинга.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )

# ═══════════════════════════════════════════
#  АДМИН-ПАНЕЛЬ
# ═══════════════════════════════════════════

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = load_products()
    text = (
        f"⚙️ *Админ-панель KITESTORE*\n\n"
        f"📦 Товаров в каталоге: *{len(products)}*\n\n"
        "Выберите действие:"
    )
    kb = [
        [InlineKeyboardButton("➕ Добавить товар",  callback_data="admin_add")],
        [InlineKeyboardButton("📋 Список товаров",  callback_data="admin_list_0")],
        [InlineKeyboardButton("✏️ Редактировать",   callback_data="admin_edit_choose")],
        [InlineKeyboardButton("🗑 Удалить товар",   callback_data="admin_del_choose")],
        [InlineKeyboardButton("🔙 В главное меню",  callback_data="back_start")],
    ]
    markup = InlineKeyboardMarkup(kb)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await admin_panel(update, context)

# ── Список товаров ────────────────────────
PAGE = 5

async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    page = int(q.data.split("_")[-1])
    products = load_products()
    chunk = products[page*PAGE : page*PAGE+PAGE]
    if not chunk:
        await q.edit_message_text("📭 Каталог пуст.", reply_markup=_back_admin())
        return
    lines = []
    for p in chunk:
        base = _base_price(p)
        sizes_str = f"{len(p.get('sizes',[]))} р-ров" if p.get('sizes') else "—"
        colors_str = f"{len(p.get('colors',[]))} цвета" if p.get('colors') else "—"
        photos_str = f"📸 {len(p.get('photos',[]))}" if p.get('photos') else "📷 нет фото"
        lines.append(
            f"{p.get('emoji','🪁')} *{p['name']}*  `ID:{p['id']}`\n"
            f"   💰 {base:,} ₽  •  {CATEGORIES.get(p['category'],p['category'])}\n"
            f"   {photos_str}  •  {sizes_str}  •  {colors_str}"
        )
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("◀️", callback_data=f"admin_list_{page-1}"))
    if (page+1)*PAGE < len(products): nav.append(InlineKeyboardButton("▶️", callback_data=f"admin_list_{page+1}"))
    kb = []
    if nav: kb.append(nav)
    kb.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")])
    await q.edit_message_text(
        f"📋 *Товары (стр.{page+1})*\n\n" + "\n\n".join(lines),
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
    )

def _base_price(p):
    if p.get('sizes'):
        return min(p['price'] + (s.get('priceDelta',0)) for s in p['sizes'])
    return p['price']

# ═══════════════════════════════════════════
#  ДОБАВЛЕНИЕ ТОВАРА
# ═══════════════════════════════════════════

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data['np'] = {'photos': [], 'colors': [], 'sizes': []}
    await q.edit_message_text(
        "➕ *Новый товар — шаг 1/9*\n\n"
        "Введите *название* товара:\n\n_/cancel — отменить_",
        parse_mode="Markdown"
    )
    return ADD_NAME

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['np']['name'] = update.message.text.strip()
    await update.message.reply_text("Шаг 2/9 — Введите *базовую цену* (₽, только цифры):", parse_mode="Markdown")
    return ADD_PRICE

async def add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['np']['price'] = int(update.message.text.strip().replace(" ","").replace(",",""))
    except ValueError:
        await update.message.reply_text("⚠️ Только цифры! Повторите:"); return ADD_PRICE
    await update.message.reply_text("Шаг 3/9 — Введите *старую цену* (для зачёркивания) или `нет`:", parse_mode="Markdown")
    return ADD_OLD_PRICE

async def add_old_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    v = update.message.text.strip().lower()
    if v in ("нет","no","-",""):
        context.user_data['np']['oldPrice'] = None
    else:
        try: context.user_data['np']['oldPrice'] = int(v.replace(" ","").replace(",",""))
        except ValueError:
            await update.message.reply_text("⚠️ Цифры или 'нет':"); return ADD_OLD_PRICE
    kb = [[InlineKeyboardButton(l, callback_data=f"cat_{k}")] for k,l in CATEGORIES.items()]
    await update.message.reply_text("Шаг 4/9 — Выберите *категорию*:", parse_mode="Markdown",
                                    reply_markup=InlineKeyboardMarkup(kb))
    return ADD_CATEGORY

async def add_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data['np']['category'] = q.data.replace("cat_","")
    await q.edit_message_text("Шаг 5/9 — Введите *бейдж* на карточке (ХИТ, NEW, -20% …) или `нет`:", parse_mode="Markdown")
    return ADD_BADGE

async def add_badge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    v = update.message.text.strip()
    context.user_data['np']['badge'] = None if v.lower() in ("нет","no","-","") else v
    context.user_data['np']['emoji'] = "🪁"  # дефолт
    await update.message.reply_text("Шаг 6/9 — Введите *описание* товара:", parse_mode="Markdown")
    return ADD_DESC

async def add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['np']['desc'] = update.message.text.strip()
    await update.message.reply_text("Шаг 7/9 — Введите *теги* через запятую:\nПример: `Фрирайд, Профи, 3-strut`", parse_mode="Markdown")
    return ADD_TAGS

async def add_tags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['np']['tags'] = [t.strip() for t in update.message.text.split(",") if t.strip()]
    await update.message.reply_text(
        "Шаг 8/9 — Добавьте *цвета и размеры с ценами*.\n\n"
        "📌 *Формат цветов* (по одному на строку):\n`Синий #1a5fe8`\n`Красный #cc0000`\n\n"
        "📌 *Формат размеров* (по одному на строку):\n`9м² -10000` (отрицательная дельта)\n`12м² 0` (базовая цена)\n`15м² +12000`\n\n"
        "Пример сообщения:\n```\nЦВЕТА:\nСиний #0055ff\nЧёрный #111111\n\nРАЗМЕРЫ:\n9м² -10000\n12м² 0\n15м² 12000\n```\n\n"
        "_Если нет вариантов — напишите `нет`_",
        parse_mode="Markdown"
    )
    return ADD_COLORS

async def add_colors_sizes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Парсит цвета и размеры из одного сообщения"""
    text = update.message.text.strip()
    np = context.user_data['np']

    if text.lower() != "нет":
        lines = text.split('\n')
        mode = None
        for line in lines:
            line = line.strip()
            if not line: continue
            if 'ЦВЕТА' in line.upper() or 'COLORS' in line.upper(): mode = 'colors'; continue
            if 'РАЗМЕРЫ' in line.upper() or 'SIZES' in line.upper(): mode = 'sizes'; continue
            if mode == 'colors':
                parts = line.rsplit(' ', 1)
                if len(parts) == 2 and parts[1].startswith('#'):
                    np['colors'].append({'name': parts[0].strip(), 'value': parts[1].strip()})
            elif mode == 'sizes':
                parts = line.rsplit(' ', 1)
                if len(parts) == 2:
                    try:
                        delta = int(parts[1].replace('+',''))
                        np['sizes'].append({'label': parts[0].strip(), 'priceDelta': delta})
                    except ValueError: pass

    await update.message.reply_text(
        "Шаг 9/9 — Отправьте *фотографии* товара (можно несколько).\n\n"
        "📸 Отправьте фото по одному или альбомом.\n"
        "Когда закончите — нажмите кнопку ✅ Готово.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Готово (без фото)", callback_data="photos_done")]])
    )
    return ADD_PHOTOS

async def add_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает фото и сохраняет"""
    np = context.user_data['np']
    photo = update.message.photo[-1]  # лучшее качество
    file = await context.bot.get_file(photo.file_id)

    # Создаём временный ID если ещё нет
    if 'tmp_id' not in np:
        np['tmp_id'] = f"tmp_{update.message.message_id}"
    pid = np['tmp_id']
    photo_dir = PHOTOS_DIR / str(pid)
    photo_dir.mkdir(exist_ok=True)

    idx = len(np['photos'])
    filename = f"{idx}.jpg"
    filepath = photo_dir / filename
    await file.download_to_drive(filepath)

    photo_url = f"{PUBLIC_PHOTOS_URL}/{pid}/{filename}"
    np['photos'].append(photo_url)

    await update.message.reply_text(
        f"📸 Фото {idx+1} добавлено!\n_Отправьте ещё или нажмите Готово._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Готово", callback_data="photos_done")]])
    )
    return ADD_PHOTOS

async def photos_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    np = context.user_data['np']
    products = load_products()
    np['id'] = next_id(products)
    # Переименовать папку фото с реальным ID
    if 'tmp_id' in np:
        old_dir = PHOTOS_DIR / np['tmp_id']
        new_dir = PHOTOS_DIR / str(np['id'])
        if old_dir.exists():
            shutil.move(str(old_dir), str(new_dir))
            # Обновить URL фото
            np['photos'] = [url.replace(np['tmp_id'], str(np['id'])) for url in np['photos']]
        del np['tmp_id']

    products.append(np)
    save_products(products)

    price_info = f"{np['price']:,} ₽"
    if np.get('sizes'):
        prices = [np['price'] + s.get('priceDelta',0) for s in np['sizes']]
        price_info = f"{min(prices):,}–{max(prices):,} ₽"

    sizes_str  = ", ".join(s['label'] for s in np.get('sizes',[])) or "нет"
    colors_str = ", ".join(c['name'] for c in np.get('colors',[])) or "нет"
    photos_str = f"{len(np['photos'])} фото" if np.get('photos') else "нет фото"

    await q.edit_message_text(
        f"✅ *Товар добавлен!*\n\n"
        f"{np.get('emoji','🪁')} *{np['name']}*\n"
        f"💰 {price_info}\n"
        f"🏷 {CATEGORIES.get(np['category'],np['category'])}\n"
        f"📐 Размеры: {sizes_str}\n"
        f"🎨 Цвета: {colors_str}\n"
        f"📸 Фото: {photos_str}\n"
        f"🆔 ID: `{np['id']}`",
        parse_mode="Markdown",
        reply_markup=_back_admin()
    )
    context.user_data.pop('np', None)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Отменено.", reply_markup=_back_admin())
    return ConversationHandler.END

# ═══════════════════════════════════════════
#  УДАЛЕНИЕ
# ═══════════════════════════════════════════

async def del_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    products = load_products()
    if not products:
        await q.edit_message_text("📭 Каталог пуст.", reply_markup=_back_admin()); return
    kb = [[InlineKeyboardButton(f"{p.get('emoji','🪁')} {p['name']} ({_base_price(p):,}₽)",
                                callback_data=f"del_cf_{p['id']}")] for p in products]
    kb.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")])
    await q.edit_message_text("🗑 Выберите товар для удаления:", parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup(kb))

async def del_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pid = int(q.data.split("_")[-1])
    products = load_products()
    p = next((x for x in products if x['id']==pid), None)
    if not p:
        await q.edit_message_text("⚠️ Не найден.", reply_markup=_back_admin()); return
    kb = [[InlineKeyboardButton("✅ Да, удалить", callback_data=f"del_do_{pid}"),
           InlineKeyboardButton("❌ Отмена",       callback_data="admin_panel")]]
    await q.edit_message_text(f"🗑 Удалить *{p['name']}*?\n\nЭто действие необратимо.",
                              parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def del_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pid = int(q.data.split("_")[-1])
    products = load_products()
    p = next((x for x in products if x['id']==pid), None)
    name = p['name'] if p else str(pid)
    # Удалить папку с фото
    photo_dir = PHOTOS_DIR / str(pid)
    if photo_dir.exists():
        shutil.rmtree(str(photo_dir))
    products = [x for x in products if x['id']!=pid]
    save_products(products)
    await q.edit_message_text(f"✅ Товар *{name}* удалён.\nОсталось: {len(products)}",
                              parse_mode="Markdown", reply_markup=_back_admin())

# ═══════════════════════════════════════════
#  РЕДАКТИРОВАНИЕ
# ═══════════════════════════════════════════

EDIT_FIELDS = {
    "name":     "Название",
    "price":    "Базовая цена (₽)",
    "oldPrice": "Старая цена (₽ или 'нет')",
    "desc":     "Описание",
    "badge":    "Бейдж",
    "tags":     "Теги (через запятую)",
    "colors":   "Цвета (формат: Синий #hex, каждый с новой строки)",
    "sizes":    "Размеры (формат: 12м² 0, каждый с новой строки)",
}

async def edit_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    products = load_products()
    if not products:
        await q.edit_message_text("📭 Каталог пуст.", reply_markup=_back_admin()); return
    kb = [[InlineKeyboardButton(f"{p.get('emoji','🪁')} {p['name']}",
                                callback_data=f"edit_p_{p['id']}")] for p in products]
    kb.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")])
    await q.edit_message_text("✏️ Выберите товар:", parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup(kb))

async def edit_field_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pid = int(q.data.split("_")[-1])
    context.user_data['edit_id'] = pid
    products = load_products()
    p = next((x for x in products if x['id']==pid), None)
    if not p:
        await q.edit_message_text("⚠️ Не найден.", reply_markup=_back_admin()); return
    kb = [[InlineKeyboardButton(label, callback_data=f"ef_{key}")] for key, label in EDIT_FIELDS.items()]
    kb.append([InlineKeyboardButton("📸 Обновить фото", callback_data=f"edit_photos_{pid}")])
    kb.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_edit_choose")])
    await q.edit_message_text(
        f"✏️ *{p['name']}*\n\nЧто изменить?",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
    )
    return EDIT_CHOOSE_FIELD

async def edit_field_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    field = q.data.replace("ef_","")
    context.user_data['edit_field'] = field
    label = EDIT_FIELDS.get(field, field)
    hints = {
        "colors": "Пример:\n`Синий #0055ff`\n`Красный #cc0000`",
        "sizes":  "Пример:\n`9м² -10000`\n`12м² 0`\n`15м² 12000`",
        "tags":   "Пример: `Фрирайд, Профи, LEI`",
    }
    hint = hints.get(field, "")
    await q.edit_message_text(
        f"✏️ Новое значение для *{label}*:\n\n{hint}\n\n_/cancel — отменить_",
        parse_mode="Markdown"
    )
    return EDIT_VALUE

async def edit_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pid   = context.user_data.get('edit_id')
    field = context.user_data.get('edit_field')
    value = update.message.text.strip()
    products = load_products()
    p = next((x for x in products if x['id']==pid), None)
    if not p:
        await update.message.reply_text("⚠️ Товар не найден.")
        return ConversationHandler.END

    if field == 'price':
        try: value = int(value.replace(" ","").replace(",",""))
        except: await update.message.reply_text("⚠️ Только цифры."); return EDIT_VALUE
    elif field == 'oldPrice':
        value = None if value.lower() in ("нет","no","-","") else int(value.replace(" ","").replace(",",""))
    elif field == 'tags':
        value = [t.strip() for t in value.split(",") if t.strip()]
    elif field == 'colors':
        colors = []
        for line in value.split('\n'):
            line = line.strip()
            parts = line.rsplit(' ', 1)
            if len(parts)==2 and parts[1].startswith('#'):
                colors.append({'name': parts[0].strip(), 'value': parts[1].strip()})
        value = colors
    elif field == 'sizes':
        sizes = []
        for line in value.split('\n'):
            line = line.strip()
            parts = line.rsplit(' ', 1)
            if len(parts)==2:
                try: sizes.append({'label': parts[0].strip(), 'priceDelta': int(parts[1].replace('+',''))})
                except: pass
        value = sizes

    p[field] = value
    save_products(products)
    label = EDIT_FIELDS.get(field, field)
    await update.message.reply_text(
        f"✅ *{label}* обновлено для товара *{p['name']}*!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✏️ Ещё изменить", callback_data=f"edit_p_{pid}"),
            InlineKeyboardButton("⚙️ Панель",       callback_data="admin_panel"),
        ]])
    )
    return ConversationHandler.END

# ── Добавление фото к существующему товару ─
async def edit_photos_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pid = int(q.data.split("_")[-1])
    context.user_data['photo_edit_id'] = pid
    products = load_products()
    p = next((x for x in products if x['id']==pid), None)
    current = len(p.get('photos',[])) if p else 0
    await q.edit_message_text(
        f"📸 *Фото для товара {p['name']}*\n\n"
        f"Сейчас: {current} фото\n\n"
        "Отправьте новые фото (они заменят старые).\nКогда закончите — нажмите Готово.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Готово", callback_data=f"photo_edit_done_{pid}")]])
    )
    # Используем ADD_PHOTOS состояние через отдельный механизм
    context.user_data['photo_edit_mode'] = True
    context.user_data['photo_edit_photos'] = []

async def photo_edit_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('photo_edit_mode'):
        return
    pid = context.user_data.get('photo_edit_id')
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    photo_dir = PHOTOS_DIR / str(pid)
    photo_dir.mkdir(exist_ok=True)
    idx = len(context.user_data['photo_edit_photos'])
    filename = f"{idx}.jpg"
    await file.download_to_drive(photo_dir / filename)
    url = f"{PUBLIC_PHOTOS_URL}/{pid}/{filename}"
    context.user_data['photo_edit_photos'].append(url)
    await update.message.reply_text(
        f"📸 Фото {idx+1} загружено!",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Готово", callback_data=f"photo_edit_done_{pid}")
        ]])
    )

async def photo_edit_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pid = int(q.data.split("_")[-1])
    photos = context.user_data.get('photo_edit_photos', [])
    products = load_products()
    p = next((x for x in products if x['id']==pid), None)
    if p and photos:
        p['photos'] = photos
        save_products(products)
        await q.edit_message_text(f"✅ Обновлено *{len(photos)} фото* для *{p['name']}*!",
                                  parse_mode="Markdown", reply_markup=_back_admin())
    else:
        await q.edit_message_text("Фото не изменены.", reply_markup=_back_admin())
    context.user_data.pop('photo_edit_mode', None)
    context.user_data.pop('photo_edit_photos', None)
    context.user_data.pop('photo_edit_id', None)

# ═══════════════════════════════════════════
#  ЗАКАЗЫ
# ═══════════════════════════════════════════

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.effective_message.web_app_data.data
    try:
        order = json.loads(data)
        items, total = order.get("items",[]), order.get("total",0)
        user = update.effective_user
        oid  = f"{user.id}-{update.effective_message.message_id}"

        lines = "\n".join(
            f"  • {i['name']}"
            f"{' ('+i['color']+')' if i.get('color') else ''}"
            f"{' '+i['size'] if i.get('size') else ''}"
            f" × {i['qty']} — {i['price']*i['qty']:,} ₽"
            for i in items
        )

        await update.effective_message.reply_text(
            f"✅ *Заказ #{oid} принят!*\n\n📋 *Состав:*\n{lines}\n\n💰 *Итого: {total:,} ₽*\n\n"
            "Мы свяжемся с вами для подтверждения доставки. 🌊",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🛍 Продолжить", web_app=WebAppInfo(url=WEBAPP_URL))
            ]])
        )

        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                f"🆕 *Заказ #{oid}*\n\n"
                f"👤 [{user.full_name}](tg://user?id={user.id})\n"
                f"🆔 `{user.id}`\n"
                f"{'📱 @'+user.username if user.username else ''}\n\n"
                f"📋 *Товары:*\n{lines}\n\n"
                f"💰 *Сумма: {total:,} ₽*"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Принять",   callback_data=f"ord_accept_{user.id}_{oid}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"ord_decline_{user.id}_{oid}"),
            ]])
        )
    except Exception as e:
        logger.error(f"Ошибка заказа: {e}")

# ═══════════════════════════════════════════
#  КОЛБЭКИ
# ═══════════════════════════════════════════

async def handle_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    d = q.data

    if d == "admin_panel":
        if not is_admin(update): await q.edit_message_text("⛔ Нет доступа."); return
        await admin_panel(update, context)

    elif d == "back_start":
        products = load_products()
        kb = [[InlineKeyboardButton("🛍 Открыть магазин", web_app=WebAppInfo(url=WEBAPP_URL))],
              [InlineKeyboardButton("📦 Мои заказы", callback_data="my_orders"),
               InlineKeyboardButton("ℹ️ О нас",      callback_data="about")]]
        if is_admin(update):
            kb.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin_panel")])
        await q.edit_message_text("🪁 *KITESTORE*\n\nВыберите действие:",
                                  parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif d == "my_orders":
        await q.edit_message_text("📦 *Ваши заказы*\n\nИстория пуста.", parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_start")]]))

    elif d == "about":
        await q.edit_message_text(
            "ℹ️ *KITESTORE*\n\nПрофессиональное снаряжение для кайтсёрфинга\n\n"
            "🌊 Доставка по всей России\n💳 Оплата при получении или онлайн\n"
            "🔄 Возврат 14 дней\n📞 Поддержка 24/7",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_start")]]))

    elif d.startswith("ord_accept_"):
        _, _, cid, oid = d.split("_", 3)
        await context.bot.send_message(int(cid),
            f"🎉 *Заказ #{oid} подтверждён!*\nМенеджер свяжется с вами в течение 30 минут.", parse_mode="Markdown")
        await q.edit_message_reply_markup(None)
        await q.message.reply_text(f"✅ Заказ #{oid} принят.")

    elif d.startswith("ord_decline_"):
        _, _, cid, oid = d.split("_", 3)
        await context.bot.send_message(int(cid),
            f"😔 *Заказ #{oid} отклонён.*\nПожалуйста, свяжитесь с нами.", parse_mode="Markdown")
        await q.edit_message_reply_markup(None)
        await q.message.reply_text(f"❌ Заказ #{oid} отклонён.")

    elif d.startswith("photo_edit_done_"):
        await photo_edit_done(update, context)

# ═══════════════════════════════════════════
#  ХЕЛПЕРЫ
# ═══════════════════════════════════════════

def _back_admin():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin_panel")]])

# ═══════════════════════════════════════════
#  ЗАПУСК
# ═══════════════════════════════════════════

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # ConversationHandler — добавление товара
    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_start, pattern="^admin_add$")],
        states={
            ADD_NAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            ADD_PRICE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, add_price)],
            ADD_OLD_PRICE:[MessageHandler(filters.TEXT & ~filters.COMMAND, add_old_price)],
            ADD_CATEGORY: [CallbackQueryHandler(add_category, pattern="^cat_")],
            ADD_BADGE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, add_badge)],
            ADD_DESC:     [MessageHandler(filters.TEXT & ~filters.COMMAND, add_desc)],
            ADD_TAGS:     [MessageHandler(filters.TEXT & ~filters.COMMAND, add_tags)],
            ADD_COLORS:   [MessageHandler(filters.TEXT & ~filters.COMMAND, add_colors_sizes)],
            ADD_PHOTOS:   [
                MessageHandler(filters.PHOTO, add_photo),
                CallbackQueryHandler(photos_done, pattern="^photos_done$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # ConversationHandler — редактирование
    edit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_field_choose, pattern=r"^edit_p_\d+$")],
        states={
            EDIT_CHOOSE_FIELD: [CallbackQueryHandler(edit_field_ask, pattern="^ef_")],
            EDIT_VALUE:        [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_save)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("cancel", cancel))

    app.add_handler(add_conv)
    app.add_handler(edit_conv)

    app.add_handler(CallbackQueryHandler(admin_list,        pattern=r"^admin_list_\d+$"))
    app.add_handler(CallbackQueryHandler(del_choose,        pattern="^admin_del_choose$"))
    app.add_handler(CallbackQueryHandler(del_confirm,       pattern=r"^del_cf_\d+$"))
    app.add_handler(CallbackQueryHandler(del_do,            pattern=r"^del_do_\d+$"))
    app.add_handler(CallbackQueryHandler(edit_choose,       pattern="^admin_edit_choose$"))
    app.add_handler(CallbackQueryHandler(edit_photos_start, pattern=r"^edit_photos_\d+$"))

    app.add_handler(MessageHandler(filters.PHOTO, photo_edit_receive))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    app.add_handler(CallbackQueryHandler(handle_cb))

    logger.info("🪁 KITESTORE бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

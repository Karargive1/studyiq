import os
import logging
import sqlite3
from pathlib import Path
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler,
)

TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "5865382078").split(",") if x.strip()}
DB_PATH = os.getenv("DB_PATH", "student_iq.db")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

ADD_MATERIAL_TITLE, ADD_MATERIAL_FILE = range(2)
ADD_Q_TEXT, ADD_Q_A, ADD_Q_B, ADD_Q_C, ADD_Q_D, ADD_Q_CORRECT = range(2, 8)
BROADCAST_TEXT = 8

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, full_name TEXT, grade TEXT,
            branch TEXT, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT, grade TEXT, branch TEXT,
            subject TEXT, title TEXT, file_id TEXT, file_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, grade TEXT, branch TEXT,
            subject TEXT, question TEXT, a TEXT, b TEXT, c TEXT, d TEXT,
            correct TEXT
        )""")

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 المواد والملازم", callback_data="materials")],
        [InlineKeyboardButton("📝 اختبر نفسك", callback_data="quiz")],
        [InlineKeyboardButton("👤 ملفي الدراسي", callback_data="profile")],
        [InlineKeyboardButton("📢 الإعلانات", callback_data="announcements")],
    ])

def grades_menu(prefix="grade"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("الرابع الإعدادي", callback_data=f"{prefix}:الرابع")],
        [InlineKeyboardButton("الخامس الإعدادي", callback_data=f"{prefix}:الخامس")],
        [InlineKeyboardButton("السادس الإعدادي", callback_data=f"{prefix}:السادس")],
        [InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data="home")],
    ])

def branches_menu(prefix, grade):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("علمي", callback_data=f"{prefix}branch:{grade}:علمي")],
        [InlineKeyboardButton("أدبي", callback_data=f"{prefix}branch:{grade}:أدبي")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data=f"{prefix}:back")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    with db() as c:
        c.execute("INSERT OR IGNORE INTO users(user_id, full_name) VALUES(?,?)",
                  (u.id, u.full_name))
    await update.message.reply_text(
        f"أهلاً {u.first_name} في منصة طالب العراق 🎓\n"
        "اختر الخدمة التي تحتاجها من القائمة:",
        reply_markup=main_menu()
    )

async def home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("القائمة الرئيسية 🎓", reply_markup=main_menu())

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "home":
        return await q.edit_message_text("القائمة الرئيسية 🎓", reply_markup=main_menu())

    if data == "materials":
        return await q.edit_message_text("اختر مرحلتك:", reply_markup=grades_menu("matgrade"))

    if data.startswith("matgrade:"):
        grade = data.split(":", 1)[1]
        context.user_data["grade"] = grade
        return await q.edit_message_text(
            f"اختر فرع {grade} الإعدادي:",
            reply_markup=branches_menu("mat", grade)
        )

    if data.startswith("mat:"):
        parts = data.split(":")
        if parts[1] == "back":
            return await q.edit_message_text("اختر مرحلتك:", reply_markup=grades_menu("matgrade"))
        grade, branch = parts[1], parts[2]
        context.user_data["grade"], context.user_data["branch"] = grade, branch
        with db() as c:
            rows = c.execute(
                "SELECT DISTINCT subject FROM materials WHERE grade=? AND branch=? ORDER BY subject",
                (grade, branch)
            ).fetchall()
        if not rows:
            return await q.edit_message_text(
                "لا توجد مواد مضافة لهذه المرحلة حالياً. تابعنا، وسيتم رفع المحتوى قريباً.",
                reply_markup=main_menu()
            )
        kb = [[InlineKeyboardButton(r["subject"], callback_data=f"subject:{grade}:{branch}:{r['subject']}")]
              for r in rows]
        kb.append([InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")])
        return await q.edit_message_text("اختر المادة:", reply_markup=InlineKeyboardMarkup(kb))

    if data.startswith("subject:"):
        _, grade, branch, subject = data.split(":", 3)
        with db() as c:
            rows = c.execute(
                "SELECT id,title FROM materials WHERE grade=? AND branch=? AND subject=? ORDER BY id DESC",
                (grade, branch, subject)
            ).fetchall()
        if not rows:
            return await q.edit_message_text("لا توجد ملفات لهذه المادة بعد.", reply_markup=main_menu())
        kb = [[InlineKeyboardButton(r["title"], callback_data=f"file:{r['id']}")] for r in rows]
        kb.append([InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")])
        return await q.edit_message_text(f"ملفات مادة {subject}:", reply_markup=InlineKeyboardMarkup(kb))

    if data.startswith("file:"):
        material_id = int(data.split(":")[1])
        with db() as c:
            row = c.execute("SELECT * FROM materials WHERE id=?", (material_id,)).fetchone()
        if not row:
            return await q.edit_message_text("عذراً، الملف غير موجود.")
        caption = f"📘 {row['title']}\n{row['grade']} - {row['branch']} - {row['subject']}"
        if row["file_type"] == "document":
            await context.bot.send_document(q.message.chat_id, row["file_id"], caption=caption)
        elif row["file_type"] == "video":
            await context.bot.send_video(q.message.chat_id, row["file_id"], caption=caption)
        elif row["file_type"] == "photo":
            await context.bot.send_photo(q.message.chat_id, row["file_id"], caption=caption)
        else:
            await context.bot.send_audio(q.message.chat_id, row["file_id"], caption=caption)
        return

    if data == "profile":
        with db() as c:
            row = c.execute("SELECT grade,branch FROM users WHERE user_id=?",
                            (q.from_user.id,)).fetchone()
        grade = row["grade"] if row and row["grade"] else "غير محددة"
        branch = row["branch"] if row and row["branch"] else "غير محدد"
        return await q.edit_message_text(
            f"👤 ملفك الدراسي\nالمرحلة: {grade}\nالفرع: {branch}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("تحديث المرحلة", callback_data="setgrade")],
                [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")]
            ])
        )

    if data == "setgrade":
        return await q.edit_message_text("اختر مرحلتك:", reply_markup=grades_menu("profilegrade"))

    if data.startswith("profilegrade:"):
        grade = data.split(":", 1)[1]
        context.user_data["profile_grade"] = grade
        return await q.edit_message_text("اختر الفرع:", reply_markup=branches_menu("profile", grade))

    if data.startswith("profilebranch:"):
        _, grade, branch = data.split(":")
        with db() as c:
            c.execute("UPDATE users SET grade=?, branch=? WHERE user_id=?",
                      (grade, branch, q.from_user.id))
        return await q.edit_message_text("تم تحديث ملفك الدراسي بنجاح ✅", reply_markup=main_menu())

    if data == "quiz":
        return await q.edit_message_text("اختر مرحلتك للاختبار:", reply_markup=grades_menu("quizgrade"))

    if data.startswith("quizgrade:"):
        grade = data.split(":", 1)[1]
        context.user_data["quiz_grade"] = grade
        return await q.edit_message_text("اختر الفرع:", reply_markup=branches_menu("quiz", grade))

    if data.startswith("quizbranch:"):
        _, grade, branch = data.split(":")
        with db() as c:
            rows = c.execute(
                "SELECT * FROM questions WHERE grade=? AND branch=? ORDER BY RANDOM() LIMIT 1",
                (grade, branch)
            ).fetchall()
        if not rows:
            return await q.edit_message_text("لا توجد أسئلة متاحة لهذه المرحلة حالياً.", reply_markup=main_menu())
        row = rows[0]
        context.user_data["active_question"] = row["id"]
        kb = [
            [InlineKeyboardButton(f"أ) {row['a']}", callback_data=f"answer:{row['id']}:a")],
            [InlineKeyboardButton(f"ب) {row['b']}", callback_data=f"answer:{row['id']}:b")],
            [InlineKeyboardButton(f"ج) {row['c']}", callback_data=f"answer:{row['id']}:c")],
            [InlineKeyboardButton(f"د) {row['d']}", callback_data=f"answer:{row['id']}:d")],
        ]
        return await q.edit_message_text(f"📝 {row['subject']}\n\n{row['question']}",
                                         reply_markup=InlineKeyboardMarkup(kb))

    if data.startswith("answer:"):
        _, qid, choice = data.split(":")
        with db() as c:
            row = c.execute("SELECT * FROM questions WHERE id=?", (int(qid),)).fetchone()
        if not row:
            return await q.edit_message_text("انتهى هذا الاختبار.")
        if choice == row["correct"].lower():
            msg = "إجابة صحيحة! أحسنت 🎉"
        else:
            msg = f"إجابة غير صحيحة. الإجابة الصحيحة: {row['correct'].upper()}"
        return await q.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("سؤال آخر", callback_data=f"quizgrade:{row['grade']}")],
            [InlineKeyboardButton("الرئيسية", callback_data="home")]
        ]))

    if data == "announcements":
        return await q.edit_message_text(
            "📢 ستظهر هنا إعلانات المنصة وتنبيهاتها.\nتابع البوت لتصلك التحديثات.",
            reply_markup=main_menu()
        )

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("هذه الخاصية مخصصة للإدارة.")
    await update.message.reply_text(
        "لوحة الإدارة:\n"
        "/add_material — إضافة ملزمة أو ملف\n"
        "/add_question — إضافة سؤال اختباري\n"
        "/broadcast — إرسال إعلان لكل الطلاب\n"
        "/stats — إحصائيات الطلاب والمحتوى"
    )

async def add_material_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    await update.message.reply_text(
        "أرسل بيانات الملف بهذا الترتيب في رسالة واحدة:\n"
        "المرحلة | الفرع | المادة | عنوان الملف\n"
        "مثال: السادس | علمي | رياضيات | ملزمة الفصل الأول"
    )
    return ADD_MATERIAL_TITLE

async def add_material_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = [p.strip() for p in update.message.text.split("|")]
    if len(parts) != 4:
        await update.message.reply_text("الصيغة غير صحيحة. أرسل 4 حقول تفصل بينها علامة |")
        return ADD_MATERIAL_TITLE
    context.user_data["material"] = parts
    await update.message.reply_text("الآن أرسل الملف (PDF أو صورة أو فيديو أو صوت).")
    return ADD_MATERIAL_FILE

async def add_material_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.document:
        file_id, file_type = msg.document.file_id, "document"
    elif msg.photo:
        file_id, file_type = msg.photo[-1].file_id, "photo"
    elif msg.video:
        file_id, file_type = msg.video.file_id, "video"
    elif msg.audio:
        file_id, file_type = msg.audio.file_id, "audio"
    else:
        await msg.reply_text("أرسل ملف PDF أو صورة أو فيديو أو صوت.")
        return ADD_MATERIAL_FILE
    grade, branch, subject, title = context.user_data["material"]
    with db() as c:
        c.execute(
            "INSERT INTO materials(grade,branch,subject,title,file_id,file_type) VALUES(?,?,?,?,?,?)",
            (grade, branch, subject, title, file_id, file_type)
        )
    context.user_data.pop("material", None)
    await msg.reply_text("تمت إضافة الملف بنجاح ✅")
    return ConversationHandler.END

async def add_question_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    await update.message.reply_text(
        "أرسل بيانات السؤال بهذا الترتيب في رسالة واحدة:\n"
        "المرحلة | الفرع | المادة | نص السؤال | الخيار أ | الخيار ب | الخيار ج | الخيار د | الإجابة (a/b/c/d)"
    )
    return ADD_Q_TEXT

async def add_question_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = [x.strip() for x in update.message.text.split("|")]
    if len(p) != 9 or p[-1].lower() not in ("a", "b", "c", "d"):
        await update.message.reply_text("تأكد من إدخال 9 حقول، والإجابة الأخيرة a أو b أو c أو d.")
        return ADD_Q_TEXT
    with db() as c:
        c.execute("""INSERT INTO questions(grade,branch,subject,question,a,b,c,d,correct)
                     VALUES(?,?,?,?,?,?,?,?,?)""", (*p[:-1], p[-1].lower()))
    await update.message.reply_text("تمت إضافة السؤال بنجاح ✅")
    return ConversationHandler.END

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    await update.message.reply_text("أرسل نص الإعلان الذي تريد إرساله لجميع الطلاب.")
    return BROADCAST_TEXT

async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    with db() as c:
        ids = [r["user_id"] for r in c.execute("SELECT user_id FROM users").fetchall()]
    sent = 0
    for uid in ids:
        try:
            await context.bot.send_message(uid, f"📢 إعلان من منصة طالب العراق\n\n{text}")
            sent += 1
        except Exception as e:
            log.warning("Broadcast to %s failed: %s", uid, e)
    await update.message.reply_text(f"انتهى الإرسال. وصل الإعلان إلى {sent} من أصل {len(ids)} طالباً.")
    return ConversationHandler.END

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    with db() as c:
        users = c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        mats = c.execute("SELECT COUNT(*) n FROM materials").fetchone()["n"]
        qs = c.execute("SELECT COUNT(*) n FROM questions").fetchone()["n"]
    await update.message.reply_text(f"📊 الإحصائيات\nالطلاب: {users}\nالملفات: {mats}\nالأسئلة: {qs}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Set it in the hosting environment.")
    init_db()
    app = Application.builder().token(TOKEN).build()
    material_conv = ConversationHandler(
        entry_points=[CommandHandler("add_material", add_material_start)],
        states={
            ADD_MATERIAL_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_material_details)],
            ADD_MATERIAL_FILE: [MessageHandler((filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO) & ~filters.COMMAND, add_material_file)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    question_conv = ConversationHandler(
        entry_points=[CommandHandler("add_question", add_question_start)],
        states={ADD_Q_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_save)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={BROADCAST_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_send)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(material_conv)
    app.add_handler(question_conv)
    app.add_handler(broadcast_conv)
    app.add_handler(CallbackQueryHandler(menu_callback))
    log.info("Student IQ bot is running")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

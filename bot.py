#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime
import csv
from io import StringIO
import os
import yaml
from dotenv import load_dotenv

# =============================================================================
# CONFIG & QUESTIONS LOADING
# =============================================================================

def load_config():
    token = os.environ["BOT_TOKEN"]
    admin_id = int(os.environ["ADMIN_ID"])
    return token, admin_id


def load_questions(path="questions.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data


load_dotenv()
BOT_TOKEN, ADMIN_ID = load_config()
QUESTIONS = load_questions()

# =============================================================================
# DATA STORAGE
# =============================================================================

participants = {}
answers = {}
current_question = None
current_question_respondents: set = set()
quiz_active = False
quiz_start_time = None

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_display_name(user):
    if user.username:
        base = f"@{user.username}"
    elif user.last_name:
        base = f"{user.first_name} {user.last_name}"
    else:
        base = user.first_name or f"User_{str(user.id)[-4:]}"

    if user.username and user.first_name:
        fname = user.first_name.split()[0]
        if fname.lower() not in user.username.lower():
            return f"{fname} ({base})"

    return base


def is_admin(user_id, admin_id=None):
    if admin_id is None:
        admin_id = ADMIN_ID
    return user_id == admin_id


def calculate_score(user_id, answers, questions):

    if user_id not in answers:
        return 0, 0

    user_answers = answers[user_id]
    correct = 0
    total = 0

    for qid, ans in user_answers.items():
        if qid in questions:
            total += 1
            if questions[qid]["correct"] == ans:
                correct += 1

    return correct, total


def build_leaderboard(participants, answers, questions, limit=10):
    total_questions = len(questions)
    results = []
    for user_id, info in participants.items():
        name = info.get("name", "Unknown")
        correct, _ = calculate_score(user_id, answers, questions)
        results.append((name, correct, total_questions))
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:limit]


def get_correct_answer_text(qid, questions=None):
    if questions is None:
        questions = QUESTIONS

    if qid not in questions:
        return "N/A"

    correct_val = questions[qid]["correct"]
    for text, val in questions[qid]["options"]:
        if val == correct_val:
            return text
    return "N/A"

# =============================================================================
# PARTICIPANT COMMANDS
# =============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if is_admin(user_id):
        await update.message.reply_text("👑 Вы администратор квиза")
        return

    participants[user_id] = {
        "name": get_display_name(user),
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "joined": datetime.now().strftime("%H:%M:%S"),
        "joined_date": datetime.now().strftime("%Y-%m-%d")
    }

    await update.message.reply_text(
        f"👋 Привет, *{participants[user_id]['name']}*!\n\n"
        f"✅ Вы зарегистрированы в квизе\n"
        f"📛 Ваше имя: _{participants[user_id]['name']}_\n\n"
        f"Ждите вопросы от ведущего... 🎮",
        parse_mode='Markdown'
    )



# =============================================================================
# ADMIN COMMANDS
# =============================================================================

async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    global quiz_active, quiz_start_time
    quiz_active = True
    quiz_start_time = datetime.now()

    await update.message.reply_text(
        f"🎮 **Квиз запущен!**\n\n"
        f"⏰ Время: {quiz_start_time.strftime('%H:%M:%S')}\n"
        f"👥 Участников: {len(participants)}\n\n"
        f"Используйте /q1, /q2... для отправки вопросов",
        parse_mode='Markdown'
    )


async def stop_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    global quiz_active, current_question
    quiz_active = False
    current_question = None

    await update.message.reply_text("🛑 Квиз остановлен. Ответы больше не принимаются.")


async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not quiz_active:
        await update.message.reply_text("⚠️ Сначала запустите квиз: /start_quiz")
        return

    cmd = update.message.text.split()[0]
    q_id = cmd[1:]

    if q_id not in QUESTIONS:
        await update.message.reply_text(
            f"⚠️ Вопрос *{q_id}* не найден\n\n"
            f"Доступные: {', '.join(QUESTIONS.keys())}",
            parse_mode='Markdown'
        )
        return

    global current_question, current_question_respondents
    current_question = q_id
    current_question_respondents = set()
    q = QUESTIONS[q_id]

    keyboard = [
        [InlineKeyboardButton(text, callback_data=f"{q_id}:{val}")]
        for text, val in q["options"]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    sent = 0
    failed = 0
    for user_id in participants.keys():
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"<b>{q['text']}</b>\n\n⏱️ Ваш вариант...",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            sent += 1
        except Exception as e:
            failed += 1
            print(f"Failed to send to {user_id}: {e}")

    await update.message.reply_text(
        f"✅ Вопрос *{q_id}* отправлен!",
        parse_mode='Markdown'
    )


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if ":" not in data:
        return

    q_id, answer = data.split(":", 1)

    if q_id != current_question:
        await query.edit_message_text(
            "⏰ *Этот вопрос уже закрыт*",
            parse_mode='Markdown'
        )
        return

    if user_id in current_question_respondents:
        return  # already answered this question instance, ignore

    current_question_respondents.add(user_id)
    if user_id not in answers:
        answers[user_id] = {}
    answers[user_id][q_id] = answer

    answer_text = answer
    for text, val in QUESTIONS[q_id]["options"]:
        if val == answer:
            answer_text = text
            break

    await query.edit_message_text(
        f"✅ <b>Ответ принят!</b>\n\nВаш выбор: <i>{answer_text}</i>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([]),
    )


async def close_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    global current_question, current_question_respondents

    if current_question:
        closed = current_question
        current_question = None
        current_question_respondents = set()
        await update.message.reply_text(
            f"🔒 Вопрос *{closed}* закрыт\n"
            f"Новые ответы не принимаются",
            parse_mode='Markdown'
        )
        correct_text = get_correct_answer_text(closed)
        for user_id in participants.keys():
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ <b>Правильный ответ на {closed}:</b>\n\n<b>{correct_text}</b>",
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"Failed to send answer to {user_id}: {e}")
    else:
        await update.message.reply_text("⚠️ Нет активного вопроса")


async def show_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    args = update.message.text.split()
    if len(args) < 2:
        await update.message.reply_text("Используйте: /show_answer q1")
        return

    q_id = args[1]
    if q_id not in QUESTIONS:
        await update.message.reply_text("⚠️ Вопрос не найден")
        return

    correct_text = get_correct_answer_text(q_id)

    sent = 0
    for user_id in participants.keys():
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ *Правильный ответ на {q_id}:*\n\n*{correct_text}*",
                parse_mode='Markdown'
            )
            sent += 1
        except:
            pass

    await update.message.reply_text(f"📢 Ответ показан {sent} участникам: {correct_text}")



async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if not participants:
        await update.message.reply_text("📭 Пока нет участников")
        return

    results = build_leaderboard(participants, answers, QUESTIONS)

    medals = ["🥇", "🥈", "🥉"]
    leaderboard = "🏆 <b>Лидерборд</b>:\n\n"

    for i, (name, correct, total) in enumerate(results):
        medal = medals[i] if i < 3 else f"{i + 1}."
        score = f"{correct}/{total}" if total > 0 else "—"
        leaderboard += f"{medal} {name}: {score}\n"

    await update.message.reply_text(leaderboard, parse_mode='HTML')

    for user_id in participants.keys():
        try:
            await context.bot.send_message(chat_id=user_id, text=leaderboard, parse_mode='HTML')
        except Exception as e:
            print(f"Failed to send leaderboard to {user_id}: {e}")


# async def show_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     if not is_admin(update.effective_user.id):
#         return

#     if not participants:
#         await update.message.reply_text("📭 Пока нет участников")
#         return

#     text = f"👥 **Участники** ({len(participants)}):\n\n"
#     for user_id, info in participants.items():
#         correct, total = calculate_score(user_id)
#         text += f"• {info['name']} — {correct}/{total} ✅\n"

#     await update.message.reply_text(text, parse_mode='Markdown')


async def export_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if not answers:
        await update.message.reply_text("📭 Нет данных для экспорта")
        return

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Участник', 'Username', 'Вопрос', 'Ответ', 'Правильно?', 'Баллы'])

    user_scores = {}

    for user_id, user_answers in answers.items():
        info = participants.get(user_id, {})
        name = info.get("name", "Unknown")
        username = info.get("username", "")

        correct, total = calculate_score(user_id, answers, QUESTIONS)
        
        user_scores[user_id] = {"name": name, "username": username, "score": correct}

        for qid, ans in user_answers.items():
            correct_val = QUESTIONS.get(qid, {}).get("correct")
            is_correct = "✓" if ans == correct_val else "✗"
            writer.writerow([name, username, qid, ans, is_correct, ""])

    writer.writerow([])
    writer.writerow(['=== ИТОГИ ==='])
    for user_id, info in user_scores.items():
        writer.writerow([info["name"], info["username"], "ИТОГО", "", "", info["score"]])

    output.seek(0)
    filename = f"quiz_results_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

    await update.message.reply_document(
        document=output.getvalue().encode('utf-8-sig'),
        filename=filename,
        caption=f"📊 Результаты экспортированы\n📁 {filename}"
    )


async def reset_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    keyboard = [
        [InlineKeyboardButton("✅ Да, сбросить", callback_data="reset_confirm")],
        [InlineKeyboardButton("❌ Отмена", callback_data="reset_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚠️ **Внимание!**\n\n"
        "Это удалит все ответы участников.\n"
        "Продолжить?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔ Нет доступа")
        return

    if query.data == "reset_confirm":
        global answers, participants, current_question, current_question_respondents, quiz_active
        answers = {}
        participants = {}
        current_question = None
        current_question_respondents = set()
        quiz_active = False
        await query.edit_message_text("🗑️ Все данные сброшены")
    else:
        await query.edit_message_text("❌ Отменено")

# =============================================================================
# MAIN
# =============================================================================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CommandHandler("start_quiz", start_quiz))
    app.add_handler(CommandHandler("stop_quiz", stop_quiz))
    app.add_handler(CommandHandler("close", close_question))
    app.add_handler(CommandHandler("show_answer", show_answer))

    app.add_handler(CommandHandler("leaderboard", show_leaderboard))
    # app.add_handler(CommandHandler("who", show_participants))
    app.add_handler(CommandHandler("export", export_stats))
    app.add_handler(CommandHandler("reset", reset_quiz))

    for q_id in QUESTIONS:
        app.add_handler(CommandHandler(q_id, send_question))

    app.add_handler(CallbackQueryHandler(reset_callback, pattern="^reset_"))
    app.add_handler(CallbackQueryHandler(handle_answer))

    print("🤖 Bot is running...")
    print(f"👑 Admin ID: {ADMIN_ID}")
    print(f"📚 Questions: {len(QUESTIONS)}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

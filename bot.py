import os
import logging
import asyncio
import threading
import time
from datetime import datetime, timedelta
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from storage import Storage

# ========== НАСТРОЙКИ (из переменных окружения) ==========
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PROVOD_API_KEY = os.environ.get("PROVOD_API_KEY")

if not TELEGRAM_TOKEN or not PROVOD_API_KEY:
    raise ValueError("❌ Ошибка: TELEGRAM_TOKEN или PROVOD_API_KEY не найдены!")

# ========== ПОДКЛЮЧЕНИЕ К PROVOD.AI ==========
client = OpenAI(
    api_key=PROVOD_API_KEY,
    base_url="https://api.provod.ai/v1",
)

# ========== ХРАНИЛИЩА ==========
weight_storage = Storage("weight_data.json", {"history": [], "goal": 85, "start_weight": 75})
task_storage = Storage("tasks_data.json", {"tasks": []})
workout_storage = Storage("workouts_data.json", {"history": [], "templates": {
    "monday": ["Приседания 4×12", "Жим 4×10"],
    "wednesday": ["Становая 4×8", "Подтягивания 4×10"],
    "friday": ["Жим ногами 4×12", "Разгибания 4×15"]
}})
food_storage = Storage("food_data.json", {
    "training": [
        {"time": "08:00", "meal": "Завтрак", "foods": "омлет 3 яйца, овсянка 60г"},
        {"time": "11:00", "meal": "Перекус", "foods": "куриная грудка 120г, гречка 60г"},
        {"time": "17:00", "meal": "Предтреник", "foods": "рис 80г, индейка 150г"},
        {"time": "21:00", "meal": "Ужин", "foods": "горбуша 200г, салат"}
    ],
    "rest": [
        {"time": "08:00", "meal": "Завтрак", "foods": "омлет 3 яйца, овсянка 40г"},
        {"time": "12:00", "meal": "Обед", "foods": "говядина 150г, гречка 50г"},
        {"time": "19:00", "meal": "Ужин", "foods": "куриное филе 200г, овощи"}
    ]
})

active_chats = []

# ========== НАСТРОЙКИ AI ==========
SYSTEM_PROMPT = """Ты — фитнес-помощник. Помогаешь с питанием, тренировками, задачами и весом.
Отвечай кратко, по делу, используй эмодзи."""

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== ФУНКЦИЯ ДЛЯ AI ==========
def get_ai_response(user_message):
    try:
        response = client.chat.completions.create(
            model="zai/glm-5.3-flash",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0.6,
            max_tokens=1000,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка AI: {e}")
        return "⚠️ Ошибка подключения к AI. Попробуй позже."

# ========== КОМАНДЫ БОТА ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in active_chats:
        active_chats.append(chat_id)
    
    keyboard = [
        [InlineKeyboardButton("📅 Сегодня", callback_data="today")],
        [InlineKeyboardButton("🍽️ Еда", callback_data="food"), InlineKeyboardButton("🏋️ Тренировка", callback_data="workout")],
        [InlineKeyboardButton("💼 Задачи", callback_data="tasks"), InlineKeyboardButton("⚖️ Вес", callback_data="weight")],
        [InlineKeyboardButton("📊 Прогресс", callback_data="progress"), InlineKeyboardButton("📚 Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 Привет! Я твой AI-помощник по фитнесу и работе.\n\n"
        "📌 Нажми на кнопку или напиши команду:",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📚 ДОСТУПНЫЕ КОМАНДЫ:

🍽️ ПИТАНИЕ:
  «еда показать» — текущий рацион
  «еда добавить 16:00 перекус творог 200г»
  «еда удалить 21:00»

🏋️ ТРЕНИРОВКИ:
  «тренировка план» — план на сегодня
  «тренировка прогресс жим» — прогресс
  «тренировка логируй жим 60кг 4х10»

💼 РАБОТА:
  «добавить задачу сделать отчёт»
  «мои задачи» — список задач
  «завершить задачу 1» — завершить по номеру

⚖️ ВЕС:
  «записать вес 76.5 кг»
  «прогресс веса» — шкала прогресса
  «установить цель 85 кг»

📅 ОБЩЕЕ:
  «сегодня» — полный план дня
  «помощь» — это сообщение
    """
    await update.message.reply_text(help_text)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    commands = {
        "today": "сегодня",
        "food": "еда показать",
        "workout": "тренировка план",
        "tasks": "мои задачи",
        "weight": "прогресс веса",
        "progress": "полный прогресс",
        "help": "помощь"
    }
    
    command = commands.get(query.data, "помощь")
    response = get_ai_response(command)
    await query.edit_message_text(text=response)

# ========== ОБРАБОТКА ВЕСА ==========
async def handle_weight_command(text, update):
    response = ""
    
    if "записать вес" in text:
        try:
            weight = float(text.split("кг")[0].split()[-1])
            weight_storage.append_to_list("history", {"weight": weight, "date": str(datetime.now().date())})
            response = f"✅ Вес {weight} кг записан!"
        except:
            response = "❌ Неверный формат. Используй: записать вес 76.5 кг"
    
    elif "прогресс веса" in text:
        history = weight_storage.get("history", [])
        if not history:
            response = "📭 Нет данных о весе. Запиши первый вес: записать вес 75 кг"
        else:
            current = history[-1]["weight"]
            goal = weight_storage.get("goal", 85)
            start = weight_storage.get("start_weight", 75)
            progress = round((current - start) / (goal - start) * 100, 1)
            bar = "█" * int(progress // 10) + "░" * (10 - int(progress // 10))
            response = f"⚖️ Прогресс веса:\nТекущий: {current} кг\nЦель: {goal} кг\n[{bar}] {progress}%\n"
            if current >= goal:
                response += "🎉 Поздравляю! Ты достиг цели!"
            else:
                response += f"📉 Осталось: {round(goal - current, 1)} кг"
    
    elif "установить цель" in text:
        try:
            goal = float(text.split("кг")[0].split()[-1])
            weight_storage.set("goal", goal)
            response = f"🎯 Новая цель: {goal} кг"
        except:
            response = "❌ Неверный формат. Используй: установить цель 85 кг"
    
    else:
        response = "❌ Неизвестная команда по весу."
    
    await update.message.reply_text(response)

# ========== ОБРАБОТКА ЗАДАЧ ==========
async def handle_task_command(text, update):
    response = ""
    
    if "добавить задачу" in text:
        task_text = text.replace("добавить задачу", "").strip()
        if task_text:
            task_storage.append_to_list("tasks", {"text": task_text, "completed": False})
            response = f"✅ Задача добавлена: {task_text}"
        else:
            response = "❌ Укажи задачу."
    
    elif "мои задачи" in text:
        tasks = task_storage.get("tasks", [])
        active = [t for t in tasks if not t["completed"]]
        if not active:
            response = "🎉 Все задачи выполнены!"
        else:
            response = "📋 Твои задачи:\n"
            for i, task in enumerate(active, 1):
                response += f"{i}. {task['text']}\n"
    
    elif "завершить задачу" in text:
        try:
            num = int(text.split()[-1]) - 1
            tasks = task_storage.get("tasks", [])
            active = [t for t in tasks if not t["completed"]]
            if 0 <= num < len(active):
                task = active[num]
                task["completed"] = True
                task_storage.save()
                response = f"✅ Задача завершена: {task['text']}"
            else:
                response = "❌ Неверный номер задачи"
        except:
            response = "❌ Укажи номер задачи. Например: завершить задачу 1"
    
    await update.message.reply_text(response)

# ========== ОБРАБОТКА ПИТАНИЯ ==========
async def handle_food_command(text, update):
    response = ""
    
    if "еда показать" in text:
        today = datetime.now().strftime("%A").lower()
        day_type = "training" if today in ["monday", "wednesday", "friday"] else "rest"
        meals = food_storage.get(day_type, [])
        if not meals:
            response = "📭 Нет запланированных приёмов пищи"
        else:
            response = f"🍽️ РАЦИОН НА СЕГОДНЯ ({day_type}):\n\n"
            for meal in meals:
                response += f"⏰ {meal['time']} — {meal['meal']}\n   📦 {meal['foods']}\n\n"
    
    elif "еда добавить" in text:
        try:
            parts = text.replace("еда добавить", "").strip().split(" ", 2)
            time = parts[0]
            meal_name = parts[1]
            foods = parts[2]
            today = datetime.now().strftime("%A").lower()
            day_type = "training" if today in ["monday", "wednesday", "friday"] else "rest"
            food_storage.append_to_list(day_type, {"time": time, "meal": meal_name, "foods": foods})
            response = f"✅ Добавлено: {time} — {meal_name}"
        except:
            response = "❌ Неверный формат. Используй: еда добавить 16:00 перекус творог 200г"
    
    elif "еда удалить" in text:
        try:
            time = text.replace("еда удалить", "").strip()
            today = datetime.now().strftime("%A").lower()
            day_type = "training" if today in ["monday", "wednesday", "friday"] else "rest"
            meals = food_storage.get(day_type, [])
            new_meals = [m for m in meals if m["time"] != time]
            if len(new_meals) < len(meals):
                food_storage.set(day_type, new_meals)
                response = f"✅ Удалён приём в {time}"
            else:
                response = f"❌ Приём в {time} не найден"
        except:
            response = "❌ Укажи время. Например: еда удалить 21:00"
    
    else:
        response = "❌ Неизвестная команда по питанию."
    
    await update.message.reply_text(response)

# ========== ОБРАБОТКА ТРЕНИРОВОК ==========
async def handle_workout_command(text, update):
    response = ""
    
    if "тренировка план" in text:
        today = datetime.now().strftime("%A").lower()
        templates = workout_storage.get("templates", {})
        plan = templates.get(today, ["Нет тренировки на сегодня"])
        response = f"🏋️ ПЛАН ТРЕНИРОВКИ НА СЕГОДНЯ:\n\n"
        for i, ex in enumerate(plan, 1):
            response += f"{i}. {ex}\n"
    
    elif "тренировка логируй" in text:
        try:
            parts = text.replace("тренировка логируй", "").strip().split()
            exercise = parts[0]
            weight = parts[1] if len(parts) > 1 else "0"
            reps = parts[2] if len(parts) > 2 else "0"
            workout_storage.append_to_list("history", {
                "exercise": exercise,
                "weight": weight,
                "reps": reps,
                "date": str(datetime.now().date())
            })
            response = f"✅ Записано: {exercise} {weight}кг × {reps} повторений"
        except:
            response = "❌ Неверный формат. Используй: тренировка логируй жим 60кг 4х10"
    
    elif "тренировка прогресс" in text:
        try:
            exercise = text.replace("тренировка прогресс", "").strip()
            history = workout_storage.get("history", [])
            logs = [h for h in history if h["exercise"] == exercise]
            if not logs:
                response = f"📭 Нет данных по упражнению {exercise}"
            else:
                response = f"📈 ПРОГРЕСС: {exercise}\n\n"
                for log in logs[-5:]:
                    response += f"{log['date']}: {log['weight']}кг × {log['reps']} повторений\n"
        except:
            response = "❌ Укажи упражнение. Например: тренировка прогресс жим"
    
    else:
        response = "❌ Неизвестная команда по тренировкам."
    
    await update.message.reply_text(response)

# ========== ГЛАВНЫЙ ОБРАБОТЧИК ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    
    # ВЕС
    if any(word in text for word in ["вес", "кг", "цель"]) and ("записать" in text or "прогресс" in text or "установить" in text):
        await handle_weight_command(text, update)
        return
    
    # ЗАДАЧИ
    if any(word in text for word in ["задач", "задание"]):
        await handle_task_command(text, update)
        return
    
    # ЕДА
    if "еда" in text:
        await handle_food_command(text, update)
        return
    
    # ТРЕНИРОВКИ
    if "трен" in text or "упражн" in text:
        await handle_workout_command(text, update)
        return
    
    # ЕСЛИ НИЧЕГО НЕ ПОДОШЛО — ОТПРАВЛЯЕМ В AI
    await context.bot.send_chat_action(update.effective_chat.id, action="typing")
    response = get_ai_response(text)
    await update.message.reply_text(response)

# ========== ЕЖЕДНЕВНЫЙ ОТЧЁТ ==========
async def send_daily_report():
    for chat_id in active_chats:
        try:
            today = datetime.now().date()
            history = weight_storage.get("history", [])
            
            report = f"📋 ДОБРОЕ УТРО! ОТЧЁТ ЗА {today}\n\n"
            
            if history:
                last = history[-1]
                report += f"⚖️ Вес: {last['weight']} кг\n"
                
                week_ago = today - timedelta(days=7)
                week_data = [h for h in history if datetime.strptime(h['date'], '%Y-%m-%d').date() >= week_ago]
                if len(week_data) >= 2:
                    change = week_data[-1]['weight'] - week_data[0]['weight']
                    report += f"📉 Изменение за неделю: {'+' if change > 0 else ''}{change:.1f} кг\n"
            
            tasks = task_storage.get("tasks", [])
            active_tasks = [t for t in tasks if not t["completed"]]
            done_tasks = [t for t in tasks if t["completed"]]
            report += f"\n💼 Задачи: {len(active_tasks)} активных, {len(done_tasks)} выполненных\n"
            
            report += f"\n📌 Напиши «сегодня» для полного плана дня!"
            
            import telegram
            bot = telegram.Bot(token=TELEGRAM_TOKEN)
            await bot.send_message(chat_id, report)
        except Exception as e:
            logger.error(f"Ошибка отправки отчёта: {e}")

# ========== ПЛАНИРОВЩИК ==========
def run_scheduler():
    import schedule
    while True:
        schedule.run_pending()
        time.sleep(60)

# ========== ЗАПУСК ==========
def main():
    # Создаём приложение
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Добавляем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем планировщик
    import schedule
    schedule.every().day.at("09:00").do(lambda: asyncio.run(send_daily_report()))
    
    thread = threading.Thread(target=run_scheduler, daemon=True)
    thread.start()
    
    print("✅ Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()

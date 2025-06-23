import discord
from discord.ext import commands
import json
import os
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import asyncio

scheduler = BackgroundScheduler()
scheduler.start()

async def send_reminder(user_id, habit):
    user = await bot.fetch_user(int(user_id))
    if user:
        try:
            await user.send(f"⏰ Reminder: Don't forget to **{habit['habit']}** today! Reply with `!markdone {habit['habit']}` to keep your streak alive 💪")
        except Exception as e:
            print(f"⚠️ Could not send reminder to {user.name}: {e}")

#crud test to understand better db structure
FILENAME = "data.json"

# Load or create JSON file
def load_data():
    if not os.path.exists(FILENAME):
        return {}
    with open(FILENAME, "r") as f:
        return json.load(f)

def save_data(data):
    with open(FILENAME, "w") as f:
        json.dump(data, f, indent=4)

# Create a new habit
def create_habit(user_id, habit=None, hour=None, minute=None):
    data = load_data()
    user_id = str(user_id)

    if habit is None:
        habit = input("Enter habit name: ")
    if hour is None:
        hour = int(input("Hour (0–23): "))
    if minute is None:
        minute = int(input("Minute (0–59): "))

    # Normalize habit name to check for duplicates
    if user_id in data:
        for h in data[user_id]:
            if h["habit"].lower() == habit.lower():
                print("⚠️ Habit already exists!")
                return False
    else:
        data[user_id] = []

    new_habit = {
        "habit": habit,
        "hour": hour,
        "minute": minute,
        "streak": 0,
        "last_done": None,
    }

    data[user_id].append(new_habit)
    save_data(data)
    print("✅ Habit added!")
    return True

def list_habits(user_id):
    data = load_data()
    user_id = str(user_id)
    if user_id not in data or len(data[user_id]) == 0:
        print("No habits found.")
        return

    for i, h in enumerate(data[user_id]):
        print(f"{i+1}. {h['habit']} at {h['hour']:02d}:{h['minute']:02d} (Streak: {h['streak']})")

def mark_done(user_id, habit_name=None):
    data = load_data()
    user_id = str(user_id)
    today = datetime.utcnow().date()

    if user_id not in data or len(data[user_id]) == 0:
        return "No habits to mark."

    for h in data[user_id]:
        if h["habit"].lower() == habit_name.lower():
            last_str = h.get("last_done")
            last_done = datetime.strptime(last_str, "%Y-%m-%d").date() if last_str else None

            if last_done == today:
                return f"⚠️ You've already marked **{habit_name}** as done today."


            scheduled_time = datetime.combine(today, datetime.min.time()) + timedelta(hours=h["hour"], minutes=h["minute"])
            deadline = scheduled_time + timedelta(hours=9)
            now = datetime.utcnow()

            if now > deadline:
                h["streak"] = 0  # se pasó del plazo
                response = f"⏳ You missed the deadline. Streak for **{habit_name}** has been reset."
            else:
                h["streak"] += 1
                response = f"🎉 You did it! Streak for **{habit_name}** is now {h['streak']} days!"

            h["last_done"] = today.isoformat()
            save_data(data)
            return response

    return f"❌ Habit **{habit_name}** not found."


def delete_habit(user_id, habit_name):
    data = load_data()
    user_id = str(user_id)
    if user_id not in data or len(data[user_id]) == 0:
        print("No habits to delete.")
        return
    updated = [
        h for h in data[user_id]
        if h['habit'].lower() != habit_name.lower()
    ]

    if len(updated) == len(data[user_id]):
        return f"❌ Habit **{habit_name}** not found."

    data[user_id] = updated
    save_data(data)
    return f"🗑️ Habit **{habit_name}** has been deleted."

# Ask user who they are (simulate Discord user ID or name)
def get_user_id():
    user = input("Enter your user ID or name: ").strip().lower()
    if not user:
        print("⚠️ Please enter a valid ID.")
        return get_user_id()
    return user

def reset_streak(user_id, habit_name):
    data = load_data()
    user_id = str(user_id)



intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")

    data = load_data()
    for user_id, habits in data.items():
        for habit in habits:
            job_id = f"{user_id}_{habit['habit'].lower()}"
            hour = habit.get("hour", 10)
            minute = habit.get("minute", 0)

            # Schedule the reminder
            scheduler.add_job(
                lambda uid=user_id, h=habit: asyncio.run_coroutine_threadsafe(
                    send_reminder(uid, h),
                    bot.loop
                ),
                trigger="cron",
                hour=hour,
                minute=minute,
                id=job_id,
                replace_existing=True
            )
    print("🕒 All reminders scheduled.")


@bot.command()
async def hello(ctx):
    await ctx.send(f"👋 Hello, {ctx.author.name}! I'm alive and listening.")

@bot.command(name="get_help")
async def custom_help(ctx):
    help_msg = (
        "🧠 **HabitPal Bot Commands**\n"
        "➕ `!addhabit <name> <hour> <minute>` – Add a new habit\n"
        "✅ `!done <name>` – Mark habit as done\n"
        "📋 `!listhabits` – Show your current habits\n"
        "🗑️ `!deletehabit <name>` – Delete a habit\n"
        "🏆 `!stats` – See your progress (coming soon!)\n"
        "🎖️ `!badges` – Earn badges for milestones (coming soon!)"
    )
    await ctx.send(help_msg)


@bot.command()
async def addhabit(ctx, habit: str, hour: int, minute: int):
    user_id = str(ctx.author.id)
    created = create_habit(user_id, habit, hour, minute)

    if created:
        await ctx.send(f"✅ Habit **{habit}** has been added and will be tracked daily at {hour:02d}:{minute:02d}.")
        scheduler.add_job(
            lambda uid=user_id, h={"habit": habit, "hour": hour, "minute": minute}: asyncio.run_coroutine_threadsafe(
                send_reminder(uid, h),
                bot.loop
            ),
            trigger="cron",
            hour=hour,
            minute=minute,
            id=f"{user_id}_{habit.lower()}",
            replace_existing=True
        )

    else:
        await ctx.send(f"⚠️ You already have a habit named **{habit}**.")

@bot.command()
async def listhabits(ctx):
    user_id = str(ctx.author.id)
    data = load_data()

    if user_id not in data or len(data[user_id]) == 0:
        await ctx.send("📭 You don't have any habits yet. Use `!addhabit` to create one.")
        return

    message = f"📋 **Your Habits, {ctx.author.name}**:\n"
    for habit in data[user_id]:
        name = habit['habit']
        hour = habit.get('hour', 0)
        minute = habit.get('minute', 0)
        streak = habit.get('streak', 0)
        message += f"• **{name}** at {hour:02d}:{minute:02d} ⏰ (Streak: {streak} 🔥)\n"

    await ctx.send(message)

@bot.command()
async def markdone(ctx, *, habit:str):
    user_id = str(ctx.author.id)
    await ctx.send(mark_done(user_id, habit))

@bot.command()
async def deletehabit(ctx, *, habit:str):
    user_id = str(ctx.author.id)
    await ctx.send(delete_habit(user_id, habit))

bot.run("your token here")

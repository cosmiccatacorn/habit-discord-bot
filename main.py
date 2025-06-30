import discord
from discord.ext import commands
import json
import os
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta, timezone
import asyncio
import pytz

# --- Timezone Conversion Functions ---
def local_to_utc(hour, minute, timezone_str):
    try:
        local = pytz.timezone(timezone_str)
    except pytz.UnknownTimeZoneError:
        return None, None
    now = datetime.now()
    local_time = local.localize(datetime(now.year, now.month, now.day, hour, minute))
    utc_time = local_time.astimezone(pytz.utc)
    return utc_time.hour, utc_time.minute

def utc_to_local(hour, minute, timezone_str):
    utc = pytz.utc
    local = pytz.timezone(timezone_str)
    now = datetime.now(timezone.utc)
    utc_time = utc.localize(datetime(now.year, now.month, now.day, hour, minute))
    local_time = utc_time.astimezone(local)
    return local_time.hour, local_time.minute

# --- JSON Data Management ---
FILENAME = "data.json"

def load_data():
    if not os.path.exists(FILENAME):
        return {}
    with open(FILENAME, "r") as f:
        return json.load(f)

def save_data(data):
    with open(FILENAME, "w") as f:
        json.dump(data, f, indent=4)

# --- Reminder Scheduler ---
scheduler = BackgroundScheduler()

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")
    data = load_data()
    for user_id, habits in data.items():
        if user_id == "user_meta":
            continue
        for habit in habits:
            schedule_reminder(user_id, habit)

    if not scheduler.running:
        scheduler.start()

    print("🕒 All reminders scheduled.")

# --- Scheduling Function ---
def schedule_reminder(user_id, habit):
    job_id = f"{user_id}_{habit['habit'].lower()}"

    async def job():
        await send_reminder(user_id, habit)

    def wrapper():
        future = asyncio.run_coroutine_threadsafe(job(), bot.loop)
        try:
            future.result()
        except Exception as e:
            print(f"⚠️ Error sending reminder: {e}")

    print(f"📅 Scheduling {habit['habit']} for {habit['hour']:02}:{habit['minute']:02} UTC")
    scheduler.add_job(
        wrapper,
        trigger="cron",
        hour=habit["hour"],
        minute=habit["minute"],
        id=job_id,
        replace_existing=True
    )


async def send_reminder(user_id, habit):
    print(f"🔔 Sending reminder for {habit['habit']} to user {user_id}")
    user = await bot.fetch_user(int(user_id))
    if user:
        try:
            await user.send(f"⏰ Reminder: Don't forget to **{habit['habit']}** today!")
            print(f"✅ Reminder sent to {user.name}")
        except Exception as e:
            print(f"⚠️ Could not send reminder to {user_id}: {e}")

# --- Habit Marking ---
def mark_done(user_id, habit_name):
    data = load_data()
    user_id = str(user_id)
    today = datetime.now(timezone.utc).date()

    if user_id not in data:
        return "❌ No habits found."

    for h in data[user_id]:
        if h["habit"].lower() == habit_name.lower():
            last = h.get("last_done")
            last_done = datetime.strptime(last, "%Y-%m-%d").date() if last else None

            if last_done == today:
                return "⚠️ Already marked as done today."

            scheduled_time = datetime.combine(today, datetime.min.time()) + timedelta(hours=h["hour"], minutes=h["minute"])
            deadline = scheduled_time + timedelta(hours=9)
            now = datetime.now(timezone.utc)

            if now > deadline:
                h["streak"] = 0
                result = f"⏳ Too late! Streak for **{habit_name}** reset."
            else:
                h["streak"] += 1
                result = f"🎉 Streak updated to {h['streak']} for **{habit_name}**!"

            h["last_done"] = today.isoformat()
            save_data(data)
            return result

    return f"❌ Habit **{habit_name}** not found."

# --- Bot Commands ---
@bot.command()
async def settimezone(ctx, tz: str):
    try:
        pytz.timezone(tz)
    except pytz.UnknownTimeZoneError:
        await ctx.send("❌ Unknown timezone. Example: `America/Bogota`")
        return
    data = load_data()
    user_id = str(ctx.author.id)
    if "user_meta" not in data:
        data["user_meta"] = {}
    data["user_meta"][user_id] = {"timezone": tz}
    save_data(data)
    await ctx.send(f"✅ Timezone set to `{tz}`")

@bot.command()
async def listtimezones(ctx):
    sample = [z for z in pytz.all_timezones if "America" in z][:10]
    msg = "**Sample timezones:**\n" + "\n".join(f"• `{z}`" for z in sample)
    await ctx.send(msg + "\nSee more at: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones")

@bot.command()
async def addhabit(ctx, habit: str, hour: int, minute: int):
    user_id = str(ctx.author.id)
    data = load_data()
    if "user_meta" not in data or user_id not in data["user_meta"]:
        await ctx.send("❗ Please set your timezone first using `!settimezone Your/Zone`")
        return

    tz = data["user_meta"][user_id]["timezone"]
    utc_hour, utc_minute = local_to_utc(hour, minute, tz)
    if user_id not in data:
        data[user_id] = []
    if any(h["habit"].lower() == habit.lower() for h in data[user_id]):
        await ctx.send("⚠️ That habit already exists.")
        return

    new_habit = {
        "habit": habit,
        "hour": utc_hour,
        "minute": utc_minute,
        "streak": 0,
        "last_done": None
    }
    data[user_id].append(new_habit)
    save_data(data)
    schedule_reminder(user_id, new_habit)
    await ctx.send(f"✅ Habit `{habit}` scheduled at {hour:02}:{minute:02} {tz} ({utc_hour:02}:{utc_minute:02} UTC)")

@bot.command()
async def listhabits(ctx):
    user_id = str(ctx.author.id)
    data = load_data()
    if user_id not in data or len(data[user_id]) == 0:
        await ctx.send("📭 No habits found.")
        return

    tz = data.get("user_meta", {}).get(user_id, {}).get("timezone", "UTC")
    message = f"📋 **Your Habits:**\n"
    for habit in data[user_id]:
        name = habit["habit"]
        streak = habit["streak"]
        local_hour, local_minute = utc_to_local(habit["hour"], habit["minute"], tz)
        message += f"• **{name}** – ⏰ {local_hour:02}:{local_minute:02} {tz} – 🔥 Streak: {streak}\n"
    await ctx.send(message)

@bot.command()
async def markdone(ctx, *, habit: str):
    user_id = str(ctx.author.id)
    result = mark_done(user_id, habit)
    await ctx.send(result)

@bot.command()
async def deletehabit(ctx, *, habit: str):
    user_id = str(ctx.author.id)
    data = load_data()
    if user_id not in data:
        await ctx.send("❌ No habits to delete.")
        return

    original = len(data[user_id])
    data[user_id] = [h for h in data[user_id] if h["habit"].lower() != habit.lower()]
    if len(data[user_id]) == original:
        await ctx.send(f"❌ Habit `{habit}` not found.")
    else:
        save_data(data)
        await ctx.send(f"🗑️ Habit `{habit}` deleted.")

bot.run(os.getenv("DISCORD_TOKEN"))

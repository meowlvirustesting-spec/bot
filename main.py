import os
import random
import re
import asyncio
import threading
from flask import Flask
import discord
from discord.ext import commands

# --- CONFIGURATION ---
ALLOWED_ROLE_NAME = "Code Manager"  # Role allowed to create codes and manage blacklist

# Custom riddle bank: (Question, Answer)
RIDDLE_BANK = [
    ("What month did the first fuse machine release?", "AUGUST"),
    ("What is the rarest DLC brainrot?", "POLAROIDINI"),
    ("What was Cerberus's old name?", "HELLHOUND"),
    ("What is the unused mutation called?", "DISCO"),
    ("What is Sammy's favorite color?", "BLUE"),
    ("What is bradar's favorite brainrot?", "SPINNYHAMMY"),
    ("What is Toothpik's worst missed log?", "CELESTIALPEGASUS"),
    ("What was the most recent brainrot added to the game?", "LAFUSEMACHINE"),
    ("The first limited quantity brainrot was called?", "LAEXTINCTGRANDE"),
]

# Track last used riddle to avoid repeats
last_riddle = None

# Set of blacklisted user IDs
blacklisted_users = set()

# Common word list to match against when no spaces are provided
COMMON_WORDS = {
    "banana", "good", "apple", "super", "cool", "fire", "code", "epic", "legend",
    "master", "pro", "ultra", "mega", "hyper", "shadow", "cyber", "gamer", "hero",
    "star", "dragon", "viper", "titan", "ninja", "boss", "king", "queen", "lord"
}

# --- 1. KEEP-ALIVE WEB SERVER ---
app = Flask("")


@app.route("/")
def home():
  return "Bot is online!"


def run_server():
  port = int(os.environ.get("PORT", 8080))
  app.run(host="0.0.0.0", port=port)


def keep_alive():
  t = threading.Thread(target=run_server)
  t.daemon = True
  t.start()


# --- 2. BOT CONFIGURATION ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Required to grant roles to users

bot = commands.Bot(command_prefix="!", intents=intents)

# Active secret codes/riddles per channel:
# {channel_id: {"code": "secret code", "ready": False, "role_id": Optional[int]}}
active_codes = {}


@bot.event
async def on_ready():
  print(f"Logged in as {bot.user}!")


# --- Blacklist Check Decorator ---
def is_not_blacklisted():

  async def predicate(ctx):
    return ctx.author.id not in blacklisted_users

  return commands.check(predicate)


# --- 3. HELPER FUNCTION TO SMART SPLIT WORDS & NUMBERS ---
def split_phrase(text: str) -> list[str]:
  if " " in text:
    return text.split()

  raw_blocks = re.findall(r"[a-zA-Z]+|\d+|[^\w\s]+", text)
  sections = []

  for block in raw_blocks:
    if block.isalpha():
      remaining = block.lower()
      sub_sections = []

      while remaining:
        matched = False
        for word in sorted(COMMON_WORDS, key=len, reverse=True):
          if remaining.startswith(word):
            sub_sections.append(remaining[: len(word)])
            remaining = remaining[len(word) :]
            matched = True
            break

        if not matched:
          take = min(4, len(remaining))
          sub_sections.append(remaining[:take])
          remaining = remaining[take:]

      sections.extend(sub_sections)
    else:
      sections.append(block)

  return sections


# --- 4. HELPER TASK TO ANIMATE EMBED IN A SPECIFIC CHANNEL ---
async def process_code_creation(
    target_channel: discord.TextChannel,
    clean_code: str,
    sections: list[str],
    creator: discord.User | discord.Member,
    reward_role: discord.Role | None = None,
):
  active_codes[target_channel.id] = {
      "code": clean_code.lower(),
      "ready": False,
      "role_id": reward_role.id if reward_role else None,
  }

  embed = discord.Embed(
      title="Creating Code...",
      description=f"**Created by:** {creator.mention}\n\n*Generating Code...*",
      color=discord.Color.blue(),
  )
  embed.set_thumbnail(url=creator.display_avatar.url)
  message = await target_channel.send(embed=embed)

  displayed_text = ""

  async with target_channel.typing():
    for section in sections:
      await asyncio.sleep(2.5)
      displayed_text += section + " "

      embed.description = (
          f"**Created by:** {creator.mention}\n\n"
          f"**USE CODE:** {displayed_text.strip()}\n\n"
          f"*Type the full code in chat to solve!*"
      )
      await message.edit(embed=embed)

  active_codes[target_channel.id]["ready"] = True

  embed.title = "Role Code Created!" if reward_role else "Code Created!"
  reward_text = f"\n**Reward:** {reward_role.mention}" if reward_role else ""
  embed.description = (
      f"**Created by:** {creator.mention}\n\n"
      f"**USE CODE:** {clean_code}{reward_text}\n\n"
      f"Type the full code in chat to claim!"
  )
  embed.color = discord.Color.green()
  await message.edit(embed=embed)


# --- 5. HELPER TASK FOR RIDDLE CREATION ---
async def process_riddle_creation(
    target_channel: discord.TextChannel,
    question: str,
    base_answer: str,
    creator: discord.User | discord.Member,
):
  use_numbers = random.choice([True, False])

  if use_numbers:
    random_num = random.randint(1000, 9999)
    full_code = f"{base_answer}{random_num}"
    num_str = str(random_num)

    active_codes[target_channel.id] = {
        "code": full_code.lower(),
        "ready": False,
        "role_id": None,
    }

    embed = discord.Embed(
        title="🧩 Riddle Challenge!",
        description=(
            f"**Created by:** {creator.mention}\n\n**Question:** {question}"
        ),
        color=discord.Color.gold(),
    )
    embed.set_thumbnail(url=creator.display_avatar.url)
    message = await target_channel.send(embed=embed)

    await asyncio.sleep(3)

    active_codes[target_channel.id]["ready"] = True

    embed.description = (
        f"**Created by:** {creator.mention}\n\n"
        f"**Question:** {question}\n\n"
        f"**Code Number:** `{num_str}`\n\n"
        f"*Combine the riddle answer + the number (e.g. ANSWER{num_str}) and type it in chat to solve!*"
    )
    await message.edit(embed=embed)

  else:
    active_codes[target_channel.id] = {
        "code": base_answer.lower(),
        "ready": True,
        "role_id": None,
    }

    embed = discord.Embed(
        title="🧩 Riddle Challenge!",
        description=(
            f"**Created by:** {creator.mention}\n\n"
            f"**Question:** {question}\n\n"
            f"*Type the answer to the riddle in chat to solve!*"
        ),
        color=discord.Color.gold(),
    )
    embed.set_thumbnail(url=creator.display_avatar.url)
    await target_channel.send(embed=embed)


# --- 6. STANDARD CREATECODE COMMAND ---
@bot.command()
@is_not_blacklisted()
@commands.has_role(ALLOWED_ROLE_NAME)
async def createcode(ctx, *, args: str = ""):
  try:
    await ctx.message.delete()
  except (discord.Forbidden, discord.NotFound):
    pass

  if not args.strip():
    await ctx.send(
        "❌ **Usage:** `!createcode [#channel] bananagood123`", delete_after=5
    )
    return

  target_channel = ctx.channel
  clean_code = args.strip()

  if ctx.message.channel_mentions:
    target_channel = ctx.message.channel_mentions[0]
    clean_code = re.sub(r"<#\d+>", "", clean_code).strip()

  if not clean_code:
    await ctx.send(
        "❌ **Usage:** `!createcode [#channel] bananagood123`", delete_after=5
    )
    return

  sections = split_phrase(clean_code)
  await process_code_creation(
      target_channel, clean_code, sections, ctx.author
  )


@createcode.error
async def createcode_error(ctx, error):
  try:
    await ctx.message.delete()
  except (discord.Forbidden, discord.NotFound):
    pass

  if isinstance(error, commands.MissingRole):
    await ctx.send(
        f"❌ {ctx.author.mention}, you need the **{ALLOWED_ROLE_NAME}** role to use this command!",
        delete_after=5,
    )


# --- 7. ROLE CODE COMMAND ---
@bot.command()
@is_not_blacklisted()
@commands.has_role(ALLOWED_ROLE_NAME)
async def createrolecode(ctx, role: discord.Role, *, args: str = ""):
  try:
    await ctx.message.delete()
  except (discord.Forbidden, discord.NotFound):
    pass

  if not args.strip():
    await ctx.send(
        "❌ **Usage:** `!createrolecode @Role [#channel] bananagood123`",
        delete_after=5,
    )
    return

  target_channel = ctx.channel
  clean_code = args.strip()

  if ctx.message.channel_mentions:
    target_channel = ctx.message.channel_mentions[0]
    clean_code = re.sub(r"<#\d+>", "", clean_code).strip()

  if not clean_code:
    await ctx.send(
        "❌ **Usage:** `!createrolecode @Role [#channel] bananagood123`",
        delete_after=5,
    )
    return

  sections = split_phrase(clean_code)
  await process_code_creation(
      target_channel, clean_code, sections, ctx.author, reward_role=role
  )


@createrolecode.error
async def createrolecode_error(ctx, error):
  try:
    await ctx.message.delete()
  except (discord.Forbidden, discord.NotFound):
    pass

  if isinstance(error, commands.MissingRole):
    await ctx.send(
        f"❌ {ctx.author.mention}, you need the **{ALLOWED_ROLE_NAME}** role to use this command!",
        delete_after=5,
    )


# --- 8. CREATE RIDDLE COMMAND ---
@bot.command()
@is_not_blacklisted()
@commands.has_role(ALLOWED_ROLE_NAME)
async def createriddle(ctx, channel: discord.TextChannel | None = None):
  global last_riddle

  try:
    await ctx.message.delete()
  except (discord.Forbidden, discord.NotFound):
    pass

  target_channel = channel or ctx.channel

  available_riddles = [r for r in RIDDLE_BANK if r != last_riddle]
  if not available_riddles:
    available_riddles = RIDDLE_BANK

  selected_riddle = random.choice(available_riddles)
  last_riddle = selected_riddle

  question, answer = selected_riddle

  await process_riddle_creation(target_channel, question, answer, ctx.author)


@createriddle.error
async def createriddle_error(ctx, error):
  if isinstance(error, commands.MissingRole):
    await ctx.send(
        f"❌ {ctx.author.mention}, you need the **{ALLOWED_ROLE_NAME}** role to use this command!",
        delete_after=5,
    )


# --- 9. BLACKLIST COMMANDS ---
@bot.command()
@is_not_blacklisted()
@commands.has_role(ALLOWED_ROLE_NAME)
async def blacklist(ctx, user: discord.User | discord.Member):
  try:
    await ctx.message.delete()
  except (discord.Forbidden, discord.NotFound):
    pass

  if user.id in blacklisted_users:
    await ctx.send(f"⚠️ {user.mention} is already blacklisted.", delete_after=5)
    return

  blacklisted_users.add(user.id)
  await ctx.send(
      f"🚫 {user.mention} has been blacklisted from using the bot!"
  )


@blacklist.error
async def blacklist_error(ctx, error):
  try:
    await ctx.message.delete()
  except (discord.Forbidden, discord.NotFound):
    pass

  if isinstance(error, commands.MissingRole):
    await ctx.send(
        f"❌ {ctx.author.mention}, you need the **{ALLOWED_ROLE_NAME}** role to use this command!",
        delete_after=5,
    )
  elif isinstance(error, commands.MissingRequiredArgument):
    await ctx.send("❌ **Usage:** `!blacklist @User`", delete_after=5)


@bot.command()
@is_not_blacklisted()
@commands.has_role(ALLOWED_ROLE_NAME)
async def unblacklist(ctx, user: discord.User | discord.Member):
  try:
    await ctx.message.delete()
  except (discord.Forbidden, discord.NotFound):
    pass

  if user.id not in blacklisted_users:
    await ctx.send(f"⚠️ {user.mention} is not blacklisted.", delete_after=5)
    return

  blacklisted_users.remove(user.id)
  await ctx.send(f"✅ {user.mention} has been removed from the blacklist!")


@unblacklist.error
async def unblacklist_error(ctx, error):
  try:
    await ctx.message.delete()
  except (discord.Forbidden, discord.NotFound):
    pass

  if isinstance(error, commands.MissingRole):
    await ctx.send(
        f"❌ {ctx.author.mention}, you need the **{ALLOWED_ROLE_NAME}** role to use this command!",
        delete_after=5,
    )
  elif isinstance(error, commands.MissingRequiredArgument):
    await ctx.send("❌ **Usage:** `!unblacklist @User`", delete_after=5)


# --- 10. COMMANDS LIST COMMAND ---
@bot.command()
@is_not_blacklisted()
@commands.has_role(ALLOWED_ROLE_NAME)
async def cmds(ctx):
  embed = discord.Embed(
      title="🤖 Bot Commands List",
      description=f"Commands restricted to the **{ALLOWED_ROLE_NAME}** role:",
      color=discord.Color.purple(),
  )

  embed.add_field(
      name="`!createcode [#channel] <code>`",
      value="Creates a standard code embed in a channel.\n**Examples:**\n`!createcode bananagood123`\n`!createcode #codes bananagood123`",
      inline=False,
  )

  embed.add_field(
      name="`!createrolecode <@role> [#channel] <code>`",
      value="Creates a role reward code in a channel.\n**Examples:**\n`!createrolecode @VIP bananagood123`\n`!createrolecode @VIP #codes bananagood123`",
      inline=False,
  )

  embed.add_field(
      name="`!createriddle [#channel]`",
      value="Generates a riddle challenge in a channel.",
      inline=False,
  )

  embed.add_field(
      name="`!blacklist <@user>`",
      value="Blacklists a user from interacting with the bot or completing codes.",
      inline=False,
  )

  embed.add_field(
      name="`!unblacklist <@user>`",
      value="Removes a user from the blacklist.",
      inline=False,
  )

  await ctx.send(embed=embed)


@cmds.error
async def cmds_error(ctx, error):
  if isinstance(error, commands.MissingRole):
    await ctx.send(
        f"❌ {ctx.author.mention}, you need the **{ALLOWED_ROLE_NAME}** role to use this command!"
    )


# --- 11. CHAT LISTENER FOR PHRASE VERIFICATION & ROLE GRANT ---
@bot.event
async def on_message(message):
  if message.author.bot:
    return

  # Process command invocations directly
  ctx = await bot.get_context(message)
  if ctx.valid:
    await bot.invoke(ctx)
    return

  # Ignore any messages from blacklisted users for code guessing
  if message.author.id in blacklisted_users:
    return

  channel_id = message.channel.id

  if channel_id in active_codes:
    code_data = active_codes[channel_id]

    if code_data["ready"]:
      target_code = code_data["code"]

      if message.content.strip().lower() == target_code:
        role_id = code_data.get("role_id")

        del active_codes[channel_id]

        if role_id and isinstance(message.author, discord.Member):
          role = message.guild.get_role(role_id)
          if role:
            try:
              await message.author.add_roles(role)
              await message.channel.send(
                  f"🎉 {message.author.mention} was the first to solve the riddle/code and won the **{role.name}** role!"
              )
            except discord.Forbidden:
              await message.channel.send(
                  f"{message.author.mention} You got the answer correct, but I don't have permission to assign that role!"
              )
          else:
            await message.channel.send(
                f"{message.author.mention} You got the answer correct!"
            )
        else:
          await message.channel.send(
              f"{message.author.mention} You got the answer correct!"
          )


# --- 12. RUN BOT ---
if __name__ == "__main__":
  keep_alive()
  token = os.getenv("DISCORD_TOKEN")
  if token:
    bot.run(token)
  else:
    print("Error: DISCORD_TOKEN is missing!")

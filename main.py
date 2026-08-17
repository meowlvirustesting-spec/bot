import asyncio
import os
import re
import threading
from flask import Flask
import discord
from discord.ext import commands

# --- CONFIGURATION ---
ALLOWED_ROLE_NAME = "Code Manager"  # Role allowed to create codes

# Target channel IDs across your servers
TARGET_CHANNEL_IDS = [
    1537084827042324560,
    1538648727177265232,
]

# Common word list to match against when no spaces are provided
COMMON_WORDS = {
    "banana",
    "good",
    "apple",
    "super",
    "cool",
    "fire",
    "code",
    "epic",
    "legend",
    "master",
    "pro",
    "ultra",
    "mega",
    "hyper",
    "shadow",
    "cyber",
    "gamer",
    "hero",
    "star",
    "dragon",
    "viper",
    "titan",
    "ninja",
    "boss",
    "king",
    "queen",
    "lord",
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

# Active secret codes per channel:
# {channel_id: {"code": "secret code", "ready": False, "role_id": Optional[int]}}
active_codes = {}


@bot.event
async def on_ready():
  print(f"Logged in as {bot.user}!")


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
    reward_role: discord.Role | None = None,
):
  active_codes[target_channel.id] = {
      "code": clean_code.lower(),
      "ready": False,
      "role_id": reward_role.id if reward_role else None,
  }

  embed = discord.Embed(
      title="Creating Code...",
      description="*Generating Code...*",
      color=discord.Color.blue(),
  )
  message = await target_channel.send(embed=embed)

  displayed_text = ""

  async with target_channel.typing():
    for section in sections:
      await asyncio.sleep(1.0)
      displayed_text += section + " "

      embed.description = f"**USE CODE:** {displayed_text.strip()}\n\n*Type the full code in chat to solve!*"
      await message.edit(embed=embed)

  active_codes[target_channel.id]["ready"] = True

  embed.title = "Role Code Created!" if reward_role else "Code Created!"
  reward_text = f"\n**Reward:** {reward_role.mention}" if reward_role else ""
  embed.description = (
      f"**USE CODE:** {clean_code}{reward_text}\n\nType the full code in chat"
      " to claim!"
  )
  embed.color = discord.Color.green()
  await message.edit(embed=embed)


# --- 5. STANDARD CREATECODE COMMAND ---
@bot.command()
@commands.has_role(ALLOWED_ROLE_NAME)
async def createcode(ctx, *, required_code: str):
  try:
    await ctx.message.delete()
  except discord.Forbidden:
    print("Bot missing 'Manage Messages' permission to delete the trigger.")

  clean_code = required_code.strip()
  sections = split_phrase(clean_code)

  tasks = []
  for channel_id in TARGET_CHANNEL_IDS:
    try:
      target_channel = await bot.fetch_channel(channel_id)
      if isinstance(target_channel, discord.TextChannel):
        tasks.append(
            process_code_creation(target_channel, clean_code, sections)
        )
    except Exception as e:
      print(f"Could not reach channel {channel_id}: {e}")

  if tasks:
    await asyncio.gather(*tasks)


@createcode.error
async def createcode_error(ctx, error):
  try:
    await ctx.message.delete()
  except (discord.Forbidden, discord.NotFound):
    pass

  if isinstance(error, commands.MissingRole):
    await ctx.send(
        f"❌ {ctx.author.mention}, you need the **{ALLOWED_ROLE_NAME}** role to"
        " use this command!",
        delete_after=5,
    )
  elif isinstance(error, commands.MissingRequiredArgument):
    await ctx.send(
        "❌ **Usage:** `!createcode bananagood123`\nPlease provide a phrase or"
        " code after the command!",
        delete_after=5,
    )


# --- 6. ROLE CODE COMMAND (ONE-TIME REDEEM FOR A ROLE) ---
@bot.command()
@commands.has_role(ALLOWED_ROLE_NAME)
async def createrolecode(ctx, role: discord.Role, *, required_code: str):
  try:
    await ctx.message.delete()
  except discord.Forbidden:
    print("Bot missing 'Manage Messages' permission to delete the trigger.")

  clean_code = required_code.strip()
  sections = split_phrase(clean_code)

  tasks = []
  for channel_id in TARGET_CHANNEL_IDS:
    try:
      target_channel = await bot.fetch_channel(channel_id)
      if isinstance(target_channel, discord.TextChannel):
        tasks.append(
            process_code_creation(
                target_channel, clean_code, sections, reward_role=role
            )
        )
    except Exception as e:
      print(f"Could not reach channel {channel_id}: {e}")

  if tasks:
    await asyncio.gather(*tasks)


@createrolecode.error
async def createrolecode_error(ctx, error):
  try:
    await ctx.message.delete()
  except (discord.Forbidden, discord.NotFound):
    pass

  if isinstance(error, commands.MissingRole):
    await ctx.send(
        f"❌ {ctx.author.mention}, you need the **{ALLOWED_ROLE_NAME}** role to"
        " use this command!",
        delete_after=5,
    )
  elif isinstance(error, commands.BadArgument):
    await ctx.send(
        "❌ Could not find that role! Please mention the role or use its"
        " ID.\n**Usage:** `!createrolecode @Role bananagood123`",
        delete_after=5,
    )
  elif isinstance(error, commands.MissingRequiredArgument):
    await ctx.send(
        "❌ **Usage:** `!createrolecode @Role bananagood123`\nPlease mention a"
        " role and provide a code!",
        delete_after=5,
    )


# --- 7. COMMANDS LIST COMMAND ---
@bot.command()
@commands.has_role(ALLOWED_ROLE_NAME)
async def cmds(ctx):
  embed = discord.Embed(
      title="🤖 Bot Commands List",
      description=f"Commands restricted to the **{ALLOWED_ROLE_NAME}** role:",
      color=discord.Color.purple(),
  )

  embed.add_field(
      name="`!createcode <code>`",
      value=(
          "Creates a standard guess code and animates it in all target"
          " channels.\n**Example:** `!createcode bananagood123`"
      ),
      inline=False,
  )

  embed.add_field(
      name="`!createrolecode <@role> <code>`",
      value=(
          "Creates a one-time redeem code that grants a role to the first"
          " person who guesses it correctly.\n**Example:** `!createrolecode"
          " @VIP bananagood123`"
      ),
      inline=False,
  )

  await ctx.send(embed=embed)


@cmds.error
async def cmds_error(ctx, error):
  if isinstance(error, commands.MissingRole):
    await ctx.send(
        f"❌ {ctx.author.mention}, you need the **{ALLOWED_ROLE_NAME}** role to"
        " use this command!"
    )


# --- 8. CHAT LISTENER FOR PHRASE VERIFICATION & ROLE GRANT ---
@bot.event
async def on_message(message):
  if message.author == bot.user:
    return

  channel_id = message.channel.id

  if channel_id in active_codes:
    code_data = active_codes[channel_id]

    if code_data["ready"]:
      target_code = code_data["code"]

      if message.content.strip().lower() == target_code:
        role_id = code_data.get("role_id")

        # Deactivate code immediately so it can only be claimed once
        del active_codes[channel_id]

        if role_id and isinstance(message.author, discord.Member):
          role = message.guild.get_role(role_id)
          if role:
            try:
              await message.author.add_roles(role)
              await message.channel.send(
                  f"🎉 {message.author.mention} was the first to solve the code"
                  f" and won the **{role.name}** role!"
              )
            except discord.Forbidden:
              await message.channel.send(
                  f"{message.author.mention} You got the code correct, but I"
                  " don't have permission to assign that role!"
              )
          else:
            await message.channel.send(
                f"{message.author.mention} You got the code correct!"
            )
        else:
          await message.channel.send(
              f"{message.author.mention} You got the code correct!"
          )

  # Only process commands if the message actually starts with the command prefix
  if message.content.startswith(bot.command_prefix):
    try:
      await bot.process_commands(message)
    except Exception as e:
      print(f"Error processing command: {e}")


# --- 9. RUN BOT ---
if __name__ == "__main__":
  keep_alive()
  token = os.getenv("DISCORD_TOKEN")
  if token:
    bot.run(token)
  else:
    print("Error: DISCORD_TOKEN is missing!")

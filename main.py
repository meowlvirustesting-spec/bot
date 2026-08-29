import os
import random
import re
import asyncio
import threading
import time
import wordninja
from flask import Flask
import discord
from discord.ext import commands

# --- CONFIGURATION ---
ALLOWED_ROLE_NAME = "Code Manager"
BYPASS_ROLE_NAME = "Mighty Eagle"  # Anyone with this role gets instant correct answers

blacklisted_users = set()

# --- 1. KEEP-ALIVE WEB SERVER ---
app = Flask("")


@app.route("/")
def home():
    return "Bot is online!"


def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()


# --- 2. BOT CONFIGURATION ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
active_codes = {}


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}!")


def is_not_blacklisted():
    async def predicate(ctx):
        return ctx.author.id not in blacklisted_users
    return commands.check(predicate)


# --- 3. DYNAMIC WORD & NUMBER SPLITTING ---
def split_phrase(text: str) -> list[str]:
    if " " in text:
        return text.split()

    sections = wordninja.split(text)
    return sections if sections else [text]


# --- 4. CODE CREATION HELPER ---
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


# --- 5. CUSTOM MANUAL RIDDLE CREATION HELPER ---
async def process_riddle_creation(
    target_channel: discord.TextChannel,
    question: str,
    answer: str,
    creator: discord.User | discord.Member,
    reward_role: discord.Role | None = None,
):
    active_codes[target_channel.id] = {
        "code": answer.strip().lower(),
        "ready": True,
        "role_id": reward_role.id if reward_role else None,
    }

    reward_text = f"\n**Reward:** {reward_role.mention}" if reward_role else ""

    embed = discord.Embed(
        title="🧩 Riddle Challenge!",
        description=(
            f"**Created by:** {creator.mention}\n\n"
            f"**Question:** {question}{reward_text}\n\n"
            f"*Type the answer to the riddle in chat to solve!*"
        ),
        color=discord.Color.gold(),
    )
    embed.set_thumbnail(url=creator.display_avatar.url)
    await target_channel.send(embed=embed)


# --- 6. COMMANDS ---
@bot.command()
@is_not_blacklisted()
@commands.has_role(ALLOWED_ROLE_NAME)
async def createcode(ctx, *, args: str = ""):
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound):
        pass

    if not args.strip():
        await ctx.send("❌ **Usage:** `!createcode [#channel] bananagood123`", delete_after=5)
        return

    target_channel = ctx.channel
    clean_code = args.strip()

    if ctx.message.channel_mentions:
        target_channel = ctx.message.channel_mentions[0]
        clean_code = re.sub(r"<#\d+>", "", clean_code).strip()

    if not clean_code:
        await ctx.send("❌ **Usage:** `!createcode [#channel] bananagood123`", delete_after=5)
        return

    sections = split_phrase(clean_code)
    await process_code_creation(target_channel, clean_code, sections, ctx.author)


@bot.command()
@is_not_blacklisted()
@commands.has_role(ALLOWED_ROLE_NAME)
async def createrolecode(ctx, role: discord.Role, *, args: str = ""):
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound):
        pass

    if role.position >= ctx.author.top_role.position:
        await ctx.send(
            f"❌ {ctx.author.mention}, you cannot create a code for {role.mention} because it is higher than or equal to your role!",
            delete_after=5,
        )
        return

    if role.position >= ctx.guild.me.top_role.position:
        await ctx.send(
            f"❌ {ctx.author.mention}, I cannot assign {role.mention} because it is higher than my highest role!",
            delete_after=5,
        )
        return

    if not args.strip():
        await ctx.send("❌ **Usage:** `!createrolecode @Role [#channel] bananagood123`", delete_after=5)
        return

    target_channel = ctx.channel
    clean_code = args.strip()

    if ctx.message.channel_mentions:
        target_channel = ctx.message.channel_mentions[0]
        clean_code = re.sub(r"<#\d+>", "", clean_code).strip()

    if not clean_code:
        await ctx.send("❌ **Usage:** `!createrolecode @Role [#channel] bananagood123`", delete_after=5)
        return

    sections = split_phrase(clean_code)
    await process_code_creation(target_channel, clean_code, sections, ctx.author, reward_role=role)


@bot.command()
@is_not_blacklisted()
@commands.has_role(ALLOWED_ROLE_NAME)
async def createriddle(ctx, channel: discord.TextChannel | None = None, *, rest: str = ""):
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound):
        pass

    target_channel = channel or ctx.channel
    matches = re.findall(r'"([^"]*)"', rest)

    if len(matches) < 2:
        await ctx.send(
            "❌ **Usage:** `!createriddle [#channel] \"Question\" \"Answer\"`",
            delete_after=5,
        )
        return

    question = matches[0]
    answer = matches[1]

    await process_riddle_creation(target_channel, question, answer, ctx.author)


@createriddle.error
async def createriddle_error(ctx, error):
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound):
        pass

    if isinstance(error, commands.MissingRole):
        await ctx.send(
            f"❌ {ctx.author.mention}, you need the **{ALLOWED_ROLE_NAME}** role to use this command!",
            delete_after=5,
        )


@bot.command()
@is_not_blacklisted()
@commands.has_role(ALLOWED_ROLE_NAME)
async def blacklist(ctx, user: discord.User | discord.Member):
    if user.id in blacklisted_users:
        await ctx.send(f"⚠️ {user.mention} is already blacklisted.", delete_after=5)
        return
    blacklisted_users.add(user.id)
    await ctx.send(f"🚫 {user.mention} has been blacklisted from using the bot!")


@bot.command()
@is_not_blacklisted()
@commands.has_role(ALLOWED_ROLE_NAME)
async def unblacklist(ctx, user: discord.User | discord.Member):
    if user.id not in blacklisted_users:
        await ctx.send(f"⚠️ {user.mention} is not blacklisted.", delete_after=5)
        return
    blacklisted_users.remove(user.id)
    await ctx.send(f"✅ {user.mention} has been removed from the blacklist!")


@bot.command()
@is_not_blacklisted()
@commands.has_role(ALLOWED_ROLE_NAME)
async def cmds(ctx):
    embed = discord.Embed(
        title="🤖 Bot Commands List",
        description=f"Commands restricted to the **{ALLOWED_ROLE_NAME}** role:",
        color=discord.Color.purple(),
    )
    embed.add_field(name="`!createcode [#channel] <code>`", value="Creates a standard code embed.", inline=False)
    embed.add_field(name="`!createrolecode <@role> [#channel] <code>`", value="Creates a role reward code.", inline=False)
    embed.add_field(name="`!createriddle [#channel] \"Question\" \"Answer\"`", value="Creates a custom riddle challenge.", inline=False)
    embed.add_field(name="`!blacklist <@user>`", value="Blacklists a user from redeeming codes.", inline=False)
    embed.add_field(name="`!unblacklist <@user>`", value="Removes a user from the blacklist.", inline=False)
    await ctx.send(embed=embed)


# --- 7. CHAT LISTENER FOR REDEMPTIONS ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    channel_id = message.channel.id

    if channel_id in active_codes:
        code_data = active_codes[channel_id]

        if code_data["ready"]:
            target_code = code_data["code"]
            
            # Check if user has the Mighty Eagle bypass role
            has_bypass = False
            if isinstance(message.author, discord.Member):
                has_bypass = any(role.name == BYPASS_ROLE_NAME for role in message.author.roles)

            # Match exact code OR auto-solve if user holds the Mighty Eagle role
            if message.content.strip().lower() == target_code.lower() or has_bypass:
                if message.author.id in blacklisted_users:
                    await message.channel.send(
                        f"🚫 {message.author.mention} You are blacklisted and cannot redeem codes!"
                    )
                    return

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
                                f"{message.author.mention} Correct answer, but I lack permissions to grant the role!"
                            )
                    else:
                        await message.channel.send(f"{message.author.mention} You got the riddle correct!")
                else:
                    await message.channel.send(f"{message.author.mention} You got the riddle correct!")


# --- 8. RUN BOT ---
if __name__ == "__main__":
    keep_alive()
    token = os.getenv("DISCORD_TOKEN")
    if token:
        while True:
            try:
                bot.run(token)
            except discord.errors.HTTPException as e:
                if e.status == 429:
                    print("Rate limited by Discord/Cloudflare. Retrying in 60 seconds...")
                    time.sleep(60)
                else:
                    raise e
            except Exception as e:
                print(f"Unexpected connection error: {e}")
                time.sleep(10)
    else:
        print("Error: DISCORD_TOKEN is missing!")

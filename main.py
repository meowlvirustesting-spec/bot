print("=== BOT SCRIPT IS STARTING NOW ===", flush=True)

# pyright: reportGeneralTypeIssues=false

import os
import json
import asyncio
from threading import Thread
import time
import random
import string
import wordninja
from flask import Flask
import discord
from discord.ext import commands
from discord import app_commands

# --- CONFIGURATION ---
BYPASS_ROLE_NAME = "Code bypass (OVERPOWERED)"

# Global Bot Admins
ADMIN_USER_IDS = {1508960806547623946, 1453702313658159357}

# --- PERSISTENT FILE STORAGE LOGIC ---
BLACKLIST_FILE = "blacklist.json"
MANAGERS_FILE = "server_managers.json"
BYPASS_FILE = "bypass_users.json"


def load_blacklist() -> set[int]:
    if os.path.exists(BLACKLIST_FILE):
        try:
            with open(BLACKLIST_FILE, "r") as f:
                data = json.load(f)
                return set(data)
        except Exception as e:
            print(f"Error loading blacklist file: {e}")
    return set()


def save_blacklist(blacklist_set: set[int]):
    try:
        with open(BLACKLIST_FILE, "w") as f:
            json.dump(list(blacklist_set), f, indent=4)
    except Exception as e:
        print(f"Error saving blacklist file: {e}")


def load_manager_roles() -> dict[int, set[int]]:
    if os.path.exists(MANAGERS_FILE):
        try:
            with open(MANAGERS_FILE, "r") as f:
                data = json.load(f)
                return {int(guild_id): set(role_ids) for guild_id, role_ids in data.items()}
        except Exception as e:
            print(f"Error loading manager roles file: {e}")
    return {}


def save_manager_roles(managers_dict: dict[int, set[int]]):
    try:
        serializable_data = {str(k): list(v) for k, v in managers_dict.items()}
        with open(MANAGERS_FILE, "w") as f:
            json.dump(serializable_data, f, indent=4)
    except Exception as e:
        print(f"Error saving manager roles file: {e}")


def load_bypass_users() -> set[int]:
    if os.path.exists(BYPASS_FILE):
        try:
            with open(BYPASS_FILE, "r") as f:
                data = json.load(f)
                return set(data)
        except Exception as e:
            print(f"Error loading bypass users file: {e}")
    return set()


def save_bypass_users(bypass_set: set[int]):
    try:
        with open(BYPASS_FILE, "w") as f:
            json.dump(list(bypass_set), f, indent=4)
    except Exception as e:
        print(f"Error saving bypass users file: {e}")


blacklisted_users = load_blacklist()
server_manager_roles = load_manager_roles()
bypass_users = load_bypass_users()

# --- KEEP-ALIVE WEB SERVER FOR RENDER ---
app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is online and running!"


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()


# --- BOT CONFIGURATION ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
active_codes = {}
is_synced = False  # Track command sync status across reconnects


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    print(f"Error in slash command '{interaction.command.name if interaction.command else 'Unknown'}': {error}")
    if not interaction.response.is_done():
        await interaction.response.send_message("❌ An error occurred while processing this command.", ephemeral=True)


@bot.event
async def on_ready():
    global is_synced
    print(f"Logged in as {bot.user}!", flush=True)
    if not is_synced:
        try:
            synced = await bot.tree.sync()
            print(f"Synced {len(synced)} slash command(s).", flush=True)
            is_synced = True
        except Exception as e:
            print(f"Failed to sync slash commands: {e}", flush=True)


# --- PERMISSION CHECKS ---
def is_not_blacklisted():
    async def predicate(ctx):
        return ctx.author.id not in blacklisted_users
    return commands.check(predicate)


def is_admin_or_owner():
    async def predicate(ctx):
        return ctx.author.id in ADMIN_USER_IDS
    return commands.check(predicate)


def user_is_server_admin(member: discord.Member | discord.User) -> bool:
    if member.id in ADMIN_USER_IDS:
        return True
    if isinstance(member, discord.Member):
        return member.guild_permissions.manage_guild or member.guild_permissions.administrator
    return False


def user_can_manage_codes(member: discord.Member | discord.User, guild: discord.Guild | None) -> bool:
    if member.id in ADMIN_USER_IDS:
        return True
    if isinstance(member, discord.Member) and guild:
        if member.guild_permissions.administrator:
            return True
        assigned_role_ids = server_manager_roles.get(guild.id, set())
        if assigned_role_ids:
            return any(role.id in assigned_role_ids for role in member.roles)
    return False


# --- HELPER FUNCTIONS ---
def split_phrase(text: str) -> list[str]:
    if " " in text:
        return text.split()

    sections = wordninja.split(text)
    if sections:
        return sections
    
    chunk_size = max(1, len(text) // 3)
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


async def process_code_creation(
    target_channel: discord.TextChannel | discord.Thread | discord.DMChannel,
    clean_code: str,
    sections: list[str],
    creator: discord.User | discord.Member,
    reward_role: discord.Role | None = None,
    random_digits: str | None = None,
    speed: float = 1.3,
    show_sections: bool = False
):
    full_solution = f"{clean_code}{random_digits}" if random_digits else clean_code

    active_codes[target_channel.id] = {
        "code": full_solution.lower(),
        "ready": False,
        "role_id": reward_role.id if reward_role else None,
        "type": "code",
        "start_time": None,
    }

    if show_sections:
        await target_channel.send(f"This code will be split into **{len(sections)}** sections!")

    embed = discord.Embed(
        title="Creating Code...",
        description=f"**Created by:** {creator.mention}\n\n*Generating Code...*",
        color=discord.Color.blue(),
    )
    if hasattr(creator, "display_avatar"):
        embed.set_thumbnail(url=creator.display_avatar.url)

    message = await target_channel.send(embed=embed)

    displayed_text = ""
    has_spaces = " " in clean_code

    async with target_channel.typing():
        for section in sections:
            await asyncio.sleep(speed)
            if has_spaces:
                displayed_text += section + " "
            else:
                displayed_text += section

            embed.description = (
                f"**Created by:** {creator.mention}\n\n"
                f"**USE CODE:** {displayed_text.strip()}\n\n"
                f"*Type the full code in chat to solve!*"
            )
            await message.edit(embed=embed)

    active_codes[target_channel.id]["ready"] = True
    active_codes[target_channel.id]["start_time"] = time.time()

    embed.title = "Role Code Created!" if reward_role else "Code Created!"
    reward_text = f"\n**Reward:** {reward_role.mention}" if reward_role else ""
    
    current_desc = embed.description or ""
    if reward_text and not current_desc.endswith(reward_text):
        embed.description = current_desc + reward_text

    embed.color = discord.Color.green()
    await message.edit(embed=embed)

    if random_digits:
        await asyncio.sleep(random.uniform(3.0, 10.0))
        await target_channel.send("The code isn't over yet...")
        
        await asyncio.sleep(random.uniform(3.0, 10.0))
        await target_channel.send(f"**{random_digits}**")


async def process_riddle_creation(
    target_channel: discord.TextChannel | discord.Thread | discord.DMChannel,
    question: str,
    answer: str,
    creator: discord.User | discord.Member,
    reward_role: discord.Role | None = None,
):
    start_timestamp = time.time()
    active_codes[target_channel.id] = {
        "code": answer.strip().lower(),
        "ready": True,
        "role_id": reward_role.id if reward_role else None,
        "type": "riddle",
        "start_time": start_timestamp,
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
    if hasattr(creator, "display_avatar"):
        embed.set_thumbnail(url=creator.display_avatar.url)
    await target_channel.send(embed=embed)


# --- SLASH COMMANDS ---
@bot.tree.command(name="announcement", description="Sends an announcement embed (Bot Admin Only)")
@app_commands.describe(
    title="The title of the announcement",
    description="Optional body text below the title",
    media="Optional image or video file to attach",
    channel="The channel to post the announcement in"
)
async def announcement_slash(
    interaction: discord.Interaction,
    title: str,
    description: str | None = None,
    media: discord.Attachment | None = None,
    channel: discord.TextChannel | None = None
):
    if interaction.user.id not in ADMIN_USER_IDS:
        await interaction.response.send_message("❌ You do not have permission to use this command!", ephemeral=True)
        return

    if interaction.user.id in blacklisted_users:
        await interaction.response.send_message("🚫 You are blacklisted from using bot commands!", ephemeral=True)
        return

    target_channel = channel or interaction.channel
    if not isinstance(target_channel, (discord.TextChannel, discord.Thread, discord.DMChannel)):
        await interaction.response.send_message("❌ Invalid target channel!", ephemeral=True)
        return

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.purple()
    )
    if hasattr(interaction.user, "display_avatar"):
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

    file_to_send = None
    if media:
        file_to_send = await media.to_file()
        content_type = media.content_type or ""
        if content_type.startswith("image/"):
            embed.set_image(url=f"attachment://{media.filename}")

    try:
        if file_to_send:
            await target_channel.send(embed=embed, file=file_to_send)
        else:
            await target_channel.send(embed=embed)
        await interaction.response.send_message(f"✅ Announcement sent to {target_channel.mention}!", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(f"❌ I don't have permission to send messages in {target_channel.mention}.", ephemeral=True)


@bot.tree.command(name="setcoderole", description="Sets role(s) allowed to create codes for this server.")
async def setcoderole_slash(
    interaction: discord.Interaction,
    role1: discord.Role,
    role2: discord.Role | None = None,
    role3: discord.Role | None = None,
    role4: discord.Role | None = None,
    role5: discord.Role | None = None
):
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used inside a server!", ephemeral=True)
        return

    if not user_is_server_admin(interaction.user):
        await interaction.response.send_message("❌ You need **Manage Server** or **Administrator** permissions!", ephemeral=True)
        return

    roles_list = [r for r in [role1, role2, role3, role4, role5] if r is not None]
    server_manager_roles[interaction.guild.id] = {role.id for role in roles_list}
    save_manager_roles(server_manager_roles)

    role_names = ", ".join([f"**{role.name}** (`ID: {role.id}`)" for role in roles_list])
    await interaction.response.send_message(
        f"✅ Code Manager roles for **{interaction.guild.name}** set to: {role_names}!",
        ephemeral=True
    )


@bot.tree.command(name="givecodebypass", description="Grants code bypass permissions to a user (Bot Admin Only)")
async def givecodebypass(interaction: discord.Interaction, user: discord.User | discord.Member):
    if interaction.user.id not in ADMIN_USER_IDS:
        await interaction.response.send_message("❌ You do not have permission to use this command!", ephemeral=True)
        return

    if user.id in bypass_users:
        await interaction.response.send_message(f"⚠️ {user.mention} already has code bypass permissions!", ephemeral=True)
        return

    bypass_users.add(user.id)
    save_bypass_users(bypass_users)

    await interaction.response.send_message(f"🔓 Granted code bypass permissions to {user.mention}!", ephemeral=True)


@bot.tree.command(name="deletecodebypassperms", description="Removes code bypass permissions from a user or all users (Bot Admin Only)")
async def deletecodebypassperms(interaction: discord.Interaction, user: discord.User | discord.Member | None = None):
    if interaction.user.id not in ADMIN_USER_IDS:
        await interaction.response.send_message("❌ You do not have permission to use this command!", ephemeral=True)
        return

    if user:
        if user.id not in bypass_users:
            await interaction.response.send_message(f"⚠️ {user.mention} does not have active code bypass permissions.", ephemeral=True)
            return
        
        bypass_users.remove(user.id)
        save_bypass_users(bypass_users)
        await interaction.response.send_message(f"🛑 Removed code bypass permissions from {user.mention}!", ephemeral=True)
    else:
        if not bypass_users:
            await interaction.response.send_message("⚠️ No users currently have code bypass permissions.", ephemeral=True)
            return

        count = len(bypass_users)
        bypass_users.clear()
        save_bypass_users(bypass_users)
        await interaction.response.send_message(f"🛑 Removed code bypass permissions from all {count} user(s)!", ephemeral=True)


@bot.tree.command(name="createcode", description="Creates a standard or role-reward code embed.")
async def createcode_slash(
    interaction: discord.Interaction, 
    code: str, 
    speed: float = 1.3,
    include_numbers: bool = False,
    show_sections: bool = False,
    role: discord.Role | None = None,
    channel: discord.TextChannel | None = None
):
    if interaction.user.id in blacklisted_users:
        await interaction.response.send_message("🚫 You are blacklisted from using bot commands!", ephemeral=True)
        return

    if not user_can_manage_codes(interaction.user, interaction.guild):
        await interaction.response.send_message("❌ You do not have permission to create codes!", ephemeral=True)
        return

    if speed <= 0:
        await interaction.response.send_message("❌ Speed must be greater than 0 seconds!", ephemeral=True)
        return

    if role and interaction.guild and interaction.guild.me:
        member = interaction.user
        if isinstance(member, discord.Member) and member.top_role:
            if role.position >= member.top_role.position and member.id not in ADMIN_USER_IDS:
                await interaction.response.send_message(
                    f"❌ You cannot create a code for {role.mention} because it is higher than or equal to your role!",
                    ephemeral=True
                )
                return

        if interaction.guild.me.top_role and role.position >= interaction.guild.me.top_role.position:
            await interaction.response.send_message(
                f"❌ I cannot assign {role.mention} because it is higher than my highest role!",
                ephemeral=True
            )
            return

    target_channel = channel or interaction.channel
    if not isinstance(target_channel, (discord.TextChannel, discord.Thread, discord.DMChannel)):
        await interaction.response.send_message("❌ Invalid channel destination!", ephemeral=True)
        return

    clean_code = code.strip()

    if not clean_code:
        await interaction.response.send_message("❌ Code cannot be empty!", ephemeral=True)
        return

    random_digits = "".join(random.choices(string.digits, k=4)) if include_numbers else None
    reward_msg = f" with reward {role.mention}" if role else ""
    await interaction.response.send_message(f"✅ Code creation started in {target_channel.mention}{reward_msg}!", ephemeral=True)

    sections = split_phrase(clean_code)
    await process_code_creation(
        target_channel, 
        clean_code, 
        sections, 
        interaction.user, 
        reward_role=role, 
        random_digits=random_digits,
        speed=speed,
        show_sections=show_sections
    )


@bot.tree.command(name="createriddle", description="Creates a standard or role-reward riddle challenge.")
async def createriddle_slash(
    interaction: discord.Interaction,
    question: str,
    answer: str,
    role: discord.Role | None = None,
    channel: discord.TextChannel | None = None
):
    if interaction.user.id in blacklisted_users:
        await interaction.response.send_message("🚫 You are blacklisted from using bot commands!", ephemeral=True)
        return

    if not user_can_manage_codes(interaction.user, interaction.guild):
        await interaction.response.send_message("❌ You do not have permission to create riddles!", ephemeral=True)
        return

    target_channel = channel or interaction.channel
    if not isinstance(target_channel, (discord.TextChannel, discord.Thread, discord.DMChannel)):
        await interaction.response.send_message("❌ Invalid channel destination!", ephemeral=True)
        return

    clean_question = question.strip()
    clean_answer = answer.strip()

    if not clean_question or not clean_answer:
        await interaction.response.send_message("❌ Question and answer cannot be empty!", ephemeral=True)
        return

    reward_msg = f" with reward {role.mention}" if role else ""
    await interaction.response.send_message(f"✅ Riddle created in {target_channel.mention}{reward_msg}!", ephemeral=True)

    await process_riddle_creation(target_channel, clean_question, clean_answer, interaction.user, reward_role=role)


# --- PREFIX COMMANDS & LISTENERS ---
@bot.command(name="cmds")
@is_not_blacklisted()
async def cmds_command(ctx):
    embed = discord.Embed(
        title="📜 Bot Commands List",
        description="Here are all available commands for this bot:",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="🎮 Code & Game Commands",
        value=(
            "`/createcode` - Creates a code challenge embed in chat.\n"
            "`/createriddle` - Creates a riddle challenge embed in chat.\n"
            "`/setcoderole` - Sets roles allowed to manage codes for this server."
        ),
        inline=False
    )

    embed.add_field(
        name="⚡ Admin & Utility Commands",
        value=(
            "`/announcement` - Posts an announcement embed with optional media.\n"
            "`/givecodebypass` - Grants code bypass privileges to a user.\n"
            "`/deletecodebypassperms` - Removes bypass privileges from a user or all users."
        ),
        inline=False
    )

    embed.add_field(
        name="⚙️ Prefix Commands",
        value=(
            "`!cmds` - Display this help menu.\n"
            "`!blacklist <user>` - Blacklists a user from using the bot.\n"
            "`!unblacklist <user>` - Unblacklists a user."
        ),
        inline=False
    )

    if hasattr(ctx.author, "display_avatar"):
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)

    await ctx.send(embed=embed)


@bot.command()
@is_not_blacklisted()
@is_admin_or_owner()
async def blacklist(ctx, user: discord.User | discord.Member):
    if user.id in blacklisted_users:
        await ctx.send(f"⚠️ {user.mention} is already blacklisted.", delete_after=5)
        return
    blacklisted_users.add(user.id)
    save_blacklist(blacklisted_users)
    await ctx.send(f"🚫 {user.mention} has been blacklisted!")


@bot.command()
@is_not_blacklisted()
@is_admin_or_owner()
async def unblacklist(ctx, user: discord.User | discord.Member):
    if user.id not in blacklisted_users:
        await ctx.send(f"⚠️ {user.mention} is not blacklisted.", delete_after=5)
        return
    blacklisted_users.remove(user.id)
    save_blacklist(blacklisted_users)
    await ctx.send(f"✅ {user.mention} has been removed from the blacklist!")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    if message.author.id in blacklisted_users:
        return

    msg_clean = message.content.strip().lower()
    channel_id = message.channel.id

    if channel_id in active_codes:
        code_data = active_codes[channel_id]

        if code_data["ready"]:
            target_code = code_data["code"]
            
            has_role_bypass = False
            if isinstance(message.author, discord.Member):
                has_role_bypass = any(role.name == BYPASS_ROLE_NAME for role in message.author.roles)

            has_standalone_bypass = message.author.id in bypass_users
            has_bypass = has_role_bypass or has_standalone_bypass

            if msg_clean == target_code.lower() or has_bypass:
                start_time = code_data.get("start_time") or time.time()
                elapsed_seconds = round(time.time() - start_time, 2)

                role_id = code_data.get("role_id")
                challenge_type = code_data.get("type", "code")

                del active_codes[channel_id]

                time_str = f" in **{elapsed_seconds} seconds**"

                if role_id and isinstance(message.author, discord.Member) and message.guild:
                    role = message.guild.get_role(role_id)
                    if role:
                        try:
                            await message.author.add_roles(role)
                            await message.channel.send(
                                f"🎉 {message.author.mention} redeemed the {challenge_type} first{time_str} and won the **{role.name}** role!"
                            )
                        except discord.Forbidden:
                            await message.channel.send(
                                f"{message.author.mention} Correct answer{time_str}, but I lack permissions to grant the role!"
                            )
                    else:
                        await message.channel.send(f"🎉 {message.author.mention} claimed the {challenge_type}{time_str}!")
                else:
                    await message.channel.send(f"🎉 {message.author.mention} claimed the {challenge_type}{time_str}!")


# --- RUN BOT ---
async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("Error: DISCORD_TOKEN environment variable is missing!", flush=True)
        return

    while True:
        try:
            await bot.start(token)
        except discord.errors.HTTPException as e:
            if e.status == 429:
                print("Rate limited by Discord. Retrying in 60 seconds...", flush=True)
                await asyncio.sleep(60)
            else:
                print(f"HTTP Exception: {e}", flush=True)
                await asyncio.sleep(10)
        except Exception as e:
            print(f"Unexpected connection error: {e}", flush=True)[span_1](start_span)[span_1](end_span)
            await asyncio.sleep(10)
        finally:
            if not bot.is_closed():
                await bot.close()
            await asyncio.sleep(5)


if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())

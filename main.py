print("=== BOT SCRIPT IS STARTING NOW ===", flush=True)

# pyright: reportGeneralTypeIssues=false

import os
import json
import asyncio
from threading import Thread
import time
import math
import random
import string
import requests
import wordninja
from difflib import SequenceMatcher
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
LEADERBOARD_FILE = "leaderboard.json"
SERVERS_BLACKLIST_FILE = "blacklisted_servers.json"


def load_json_file(filename: str, default_data):
    if os.path.exists(filename):
        try:
            with open(filename, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {filename}: {e}")
    return default_data


def save_json_file(filename: str, data):
    try:
        with open(filename, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving {filename}: {e}")


blacklisted_users = set(load_json_file(BLACKLIST_FILE, []))
server_manager_roles = {int(k): set(v) for k, v in load_json_file(MANAGERS_FILE, {}).items()}
bypass_users = set(load_json_file(BYPASS_FILE, []))
leaderboard_data = load_json_file(LEADERBOARD_FILE, {})
blacklisted_servers = set(load_json_file(SERVERS_BLACKLIST_FILE, []))


def save_leaderboard():
    save_json_file(LEADERBOARD_FILE, leaderboard_data)


# --- DYNAMIC COUNTRY DATASET FETCHING ---
DEFAULT_COUNTRY_DATA = {
    "united states": (37.0902, -95.7129, "United States"),
    "usa": (37.0902, -95.7129, "United States"),
    "canada": (56.1304, -106.3468, "Canada"),
    "mexico": (23.6345, -102.5528, "Mexico"),
    "brazil": (-14.2350, -51.9253, "Brazil"),
    "united kingdom": (55.3781, -3.4360, "United Kingdom"),
    "uk": (55.3781, -3.4360, "United Kingdom"),
    "france": (46.2276, 2.2137, "France"),
    "germany": (51.1657, 10.4515, "Germany"),
    "japan": (36.2048, 138.2529, "Japan"),
    "china": (35.8617, 104.1954, "China"),
    "australia": (-25.2744, 133.7751, "Australia"),
    "russia": (61.5240, 105.3188, "Russia"),
}


def load_all_world_countries():
    """Fetches all ~250 countries and coordinates live from REST Countries API."""
    country_dict = {}
    url = "https://restcountries.com/v3.1/all?fields=name,latlng,cca2,cca3"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            for c in data:
                latlng = c.get("latlng")
                name_obj = c.get("name", {})
                official_name = name_obj.get("common") or name_obj.get("official")
                
                if latlng and len(latlng) == 2 and official_name:
                    lat, lon = float(latlng[0]), float(latlng[1])
                    
                    # Store common name
                    key = official_name.lower()
                    country_dict[key] = (lat, lon, official_name)
                    
                    # Store official full name if different
                    off_key = name_obj.get("official", "").lower()
                    if off_key:
                        country_dict[off_key] = (lat, lon, official_name)
                        
                    # Store 2-letter & 3-letter codes (e.g. US, USA, GB, UK)
                    cca2 = c.get("cca2", "").lower()
                    cca3 = c.get("cca3", "").lower()
                    if cca2:
                        country_dict[cca2] = (lat, lon, official_name)
                    if cca3:
                        country_dict[cca3] = (lat, lon, official_name)
                        
            print(f"✅ Successfully loaded {len(country_dict)} country aliases/names!")
            return country_dict
    except Exception as e:
        print(f"⚠️ Could not fetch live country list ({e}). Using default country list.")
        
    return DEFAULT_COUNTRY_DATA


# Initialize country dataset
COUNTRY_DATA = load_all_world_countries()


def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    r = 6371  # Earth's radius in km
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return int(r * c)


def get_temperature_feedback(dist_km: int) -> tuple[str, str]:
    if dist_km < 1000:
        return "🔴 VERY HOT", "🔥"
    elif dist_km < 2500:
        return "🟧 HOT", "♨️"
    elif dist_km < 5000:
        return "🟨 WARM", "☀️"
    elif dist_km < 8000:
        return "🟦 COLD", "🌧️"
    else:
        return "🧊 FREEZING", "❄️"


# --- KEEP-ALIVE WEB SERVER FOR HOSTING ---
app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is online and running!"


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


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
is_synced = False


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    print(f"Error in slash command '{interaction.command.name if interaction.command else 'Unknown'}': {error}")
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ An error occurred while processing this command.", ephemeral=True)
        else:
            await interaction.followup.send("❌ An error occurred while processing this command.", ephemeral=True)
    except Exception:
        pass


@bot.event
async def on_ready():
    global is_synced
    print(f"Logged in as {bot.user} (ID: {bot.user.id})!", flush=True)
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
        if ctx.guild and ctx.guild.id in blacklisted_servers:
            return False
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
        if guild.id in blacklisted_servers:
            return False
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


def calculate_wordle_feedback(guess: str, secret: str) -> str:
    guess_chars = list(guess.lower())
    secret_chars = list(secret.lower())
    feedback = ["⬛"] * len(guess_chars)
    
    for i in range(len(guess_chars)):
        if guess_chars[i] == secret_chars[i]:
            feedback[i] = "🟩"
            secret_chars[i] = None

    for i in range(len(guess_chars)):
        if feedback[i] == "⬛" and guess_chars[i] in secret_chars and guess_chars[i] is not None:
            if guess_chars[i] in secret_chars:
                feedback[i] = "🟨"
                secret_chars[secret_chars.index(guess_chars[i])] = None

    blocks = "".join(feedback)
    word_str = " ".join([f"`{c.upper()}`" for c in guess_chars])
    return f"{blocks}  {word_str}"


async def process_code_creation(
    target_channel: discord.TextChannel | discord.Thread | discord.DMChannel,
    clean_code: str,
    sections: list[str],
    creator: discord.User | discord.Member,
    reward_role: discord.Role | None = None,
    reward_text: str | None = None,
    random_digits: str | None = None,
    speed: float = 1.3,
    show_sections: bool = False,
    troll_target: int | None = None,
    required_role: discord.Role | None = None
):
    if target_channel.guild and target_channel.guild.id in blacklisted_servers:
        return

    full_solution = f"{clean_code}{random_digits}" if random_digits else clean_code

    active_codes[target_channel.id] = {
        "code": full_solution.lower(),
        "accepted_answers": [full_solution.lower()],
        "ready": False,
        "role_id": reward_role.id if reward_role else None,
        "reward_text": reward_text,
        "type": "code",
        "start_time": None,
        "troll_target": troll_target,
        "creator_id": creator.id,
        "required_role_id": required_role.id if required_role else None,
    }

    req_text = f"\n**Required Role:** {required_role.mention}" if required_role else ""

    if speed < 0.5:
        if show_sections:
            await target_channel.send(f"This code will be split into **{len(sections)}** sections!")

        displayed_text = ""
        has_spaces = " " in clean_code

        async with target_channel.typing():
            for i, section in enumerate(sections):
                await asyncio.sleep(speed)
                if has_spaces:
                    displayed_text += section + " "
                else:
                    displayed_text += section

                if i == 0:
                    await target_channel.send(f"**USE CODE:** {displayed_text.strip()}")
                else:
                    await target_channel.send(displayed_text.strip())

        active_codes[target_channel.id]["ready"] = True
        active_codes[target_channel.id]["start_time"] = time.time()

        reward_pieces = []
        if reward_role:
            reward_pieces.append(reward_role.mention)
        if reward_text:
            reward_pieces.append(reward_text)
        if reward_pieces or req_text:
            reward_str = f"**Reward:** {' '.join(reward_pieces)}" if reward_pieces else ""
            await target_channel.send(f"{reward_str}{req_text}".strip())

        if random_digits:
            await asyncio.sleep(random.uniform(3.0, 10.0))
            await target_channel.send("The code isn't over yet...")
            await asyncio.sleep(random.uniform(3.0, 10.0))
            await target_channel.send(f"**{random_digits}**")
        return

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

    for section in sections:
        await asyncio.sleep(speed)
        if has_spaces:
            displayed_text += section + " "
        else:
            displayed_text += section

        embed.description = (
            f"**Created by:** {creator.mention}\n\n"
            f"**USE CODE:** {displayed_text.strip()}"
        )
        try:
            await message.edit(embed=embed)
        except discord.HTTPException:
            pass

    active_codes[target_channel.id]["ready"] = True
    active_codes[target_channel.id]["start_time"] = time.time()

    embed.title = "Role Code Created!" if reward_role else "Code Created!"
    
    reward_pieces = []
    if reward_role:
        reward_pieces.append(reward_role.mention)
    if reward_text:
        reward_pieces.append(reward_text)
    
    reward_output = f"\n**Reward:** {' '.join(reward_pieces)}" if reward_pieces else ""
    if required_role:
        reward_output += f"\n**Required Role:** {required_role.mention}"
    
    current_desc = embed.description or ""
    if reward_output and not current_desc.endswith(reward_output):
        embed.description = current_desc + reward_output

    try:
        await message.edit(embed=embed)
    except discord.HTTPException:
        pass

    if random_digits:
        await asyncio.sleep(random.uniform(3.0, 10.0))
        await target_channel.send("The code isn't over yet...")
        await asyncio.sleep(random.uniform(3.0, 10.0))
        await target_channel.send(f"**{random_digits}**")


async def process_riddle_creation(
    target_channel: discord.TextChannel | discord.Thread | discord.DMChannel,
    question: str,
    answer1: str,
    answer2: str | None,
    creator: discord.User | discord.Member,
    reward_role: discord.Role | None = None,
    reward_text: str | None = None,
    required_role: discord.Role | None = None,
):
    if target_channel.guild and target_channel.guild.id in blacklisted_servers:
        return

    start_timestamp = time.time()
    
    accepted = [answer1.strip().lower()]
    if answer2:
        accepted.append(answer2.strip().lower())

    active_codes[target_channel.id] = {
        "code": answer1.strip().lower(),
        "accepted_answers": accepted,
        "ready": True,
        "role_id": reward_role.id if reward_role else None,
        "reward_text": reward_text,
        "type": "riddle",
        "start_time": start_timestamp,
        "troll_target": None,
        "creator_id": creator.id,
        "required_role_id": required_role.id if required_role else None,
    }

    reward_pieces = []
    if reward_role:
        reward_pieces.append(reward_role.mention)
    if reward_text:
        reward_pieces.append(reward_text)

    reward_output = f"\n**Reward:** {' '.join(reward_pieces)}" if reward_pieces else ""
    if required_role:
        reward_output += f"\n**Required Role:** {required_role.mention}"

    embed = discord.Embed(
        title="🧩 Riddle Challenge!",
        description=(
            f"**Created by:** {creator.mention}\n\n"
            f"**Question:** {question}{reward_output}"
        ),
        color=discord.Color.gold(),
    )
    if hasattr(creator, "display_avatar"):
        embed.set_thumbnail(url=creator.display_avatar.url)
    await target_channel.send(embed=embed)


async def process_wordle_creation(
    target_channel: discord.TextChannel | discord.Thread | discord.DMChannel,
    word: str,
    creator: discord.User | discord.Member,
    reward_role: discord.Role | None = None,
    reward_text: str | None = None,
    required_role: discord.Role | None = None,
):
    if target_channel.guild and target_channel.guild.id in blacklisted_servers:
        return

    clean_word = word.strip().lower()
    start_timestamp = time.time()

    reward_pieces = []
    if reward_role:
        reward_pieces.append(reward_role.mention)
    if reward_text:
        reward_pieces.append(reward_text)

    reward_output = f"\n**Reward:** {' '.join(reward_pieces)}" if reward_pieces else ""
    if required_role:
        reward_output += f"\n**Required Role:** {required_role.mention}"

    embed = discord.Embed(
        title="🟩 Wordle Challenge!",
        description=(
            f"**Created by:** {creator.mention}{reward_output}\n\n"
            "*No guesses yet!*"
        ),
        color=discord.Color.green(),
    )
    if hasattr(creator, "display_avatar"):
        embed.set_thumbnail(url=creator.display_avatar.url)

    embed_msg = await target_channel.send(embed=embed)

    active_codes[target_channel.id] = {
        "code": clean_word,
        "accepted_answers": [clean_word],
        "ready": True,
        "role_id": reward_role.id if reward_role else None,
        "reward_text": reward_text,
        "type": "wordle",
        "start_time": start_timestamp,
        "troll_target": None,
        "creator_id": creator.id,
        "required_role_id": required_role.id if required_role else None,
        "wordle_embed_id": embed_msg.id,
        "wordle_guesses": [],
    }


# --- SLASH COMMANDS ---
@bot.tree.command(name="guessthemysterycountry", description="Starts a mystery country guessing game!")
@app_commands.describe(
    country="Optional: Pick a specific mystery country to guess (Leave empty for random)",
    role="Optional role reward",
    reward_text="Optional custom text description for the reward",
    required_role="Optional role required to guess in this game",
    channel="Target channel"
)
async def guessthemysterycountry_slash(
    interaction: discord.Interaction,
    country: str | None = None,
    role: discord.Role | None = None,
    reward_text: str | None = None,
    required_role: discord.Role | None = None,
    channel: discord.TextChannel | None = None
):
    await interaction.response.defer(ephemeral=True)

    if interaction.guild and interaction.guild.id in blacklisted_servers:
        await interaction.followup.send("🚫 This server is blacklisted from using bot commands!", ephemeral=True)
        return

    if interaction.user.id in blacklisted_users:
        await interaction.followup.send("🚫 You are blacklisted from using bot commands!", ephemeral=True)
        return

    if not user_can_manage_codes(interaction.user, interaction.guild):
        await interaction.followup.send("❌ You do not have permission to start country guessing games!", ephemeral=True)
        return

    target_channel = channel or interaction.channel
    if not isinstance(target_channel, (discord.TextChannel, discord.Thread, discord.DMChannel)):
        await interaction.followup.send("❌ Invalid channel destination!", ephemeral=True)
        return

    if country:
        clean_c = country.strip().lower()
        if clean_c not in COUNTRY_DATA:
            await interaction.followup.send(
                f"❌ Country **'{country}'** was not found in the global dataset!",
                ephemeral=True
            )
            return
        chosen_key = clean_c
    else:
        chosen_key = random.choice(list(COUNTRY_DATA.keys()))

    lat, lon, official_name = COUNTRY_DATA[chosen_key]

    reward_pieces = []
    if role:
        reward_pieces.append(role.mention)
    if reward_text:
        reward_pieces.append(reward_text)

    reward_output = f"\n**Reward:** {' '.join(reward_pieces)}" if reward_pieces else ""
    if required_role:
        reward_output += f"\n**Required Role:** {required_role.mention}"

    embed = discord.Embed(
        title="🌍 Guess The Mystery Country!",
        description=(
            f"**Created by:** {interaction.user.mention}{reward_output}\n\n"
            "*No guesses yet!*"
        ),
        color=discord.Color.teal()
    )
    if hasattr(interaction.user, "display_avatar"):
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

    embed_msg = await target_channel.send(embed=embed)

    active_codes[target_channel.id] = {
        "code": chosen_key,
        "accepted_answers": [chosen_key, official_name.lower()],
        "target_coords": (lat, lon),
        "target_display": official_name,
        "ready": True,
        "role_id": role.id if role else None,
        "reward_text": reward_text,
        "type": "country",
        "start_time": time.time(),
        "troll_target": None,
        "creator_id": interaction.user.id,
        "required_role_id": required_role.id if required_role else None,
        "country_embed_id": embed_msg.id,
        "country_guesses": [],
    }

    await interaction.followup.send(f"✅ Mystery country challenge started in {target_channel.mention}!", ephemeral=True)


@bot.tree.command(name="wordle", description="Creates a custom Wordle game challenge.")
@app_commands.describe(
    word="The secret word for players to guess",
    role="Optional role reward",
    reward_text="Optional custom text description for the reward",
    required_role="Optional role required to guess in this Wordle",
    channel="Target channel"
)
async def wordle_slash(
    interaction: discord.Interaction,
    word: str,
    role: discord.Role | None = None,
    reward_text: str | None = None,
    required_role: discord.Role | None = None,
    channel: discord.TextChannel | None = None
):
    await interaction.response.defer(ephemeral=True)

    if interaction.guild and interaction.guild.id in blacklisted_servers:
        await interaction.followup.send("🚫 This server is blacklisted from using bot commands!", ephemeral=True)
        return

    if interaction.user.id in blacklisted_users:
        await interaction.followup.send("🚫 You are blacklisted from using bot commands!", ephemeral=True)
        return

    if not user_can_manage_codes(interaction.user, interaction.guild):
        await interaction.followup.send("❌ You do not have permission to create Wordles!", ephemeral=True)
        return

    clean_word = word.strip().lower()
    if not clean_word.isalpha():
        await interaction.followup.send("❌ Secret word can only contain alphabetic letters!", ephemeral=True)
        return

    if len(clean_word) < 3 or len(clean_word) > 10:
        await interaction.followup.send("❌ Secret word length must be between 3 and 10 letters!", ephemeral=True)
        return

    target_channel = channel or interaction.channel
    if not isinstance(target_channel, (discord.TextChannel, discord.Thread, discord.DMChannel)):
        await interaction.followup.send("❌ Invalid channel destination!", ephemeral=True)
        return

    await interaction.followup.send(f"✅ Wordle challenge created in {target_channel.mention}!", ephemeral=True)

    await process_wordle_creation(
        target_channel,
        clean_word,
        interaction.user,
        reward_role=role,
        reward_text=reward_text,
        required_role=required_role
    )


@bot.tree.command(name="mock", description="Sends a message as the bot with optional text and images (Bot Admin Only)")
@app_commands.describe(
    message="The text content for the bot to send",
    media="Optional image or file attachment",
    channel="The channel to post in"
)
async def mock_slash(
    interaction: discord.Interaction,
    message: str | None = None,
    media: discord.Attachment | None = None,
    channel: discord.TextChannel | None = None
):
    await interaction.response.defer(ephemeral=True)

    if interaction.guild and interaction.guild.id in blacklisted_servers:
        await interaction.followup.send("🚫 This server is blacklisted from using bot commands!", ephemeral=True)
        return

    if interaction.user.id not in ADMIN_USER_IDS:
        await interaction.followup.send("❌ You do not have permission to use this command!", ephemeral=True)
        return

    if interaction.user.id in blacklisted_users:
        await interaction.followup.send("🚫 You are blacklisted from using bot commands!", ephemeral=True)
        return

    if not message and not media:
        await interaction.followup.send("❌ You must provide either a message or media to send!", ephemeral=True)
        return

    target_channel = channel or interaction.channel
    if not isinstance(target_channel, (discord.TextChannel, discord.Thread, discord.DMChannel)):
        await interaction.followup.send("❌ Invalid target channel!", ephemeral=True)
        return

    file_to_send = None
    if media:
        file_to_send = await media.to_file()

    try:
        if file_to_send and message:
            await target_channel.send(content=message, file=file_to_send)
        elif file_to_send:
            await target_channel.send(file=file_to_send)
        else:
            await target_channel.send(content=message)

        await interaction.followup.send(f"✅ Mock message successfully sent to {target_channel.mention}!", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send(f"❌ I lack permissions to send messages in {target_channel.mention}.", ephemeral=True)


@bot.tree.command(name="leaderboard", description="Shows the fastest solved codes and users with the most claimed codes.")
async def leaderboard_slash(interaction: discord.Interaction):
    await interaction.response.defer()

    if interaction.guild and interaction.guild.id in blacklisted_servers:
        await interaction.followup.send("🚫 This server is blacklisted from using bot commands!", ephemeral=True)
        return

    if not leaderboard_data:
        await interaction.followup.send("📊 No codes have been solved yet, so the leaderboard is empty!")
        return

    most_solved = sorted(
        leaderboard_data.values(),
        key=lambda x: x.get("total_solved", 0),
        reverse=True
    )[:5]

    fastest_solves = sorted(
        [x for x in leaderboard_data.values() if x.get("fastest_time", 999999.0) < 999999.0],
        key=lambda x: x.get("fastest_time", 999999.0)
    )[:5]

    embed = discord.Embed(
        title="🏆 Code Challenge Leaderboard",
        description="Top performers in speed and total claims!",
        color=discord.Color.gold()
    )

    solved_lines = []
    for idx, entry in enumerate(most_solved, 1):
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"`#{idx}`"
        solved_lines.append(f"{medal} **{entry['username']}** — **{entry['total_solved']}** codes")
    
    embed.add_field(
        name="🥇 Most Codes Claimed",
        value="\n".join(solved_lines) if solved_lines else "No data yet.",
        inline=False
    )

    fastest_lines = []
    for idx, entry in enumerate(fastest_solves, 1):
        medal = "⚡" if idx == 1 else f"`#{idx}`"
        fastest_lines.append(f"{medal} **{entry['username']}** — **{entry['fastest_time']}s**")

    embed.add_field(
        name="⚡ Fastest Solve Times",
        value="\n".join(fastest_lines) if fastest_lines else "No data yet.",
        inline=False
    )

    if hasattr(interaction.user, "display_avatar"):
        embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)

    await interaction.followup.send(embed=embed)


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
    await interaction.response.defer(ephemeral=True)

    if interaction.guild and interaction.guild.id in blacklisted_servers:
        await interaction.followup.send("🚫 This server is blacklisted from using bot commands!", ephemeral=True)
        return

    if interaction.user.id not in ADMIN_USER_IDS:
        await interaction.followup.send("❌ You do not have permission to use this command!", ephemeral=True)
        return

    if interaction.user.id in blacklisted_users:
        await interaction.followup.send("🚫 You are blacklisted from using bot commands!", ephemeral=True)
        return

    target_channel = channel or interaction.channel
    if not isinstance(target_channel, (discord.TextChannel, discord.Thread, discord.DMChannel)):
        await interaction.followup.send("❌ Invalid target channel!", ephemeral=True)
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
        await interaction.followup.send(f"✅ Announcement sent to {target_channel.mention}!", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send(f"❌ I don't have permission to send messages in {target_channel.mention}.", ephemeral=True)


@bot.tree.command(name="showanswer", description="Shows the answers for all active codes, riddles, wordles, and countries (Bot Admin Only)")
async def showanswer_slash(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if interaction.guild and interaction.guild.id in blacklisted_servers:
        await interaction.followup.send("🚫 This server is blacklisted from using bot commands!", ephemeral=True)
        return

    if interaction.user.id not in ADMIN_USER_IDS:
        await interaction.followup.send("❌ You do not have permission to use this command!", ephemeral=True)
        return

    if not active_codes:
        await interaction.followup.send("📋 There are currently no active codes or riddles running.", ephemeral=True)
        return

    lines = []
    for channel_id, data in active_codes.items():
        channel = bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await bot.fetch_channel(channel_id)
            except Exception:
                channel = None

        channel_mention = channel.mention if channel else f"Channel ID: {channel_id}"
        challenge_type = data.get("type", "code").capitalize()
        accepted_list = data.get("accepted_answers", [data.get("code", "Unknown")])
        answers_str = " / ".join([f"`{a}`" for a in accepted_list])
        status = "Ready" if data.get("ready", True) else "Generating..."

        lines.append(f"• **{challenge_type}** in {channel_mention}\n  ↳ Answer(s): {answers_str} ({status})")

    embed = discord.Embed(
        title="🔑 Active Challenge Answers",
        description="\n".join(lines),
        color=discord.Color.gold()
    )
    if hasattr(interaction.user, "display_avatar"):
        embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="antisnitcher", description="Creates a code challenge with a special anti-snitch trap (Bot Admin Only)")
@app_commands.describe(
    code="The secret code to type",
    speed="Speed of revealing the code sections",
    include_numbers="Whether to append random numbers at the end",
    show_sections="Show section count message",
    role="Optional role reward",
    reward_text="Optional custom text description for the reward",
    required_role="Optional role required to answer this code",
    channel="Target channel"
)
async def antisnitcher_slash(
    interaction: discord.Interaction, 
    code: str, 
    speed: float = 1.3,
    include_numbers: bool = False,
    show_sections: bool = False,
    role: discord.Role | None = None,
    reward_text: str | None = None,
    required_role: discord.Role | None = None,
    channel: discord.TextChannel | None = None
):
    await interaction.response.defer(ephemeral=True)

    if interaction.guild and interaction.guild.id in blacklisted_servers:
        await interaction.followup.send("🚫 This server is blacklisted from using bot commands!", ephemeral=True)
        return

    if interaction.user.id not in ADMIN_USER_IDS:
        await interaction.followup.send("❌ You do not have permission to use this command!", ephemeral=True)
        return

    target_channel = channel or interaction.channel
    if not isinstance(target_channel, (discord.TextChannel, discord.Thread, discord.DMChannel)):
        await interaction.followup.send("❌ Invalid channel destination!", ephemeral=True)
        return

    clean_code = code.strip()
    if not clean_code:
        await interaction.followup.send("❌ Code cannot be empty!", ephemeral=True)
        return

    random_digits = "".join(random.choices(string.digits, k=4)) if include_numbers else None
    troll_target_id = 1445161465983008780

    await interaction.followup.send(f"✅ Anti-snitcher code started in {target_channel.mention}!", ephemeral=True)

    sections = split_phrase(clean_code)
    await process_code_creation(
        target_channel, 
        clean_code, 
        sections, 
        interaction.user, 
        reward_role=role, 
        reward_text=reward_text,
        random_digits=random_digits,
        speed=speed,
        show_sections=show_sections,
        troll_target=troll_target_id,
        required_role=required_role
    )


@bot.tree.command(name="setcoderole", description="Sets role(s) allowed to create codes for this server.")
async def setcoderole_slash(
    interaction: discord.Interaction,
    role1: discord.Role,
    role2: discord.Role | None = None,
    role3: discord.Role | None = None,
    role4: discord.Role | None = None,
    role5: discord.Role | None = None
):
    await interaction.response.defer(ephemeral=True)

    if not interaction.guild:
        await interaction.followup.send("❌ This command can only be used inside a server!", ephemeral=True)
        return

    if interaction.guild.id in blacklisted_servers:
        await interaction.followup.send("🚫 This server is blacklisted from using bot commands!", ephemeral=True)
        return

    if not user_is_server_admin(interaction.user):
        await interaction.followup.send("❌ You need **Manage Server** or **Administrator** permissions!", ephemeral=True)
        return

    roles_list = [r for r in [role1, role2, role3, role4, role5] if r is not None]
    server_manager_roles[interaction.guild.id] = {role.id for role in roles_list}
    save_json_file(MANAGERS_FILE, {str(k): list(v) for k, v in server_manager_roles.items()})

    role_names = ", ".join([f"**{role.name}** (`ID: {role.id}`)" for role in roles_list])
    await interaction.followup.send(
        f"✅ Code Manager roles for **{interaction.guild.name}** set to: {role_names}!",
        ephemeral=True
    )


@bot.tree.command(name="givecodebypass", description="Grants code bypass permissions to a user (Bot Admin Only)")
async def givecodebypass(interaction: discord.Interaction, user: discord.User | discord.Member):
    await interaction.response.defer(ephemeral=True)

    if interaction.guild and interaction.guild.id in blacklisted_servers:
        await interaction.followup.send("🚫 This server is blacklisted from using bot commands!", ephemeral=True)
        return

    if interaction.user.id not in ADMIN_USER_IDS:
        await interaction.followup.send("❌ You do not have permission to use this command!", ephemeral=True)
        return

    if user.id in bypass_users:
        await interaction.followup.send(f"⚠️ {user.mention} already has code bypass permissions!", ephemeral=True)
        return

    bypass_users.add(user.id)
    save_json_file(BYPASS_FILE, list(bypass_users))

    await interaction.followup.send(f"🔓 Granted code bypass permissions to {user.mention}!", ephemeral=True)


@bot.tree.command(name="deletecodebypassperms", description="Removes code bypass permissions from a user or all users (Bot Admin Only)")
async def deletecodebypassperms(interaction: discord.Interaction, user: discord.User | discord.Member | None = None):
    await interaction.response.defer(ephemeral=True)

    if interaction.guild and interaction.guild.id in blacklisted_servers:
        await interaction.followup.send("🚫 This server is blacklisted from using bot commands!", ephemeral=True)
        return

    if interaction.user.id not in ADMIN_USER_IDS:
        await interaction.followup.send("❌ You do not have permission to use this command!", ephemeral=True)
        return

    if user:
        if user.id not in bypass_users:
            await interaction.followup.send(f"⚠️ {user.mention} does not have active code bypass permissions.", ephemeral=True)
            return
        
        bypass_users.remove(user.id)
        save_json_file(BYPASS_FILE, list(bypass_users))
        await interaction.followup.send(f"🛑 Removed code bypass permissions from {user.mention}!", ephemeral=True)
    else:
        if not bypass_users:
            await interaction.followup.send("⚠️ No users currently have code bypass permissions.", ephemeral=True)
            return

        count = len(bypass_users)
        bypass_users.clear()
        save_json_file(BYPASS_FILE, list(bypass_users))
        await interaction.followup.send(f"🛑 Removed code bypass permissions from all {count} user(s)!", ephemeral=True)


@bot.tree.command(name="createcode", description="Creates a standard or reward code embed.")
@app_commands.describe(
    code="The secret code to type",
    speed="Speed of revealing the code sections",
    include_numbers="Whether to append random numbers at the end",
    show_sections="Show section count message",
    role="Optional role reward",
    reward_text="Optional custom text description for the reward",
    required_role="Optional role required to answer this code",
    channel="Target channel"
)
async def createcode_slash(
    interaction: discord.Interaction, 
    code: str, 
    speed: float = 1.3,
    include_numbers: bool = False,
    show_sections: bool = False,
    role: discord.Role | None = None,
    reward_text: str | None = None,
    required_role: discord.Role | None = None,
    channel: discord.TextChannel | None = None
):
    await interaction.response.defer(ephemeral=True)

    if interaction.guild and interaction.guild.id in blacklisted_servers:
        await interaction.followup.send("🚫 This server is blacklisted from using bot commands!", ephemeral=True)
        return

    if interaction.user.id in blacklisted_users:
        await interaction.followup.send("🚫 You are blacklisted from using bot commands!", ephemeral=True)
        return

    if not user_can_manage_codes(interaction.user, interaction.guild):
        await interaction.followup.send("❌ You do not have permission to create codes!", ephemeral=True)
        return

    if role and interaction.guild:
        member = interaction.guild.get_member(interaction.user.id)
        if not member:
            try:
                member = await interaction.guild.fetch_member(interaction.user.id)
            except Exception:
                member = interaction.user

        if isinstance(member, discord.Member):
            if role >= member.top_role:
                await interaction.followup.send(
                    f"❌ You cannot use {role.mention} because it is higher than or equal to your highest role!",
                    ephemeral=True
                )
                return

        if interaction.guild.me and interaction.guild.me.top_role:
            if role >= interaction.guild.me.top_role:
                await interaction.followup.send(
                    f"❌ I cannot assign {role.mention} because it is higher than or equal to my highest role!",
                    ephemeral=True
                )
                return

    target_channel = channel or interaction.channel
    if not isinstance(target_channel, (discord.TextChannel, discord.Thread, discord.DMChannel)):
        await interaction.followup.send("❌ Invalid channel destination!", ephemeral=True)
        return

    clean_code = code.strip()

    if not clean_code:
        await interaction.followup.send("❌ Code cannot be empty!", ephemeral=True)
        return

    random_digits = "".join(random.choices(string.digits, k=4)) if include_numbers else None
    
    await interaction.followup.send(f"✅ Code creation started in {target_channel.mention}!", ephemeral=True)

    sections = split_phrase(clean_code)
    await process_code_creation(
        target_channel, 
        clean_code, 
        sections, 
        interaction.user, 
        reward_role=role, 
        reward_text=reward_text,
        random_digits=random_digits,
        speed=speed,
        show_sections=show_sections,
        troll_target=None,
        required_role=required_role
    )


@bot.tree.command(name="createriddle", description="Creates a standard or reward riddle challenge with up to 2 possible answers.")
@app_commands.describe(
    question="The riddle question",
    answer="The primary secret answer",
    answer2="Optional alternative second answer",
    role="Optional role reward",
    reward_text="Optional custom text description for the reward",
    required_role="Optional role required to answer this riddle",
    channel="Target channel"
)
async def createriddle_slash(
    interaction: discord.Interaction,
    question: str,
    answer: str,
    answer2: str | None = None,
    role: discord.Role | None = None,
    reward_text: str | None = None,
    required_role: discord.Role | None = None,
    channel: discord.TextChannel | None = None
):
    await interaction.response.defer(ephemeral=True)

    if interaction.guild and interaction.guild.id in blacklisted_servers:
        await interaction.followup.send("🚫 This server is blacklisted from using bot commands!", ephemeral=True)
        return

    if interaction.user.id in blacklisted_users:
        await interaction.followup.send("🚫 You are blacklisted from using bot commands!", ephemeral=True)
        return

    if not user_can_manage_codes(interaction.user, interaction.guild):
        await interaction.followup.send("❌ You do not have permission to create riddles!", ephemeral=True)
        return

    if role and interaction.guild:
        member = interaction.guild.get_member(interaction.user.id)
        if not member:
            try:
                member = await interaction.guild.fetch_member(interaction.user.id)
            except Exception:
                member = interaction.user

        if isinstance(member, discord.Member):
            if role >= member.top_role:
                await interaction.followup.send(
                    f"❌ You cannot use {role.mention} because it is higher than or equal to your highest role!",
                    ephemeral=True
                )
                return

        if interaction.guild.me and interaction.guild.me.top_role:
            if role >= interaction.guild.me.top_role:
                await interaction.followup.send(
                    f"❌ I cannot assign {role.mention} because it is higher than or equal to my highest role!",
                    ephemeral=True
                )
                return

    target_channel = channel or interaction.channel
    if not isinstance(target_channel, (discord.TextChannel, discord.Thread, discord.DMChannel)):
        await interaction.followup.send("❌ Invalid channel destination!", ephemeral=True)
        return

    clean_question = question.strip()
    clean_answer = answer.strip()
    clean_answer2 = answer2.strip() if answer2 else None

    if not clean_question or not clean_answer:
        await interaction.followup.send("❌ Question and primary answer cannot be empty!", ephemeral=True)
        return

    await interaction.followup.send(f"✅ Riddle created in {target_channel.mention}!", ephemeral=True)

    await process_riddle_creation(
        target_channel, 
        clean_question, 
        clean_answer, 
        clean_answer2,
        interaction.user, 
        reward_role=role, 
        reward_text=reward_text,
        required_role=required_role
    )


# --- PREFIX COMMANDS (!cmds) ---
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
            "`/wordle` - Creates a custom interactive Wordle game in chat.\n"
            "`/guessthemysterycountry` - Starts a mystery country distance game.\n"
            "`/leaderboard` - Displays fast solve times and top code solvers.\n"
            "`/setcoderole` - Sets roles allowed to manage codes for this server."
        ),
        inline=False
    )

    if hasattr(ctx.author, "display_avatar"):
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)

    await ctx.send(embed=embed)


# --- ADMIN PREFIX COMMANDS (HIDDEN FROM !cmds) ---
@bot.command(name="admincmds")
@is_not_blacklisted()
@is_admin_or_owner()
async def admincmds_command(ctx):
    embed = discord.Embed(
        title="🛡 Bot Admin Commands List",
        description="Here are all available commands for bot administrators:",
        color=discord.Color.dark_purple()
    )

    embed.add_field(
        name="⚙ Admin Slash Commands",
        value=(
            "`/antisnitcher` - Creates an anti-snitcher code challenge.\n"
            "`/showanswer` - Shows answers for all active codes/riddles/wordles/countries.\n"
            "`/announcement` - Sends an announcement embed.\n"
            "`/mock` - Sends a custom message/image as the bot.\n"
            "`/givecodebypass` - Grants code bypass permissions.\n"
            "`/deletecodebypassperms` - Removes code bypass permissions."
        ),
        inline=False
    )

    embed.add_field(
        name="🚫 Admin Prefix Commands",
        value=(
            "`!blacklist @user` - Blacklists a user from bot commands.\n"
            "`!unblacklist @user` - Removes a user from the blacklist.\n"
            "`!blacklistlist` - Views all currently blacklisted users.\n"
            "`!blacklistserver <id>` - Blacklists an entire server by ID.\n"
            "`!unblacklistserver <id>` - Removes a server from the blacklist.\n"
            "`!admincmds` - Displays this admin command list."
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
    save_json_file(BLACKLIST_FILE, list(blacklisted_users))
    await ctx.send(f"🚫 {user.mention} has been blacklisted!")


@bot.command()
@is_not_blacklisted()
@is_admin_or_owner()
async def unblacklist(ctx, user: discord.User | discord.Member):
    if user.id not in blacklisted_users:
        await ctx.send(f"⚠️ {user.mention} is not blacklisted.", delete_after=5)
        return
    blacklisted_users.remove(user.id)
    save_json_file(BLACKLIST_FILE, list(blacklisted_users))
    await ctx.send(f"✅ {user.mention} has been removed from the blacklist!")


@bot.command(name="blacklistlist")
@is_not_blacklisted()
@is_admin_or_owner()
async def blacklistlist_command(ctx):
    if not blacklisted_users:
        await ctx.send("📋 There are currently no blacklisted users.")
        return

    user_lines = []
    for user_id in blacklisted_users:
        user_lines.append(f"• <@!{user_id}> (`ID: {user_id}`)")

    embed = discord.Embed(
        title="🚫 Blacklisted Users List",
        description="\n".join(user_lines),
        color=discord.Color.red()
    )
    if hasattr(ctx.author, "display_avatar"):
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)

    await ctx.send(embed=embed)


@bot.command(name="blacklistserver")
@is_admin_or_owner()
async def blacklistserver_command(ctx, guild_id: int):
    if guild_id in blacklisted_servers:
        await ctx.send(f"⚠️ Server ID `{guild_id}` is already blacklisted.", delete_after=5)
        return
    
    blacklisted_servers.add(guild_id)
    save_json_file(SERVERS_BLACKLIST_FILE, list(blacklisted_servers))
    await ctx.send(f"🚫 Server with ID `{guild_id}` has been blacklisted from using the bot!")


@bot.command(name="unblacklistserver")
@is_admin_or_owner()
async def unblacklistserver_command(ctx, guild_id: int):
    if guild_id not in blacklisted_servers:
        await ctx.send(f"⚠️ Server ID `{guild_id}` is not blacklisted.", delete_after=5)
        return
    
    blacklisted_servers.remove(guild_id)
    save_json_file(SERVERS_BLACKLIST_FILE, list(blacklisted_servers))
    await ctx.send(f"✅ Server with ID `{guild_id}` has been removed from the server blacklist!")


# --- MESSAGE LISTENER FOR CODE SOLVING & LEADERBOARD UPDATES ---
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.guild and message.guild.id in blacklisted_servers:
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
            creator_id = code_data.get("creator_id")
            
            # Allow BOT ADMINS to solve their own codes/riddles/games
            if creator_id and message.author.id == creator_id and message.author.id not in ADMIN_USER_IDS:
                return

            accepted_answers = code_data.get("accepted_answers", [code_data["code"].lower()])
            challenge_type = code_data.get("type", "code")
            troll_target = code_data.get("troll_target")

            if troll_target and message.author.id == troll_target and msg_clean in accepted_answers:
                del active_codes[channel_id]
                await message.channel.send(f"Snitcher detected. Get out! {message.author.mention}")
                return
            
            has_role_bypass = False
            if isinstance(message.author, discord.Member):
                has_role_bypass = any(role.name == BYPASS_ROLE_NAME for role in message.author.roles)

            has_standalone_bypass = message.author.id in bypass_users
            has_bypass = has_role_bypass or has_standalone_bypass

            required_role_id = code_data.get("required_role_id")
            has_required_role = True
            if required_role_id and not has_bypass and message.guild:
                if isinstance(message.author, discord.Member):
                    has_required_role = any(role.id == required_role_id for role in message.author.roles)
                else:
                    has_required_role = False

            if not has_required_role:
                return

            target_code = accepted_answers[0]

            # --- COUNTRY GUESSING GAME LOGIC ---
            if challenge_type == "country":
                if msg_clean in COUNTRY_DATA:
                    guessed_lat, guessed_lon, guessed_name = COUNTRY_DATA[msg_clean]
                    target_lat, target_lon = code_data["target_coords"]
                    
                    dist_km = calculate_haversine_distance(guessed_lat, guessed_lon, target_lat, target_lon)
                    temp_status, emoji = get_temperature_feedback(dist_km)
                    
                    guess_entry = f"{emoji} **{guessed_name}** — **{dist_km:,} km** away ({temp_status}) [{message.author.mention}]"
                    code_data["country_guesses"].append(guess_entry)

                    embed_id = code_data.get("country_embed_id")
                    if embed_id:
                        try:
                            embed_msg = await message.channel.fetch_message(embed_id)
                            creator_user = bot.get_user(creator_id)
                            creator_mention = creator_user.mention if creator_user else "Unknown"

                            role_id = code_data.get("role_id")
                            custom_reward_text = code_data.get("reward_text")
                            reward_pieces = []
                            if role_id and message.guild:
                                r_obj = message.guild.get_role(role_id)
                                if r_obj:
                                    reward_pieces.append(r_obj.mention)
                            if custom_reward_text:
                                reward_pieces.append(custom_reward_text)
                            
                            reward_out = f"\n**Reward:** {' '.join(reward_pieces)}" if reward_pieces else ""
                            req_r_id = code_data.get("required_role_id")
                            if req_r_id and message.guild:
                                r_req = message.guild.get_role(req_r_id)
                                if r_req:
                                    reward_out += f"\n**Required Role:** {r_req.mention}"

                            guesses_formatted = "\n".join(code_data["country_guesses"][-10:])

                            new_embed = discord.Embed(
                                title="🌍 Guess The Mystery Country!",
                                description=(
                                    f"**Created by:** {creator_mention}{reward_out}\n\n"
                                    f"{guesses_formatted}"
                                ),
                                color=discord.Color.teal(),
                            )
                            if creator_user and hasattr(creator_user, "display_avatar"):
                                new_embed.set_thumbnail(url=creator_user.display_avatar.url)

                            await embed_msg.edit(embed=new_embed)
                        except Exception as e:
                            print(f"Error updating Country embed: {e}")

                    if dist_km == 0 or msg_clean in accepted_answers or has_bypass:
                        start_time = code_data.get("start_time") or time.time()
                        elapsed_seconds = round(time.time() - start_time, 2)
                        role_id = code_data.get("role_id")
                        custom_reward_text = code_data.get("reward_text")
                        target_display = code_data.get("target_display", target_code.capitalize())

                        del active_codes[channel_id]

                        user_id_str = str(message.author.id)
                        if user_id_str not in leaderboard_data:
                            leaderboard_data[user_id_str] = {
                                "username": message.author.display_name,
                                "total_solved": 0,
                                "fastest_time": 999999.0
                            }
                        leaderboard_data[user_id_str]["username"] = message.author.display_name
                        leaderboard_data[user_id_str]["total_solved"] += 1
                        if elapsed_seconds < leaderboard_data[user_id_str]["fastest_time"]:
                            leaderboard_data[user_id_str]["fastest_time"] = elapsed_seconds
                        save_leaderboard()

                        reward_desc = None
                        if custom_reward_text:
                            reward_desc = custom_reward_text
                        elif role_id and message.guild:
                            role_obj = message.guild.get_role(role_id)
                            if role_obj:
                                reward_desc = role_obj.name

                        if role_id and isinstance(message.author, discord.Member) and message.guild:
                            role = message.guild.get_role(role_id)
                            if role:
                                try:
                                    await message.author.add_roles(role)
                                except discord.Forbidden:
                                    pass

                        if reward_desc:
                            embed_desc = f"🎉 {message.author.mention} correctly guessed **{target_display}** for **{reward_desc}** in **{elapsed_seconds}** seconds!"
                        else:
                            embed_desc = f"🎉 {message.author.mention} correctly guessed **{target_display}** in **{elapsed_seconds}** seconds!"

                        success_embed = discord.Embed(description=embed_desc, color=discord.Color.green())
                        await message.channel.send(embed=success_embed)
                return

            # --- WORDLE GAME LOGIC ---
            if challenge_type == "wordle":
                if len(msg_clean) == len(target_code) and msg_clean.isalpha():
                    feedback_line = calculate_wordle_feedback(msg_clean, target_code)
                    code_data["wordle_guesses"].append(f"{feedback_line} ({message.author.mention})")
                    
                    embed_id = code_data.get("wordle_embed_id")
                    if embed_id:
                        try:
                            embed_msg = await message.channel.fetch_message(embed_id)
                            creator_user = bot.get_user(creator_id)
                            creator_mention = creator_user.mention if creator_user else "Unknown"

                            role_id = code_data.get("role_id")
                            custom_reward_text = code_data.get("reward_text")
                            reward_pieces = []
                            if role_id and message.guild:
                                r_obj = message.guild.get_role(role_id)
                                if r_obj:
                                    reward_pieces.append(r_obj.mention)
                            if custom_reward_text:
                                reward_pieces.append(custom_reward_text)
                            
                            reward_out = f"\n**Reward:** {' '.join(reward_pieces)}" if reward_pieces else ""
                            req_r_id = code_data.get("required_role_id")
                            if req_r_id and message.guild:
                                r_req = message.guild.get_role(req_r_id)
                                if r_req:
                                    reward_out += f"\n**Required Role:** {r_req.mention}"

                            guesses_formatted = "\n".join(code_data["wordle_guesses"][-10:])
                            
                            new_embed = discord.Embed(
                                title="🟩 Wordle Challenge!",
                                description=(
                                    f"**Created by:** {creator_mention}{reward_out}\n\n"
                                    f"{guesses_formatted}"
                                ),
                                color=discord.Color.green(),
                            )
                            if creator_user and hasattr(creator_user, "display_avatar"):
                                new_embed.set_thumbnail(url=creator_user.display_avatar.url)
                            
                            await embed_msg.edit(embed=new_embed)
                        except Exception as e:
                            print(f"Error updating Wordle embed: {e}")

                    if msg_clean == target_code or has_bypass:
                        start_time = code_data.get("start_time") or time.time()
                        elapsed_seconds = round(time.time() - start_time, 2)
                        role_id = code_data.get("role_id")
                        custom_reward_text = code_data.get("reward_text")

                        del active_codes[channel_id]

                        user_id_str = str(message.author.id)
                        if user_id_str not in leaderboard_data:
                            leaderboard_data[user_id_str] = {
                                "username": message.author.display_name,
                                "total_solved": 0,
                                "fastest_time": 999999.0
                            }
                        leaderboard_data[user_id_str]["username"] = message.author.display_name
                        leaderboard_data[user_id_str]["total_solved"] += 1
                        if elapsed_seconds < leaderboard_data[user_id_str]["fastest_time"]:
                            leaderboard_data[user_id_str]["fastest_time"] = elapsed_seconds
                        save_leaderboard()

                        reward_desc = None
                        if custom_reward_text:
                            reward_desc = custom_reward_text
                        elif role_id and message.guild:
                            role_obj = message.guild.get_role(role_id)
                            if role_obj:
                                reward_desc = role_obj.name

                        if role_id and isinstance(message.author, discord.Member) and message.guild:
                            role = message.guild.get_role(role_id)
                            if role:
                                try:
                                    await message.author.add_roles(role)
                                except discord.Forbidden:
                                    pass

                        if reward_desc:
                            embed_desc = f"{message.author.mention} solved the wordle for **{reward_desc}** in **{elapsed_seconds}** seconds!"
                        else:
                            embed_desc = f"{message.author.mention} solved the wordle in **{elapsed_seconds}** seconds!"

                        success_embed = discord.Embed(description=embed_desc, color=discord.Color.green())
                        await message.channel.send(embed=success_embed)
                return

            # --- STANDARD CODE & RIDDLE LOGIC ---
            is_exact_match = msg_clean in accepted_answers

            if is_exact_match or has_bypass:
                start_time = code_data.get("start_time") or time.time()
                elapsed_seconds = round(time.time() - start_time, 2)

                role_id = code_data.get("role_id")
                custom_reward_text = code_data.get("reward_text")

                del active_codes[channel_id]

                user_id_str = str(message.author.id)
                if user_id_str not in leaderboard_data:
                    leaderboard_data[user_id_str] = {
                        "username": message.author.display_name,
                        "total_solved": 0,
                        "fastest_time": 999999.0
                    }
                
                leaderboard_data[user_id_str]["username"] = message.author.display_name
                leaderboard_data[user_id_str]["total_solved"] += 1

                if elapsed_seconds < leaderboard_data[user_id_str]["fastest_time"]:
                    leaderboard_data[user_id_str]["fastest_time"] = elapsed_seconds

                save_leaderboard()

                reward_desc = None
                if custom_reward_text:
                    reward_desc = custom_reward_text
                elif role_id and message.guild:
                    role_obj = message.guild.get_role(role_id)
                    if role_obj:
                        reward_desc = role_obj.name

                if role_id and isinstance(message.author, discord.Member) and message.guild:
                    role = message.guild.get_role(role_id)
                    if role:
                        try:
                            await message.author.add_roles(role)
                        except discord.Forbidden:
                            pass

                label_text = "riddle" if challenge_type == "riddle" else "code"
                if reward_desc:
                    embed_desc = f"{message.author.mention} redeemed the {label_text} for **{reward_desc}** in **{elapsed_seconds}** seconds!"
                else:
                    embed_desc = f"{message.author.mention} redeemed the {label_text} in **{elapsed_seconds}** seconds!"

                success_embed = discord.Embed(description=embed_desc, color=discord.Color.green())
                await message.channel.send(embed=success_embed)
            else:
                has_keyword_match = False
                is_close_typo = False

                for target_code in accepted_answers:
                    target_words = set(target_code.split())
                    significant_target_words = {w for w in target_words if len(w) > 2}
                    
                    if any(word in msg_clean for word in significant_target_words):
                        has_keyword_match = True
                        break

                    target_len = len(target_code)
                    msg_len = len(msg_clean)
                    
                    if msg_len >= (target_len / 2) and msg_len <= (target_len + 5):
                        if target_len <= 4:
                            max_allowed_diffs = 1
                        elif target_len <= 8:
                            max_allowed_diffs = 2
                        else:
                            max_allowed_diffs = 3

                        matcher = SequenceMatcher(None, msg_clean, target_code)
                        diffs = target_len - sum(block.size for block in matcher.get_matching_blocks())
                        if diffs <= max_allowed_diffs:
                            is_close_typo = True
                            break

                if has_keyword_match or is_close_typo:
                    try:
                        await message.add_reaction("👀")
                    except discord.HTTPException:
                        pass


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
            print(f"Unexpected connection error: {e}", flush=True)
            await asyncio.sleep(10)
        finally:
            try:
                if not bot.is_closed():
                    await bot.close()
            except Exception:
                pass
            await asyncio.sleep(5)


if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())

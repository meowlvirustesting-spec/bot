import os
import re
import json
import asyncio
import threading
import time
import random
import string
import wordninja
from flask import Flask
import discord
from discord.ext import commands
from discord import app_commands

# --- CONFIGURATION ---
BYPASS_ROLE_NAME = "Code bypass (OVERPOWERED)"  # Permanent correct answers for role holders
ANNOUNCEMENT_IMAGE_URL = "https://cdn.discordapp.com/attachments/1546415351049228410/1546415372213690368/Untitled106_20260907020000.png?ex=6a9fb30b&is=6a9e618b&hm=65715670c974b258a8cff733a2f40ac6fc99801dfffe891df56e3fa07de32b3f&"

# Global Bot Admins (Override permissions on any server)
ADMIN_USER_IDS = {1508960806547623946, 1453702313658159357}

# Dynamic In-Memory States
active_bypass_code = None        # Holds the custom bypass code set by an admin
active_bypass_max_claims = 1     # Total number of unique users allowed to redeem the DLC code
redeemed_users = set()           # Set of user IDs who have already claimed the current active DLC code
bypass_users = {}                # Dictionary mapping User ID -> Remaining Bypass Uses (Always 1 per person)

# Per-Server Configuration: Guild ID -> Set of Role IDs
server_manager_roles = {}

# --- PERSISTENT BLACKLIST LOGIC ---
BLACKLIST_FILE = "blacklist.json"


def load_blacklist() -> set[int]:
    if os.path.exists(BLACKLIST_FILE):
        try:
            with open(BLACKLIST_FILE, "r") as f:
                data = json.load(f)
                return set(data)
        except Exception as e:
            print(f"Error loading blacklist file: {e}")
            return set()
    return set()


def save_blacklist(blacklist_set: set[int]):
    try:
        with open(BLACKLIST_FILE, "w") as f:
            json.dump(list(blacklist_set), f)
    except Exception as e:
        print(f"Error saving blacklist file: {e}")


blacklisted_users = load_blacklist()

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
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")


# --- PERMISSION CHECKS ---
def is_not_blacklisted():
    async def predicate(ctx):
        return ctx.author.id not in blacklisted_users
    return commands.check(predicate)


def is_admin_or_owner():
    async def predicate(ctx):
        return ctx.author.id in ADMIN_USER_IDS
    return commands.check(predicate)


def is_server_admin():
    async def predicate(ctx):
        if ctx.author.id in ADMIN_USER_IDS:
            return True
        if isinstance(ctx.author, discord.Member):
            return ctx.author.guild_permissions.manage_guild or ctx.author.guild_permissions.administrator
        return False
    return commands.check(predicate)


def can_manage_codes():
    async def predicate(ctx):
        if ctx.author.id in ADMIN_USER_IDS:
            return True
        if isinstance(ctx.author, discord.Member):
            if ctx.author.guild_permissions.administrator:
                return True
            assigned_role_ids = server_manager_roles.get(ctx.guild.id, set())
            if assigned_role_ids:
                return any(role.id in assigned_role_ids for role in ctx.author.roles)
        return False
    return commands.check(predicate)


# --- 3. DYNAMIC WORD & CHUNK SPLITTING ---
def split_phrase(text: str) -> list[str]:
    if " " in text:
        return text.split()

    sections = wordninja.split(text)
    if sections:
        return sections
    
    chunk_size = max(1, len(text) // 3)
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


# --- 4. CODE & RIDDLE CREATION HELPERS ---
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
        "type": "code",
        "start_time": None,
    }

    embed = discord.Embed(
        title="Creating Code...",
        description=f"**Created by:** {creator.mention}\n\n*Generating Code...*",
        color=discord.Color.blue(),
    )
    embed.set_thumbnail(url=creator.display_avatar.url)
    message = await target_channel.send(embed=embed)

    displayed_text = ""
    has_spaces = " " in clean_code

    async with target_channel.typing():
        for section in sections:
            await asyncio.sleep(1.3)
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
    embed.description = (
        f"**Created by:** {creator.mention}\n\n"
        f"**USE CODE:** {clean_code}{reward_text}\n\n"
        f"Type the full code to claim!"
    )
    embed.color = discord.Color.green()
    await message.edit(embed=embed)


async def process_riddle_creation(
    target_channel: discord.TextChannel,
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
    embed.set_thumbnail(url=creator.display_avatar.url)
    await target_channel.send(embed=embed)


# --- 5. SLASH COMMANDS ---
@bot.tree.command(name="generatedlc", description="Generates a random DLC code with configured max claims (Bot Admin Only)")
@app_commands.describe(
    max_claims="Maximum total number of people who can redeem this code (default: 1)"
)
async def generatedlc(interaction: discord.Interaction, max_claims: int = 1):
    global active_bypass_code, active_bypass_max_claims, redeemed_users

    if interaction.user.id not in ADMIN_USER_IDS:
        await interaction.response.send_message("❌ You do not have permission to use this command!", ephemeral=True)
        return

    if interaction.user.id in blacklisted_users:
        await interaction.response.send_message("🚫 You are blacklisted from using bot commands!", ephemeral=True)
        return

    if max_claims < 1:
        await interaction.response.send_message("❌ Max claims must be at least 1!", ephemeral=True)
        return

    letters = ''.join(random.choices(string.ascii_uppercase, k=4))
    numbers = ''.join(random.choices(string.digits, k=4))
    dlc_code = f"BRADAR-{letters}-{numbers}"

    # Reset redemption history for the new code
    active_bypass_code = dlc_code.lower()
    active_bypass_max_claims = max_claims
    redeemed_users.clear()

    claim_text = "1 person" if max_claims == 1 else f"{max_claims} people"

    await interaction.response.send_message(
        f"🎁 **Generated DLC Code:** `{dlc_code}`\n⚙️ **Bypass Uses Per Person:** 1 use\n👥 **Max Claims:** {claim_text}\n✅ *This code is now active!*", 
        ephemeral=True
    )


@bot.tree.command(name="deletecodebypassperms", description="Removes code bypass permissions from a specified user or all holders (Bot Admin Only)")
@app_commands.describe(user="The user to remove bypass permissions from (leave empty to clear all)")
async def deletecodebypassperms(interaction: discord.Interaction, user: discord.User | discord.Member | None = None):
    if interaction.user.id not in ADMIN_USER_IDS:
        await interaction.response.send_message("❌ You do not have permission to use this command!", ephemeral=True)
        return

    if user:
        if user.id not in bypass_users:
            await interaction.response.send_message(f"⚠️ {user.mention} does not currently have active code bypass permissions.", ephemeral=True)
            return
        
        del bypass_users[user.id]
        await interaction.response.send_message(f"🛑 Successfully removed code bypass permissions from {user.mention}!", ephemeral=True)
    else:
        if not bypass_users:
            await interaction.response.send_message("⚠️ No users currently have code bypass permissions.", ephemeral=True)
            return

        count = len(bypass_users)
        bypass_users.clear()
        await interaction.response.send_message(f"🛑 Successfully removed code bypass permissions from all {count} user(s)!", ephemeral=True)


# --- 6. COMMANDS ---
@bot.command()
@is_server_admin()
async def setcodemanagerrole(ctx, roles: commands.Greedy[discord.Role]):
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound):
        pass

    if not roles:
        await ctx.send("❌ **Usage:** `!setcodemanagerrole @Role1 @Role2 ...`", delete_after=5)
        return

    server_manager_roles[ctx.guild.id] = {role.id for role in roles}

    role_names = ", ".join([f"**{role.name}** (`ID: {role.id}`)" for role in roles])
    await ctx.send(
        f"✅ Code Manager roles for **{ctx.guild.name}** set to: {role_names}!",
        delete_after=7,
        allowed_mentions=discord.AllowedMentions.none()
    )


@setcodemanagerrole.error
async def setcodemanagerrole_error(ctx, error):
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound):
        pass

    if isinstance(error, commands.CheckFailure):
        await ctx.send("❌ You need the **Manage Server** or **Administrator** permission to set manager roles!", delete_after=5)


@bot.command()
@is_not_blacklisted()
@can_manage_codes()
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
@can_manage_codes()
async def createrolecode(ctx, role: discord.Role, *, args: str = ""):
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound):
        pass

    if role.position >= ctx.author.top_role.position and ctx.author.id not in ADMIN_USER_IDS:
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
@can_manage_codes()
async def createriddle(ctx, *, rest: str = ""):
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound):
        pass

    target_channel = ctx.channel
    clean_rest = rest

    if ctx.message.channel_mentions:
        target_channel = ctx.message.channel_mentions[0]
        clean_rest = re.sub(r"<#\d+>", "", clean_rest).strip()

    matches = re.findall(r'"([^"]*)"', clean_rest)

    if len(matches) < 2:
        await ctx.send(
            "❌ **Usage:** `!createriddle [#channel] \"Question\" \"Answer\"`",
            delete_after=5,
        )
        return

    question = matches[0]
    answer = matches[1]

    await process_riddle_creation(target_channel, question, answer, ctx.author)


@bot.command()
@is_not_blacklisted()
@can_manage_codes()
async def createroleriddle(ctx, role: discord.Role, *, rest: str = ""):
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound):
        pass

    if role.position >= ctx.author.top_role.position and ctx.author.id not in ADMIN_USER_IDS:
        await ctx.send(
            f"❌ {ctx.author.mention}, you cannot create a riddle for {role.mention} because it is higher than or equal to your role!",
            delete_after=5,
        )
        return

    if role.position >= ctx.guild.me.top_role.position:
        await ctx.send(
            f"❌ {ctx.author.mention}, I cannot assign {role.mention} because it is higher than my highest role!",
            delete_after=5,
        )
        return

    target_channel = ctx.channel
    clean_rest = rest

    if ctx.message.channel_mentions:
        target_channel = ctx.message.channel_mentions[0]
        clean_rest = re.sub(r"<#\d+>", "", clean_rest).strip()

    matches = re.findall(r'"([^"]*)"', clean_rest)

    if len(matches) < 2:
        await ctx.send(
            "❌ **Usage:** `!createroleriddle @Role [#channel] \"Question\" \"Answer\"`",
            delete_after=5,
        )
        return

    question = matches[0]
    answer = matches[1]

    await process_riddle_creation(target_channel, question, answer, ctx.author, reward_role=role)


@createcode.error
@createrolecode.error
@createriddle.error
@createroleriddle.error
async def code_command_error(ctx, error):
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound):
        pass

    if isinstance(error, commands.CheckFailure):
        role_ids = server_manager_roles.get(ctx.guild.id, set())
        roles = [ctx.guild.get_role(rid) for rid in role_ids if ctx.guild.get_role(rid)]
        
        if roles:
            role_text = " or ".join([f"**{r.name}**" for r in roles])
        else:
            role_text = "a configured Code Manager role (or Server Admin permissions)"

        await ctx.send(
            f"❌ {ctx.author.mention}, you need {role_text} to use this command!",
            delete_after=5,
            allowed_mentions=discord.AllowedMentions.none()
        )


@bot.command()
@is_not_blacklisted()
@is_admin_or_owner()
async def blacklist(ctx, user: discord.User | discord.Member):
    if user.id in blacklisted_users:
        await ctx.send(f"⚠️ {user.mention} is already blacklisted.", delete_after=5)
        return
    blacklisted_users.add(user.id)
    save_blacklist(blacklisted_users)
    await ctx.send(f"🚫 {user.mention} has been blacklisted from using the bot!")


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


@blacklist.error
@unblacklist.error
async def blacklist_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("❌ You do not have permission to use blacklist commands!", delete_after=5)


@bot.command()
@is_not_blacklisted()
@is_server_admin()
async def announcement(ctx, channel: discord.TextChannel | None = None, *, message: str = ""):
    if not message.strip() and not ctx.message.attachments:
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        await ctx.send("❌ **Usage:** `!announcement [#channel] Your message here`", delete_after=5)
        return

    target_channel = channel or ctx.channel

    embed = discord.Embed(
        description=message if message.strip() else None,
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.set_image(url=ANNOUNCEMENT_IMAGE_URL)

    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound):
        pass

    try:
        await target_channel.send(embed=embed)
        await ctx.send(f"✅ Announcement sent to {target_channel.mention}!", delete_after=5)
    except discord.Forbidden:
        await ctx.send(f"❌ I don't have permission to send messages in {target_channel.mention}.", delete_after=5)


@announcement.error
async def announcement_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("❌ You do not have permission to use announcement commands!", delete_after=5)


@bot.command()
@is_not_blacklisted()
@can_manage_codes()
async def cmds(ctx):
    role_ids = server_manager_roles.get(ctx.guild.id, set())
    roles = [ctx.guild.get_role(rid) for rid in role_ids if ctx.guild.get_role(rid)]
    
    if roles:
        role_text = ", ".join([f"**{r.name}**" for r in roles])
    else:
        role_text = "Configured Code Manager Role(s) or Server Admin"

    embed = discord.Embed(
        title="🤖 Bot Commands List",
        description=f"Commands restricted to {role_text}:",
        color=discord.Color.purple(),
    )
    embed.add_field(name="`/generatedlc [max_claims]`", value="Generates a random DLC code with configured max claims (Bot Admin only).", inline=False)
    embed.add_field(name="`/deletecodebypassperms [@user]`", value="Removes code bypass permissions from a user or clears all users if left empty (Bot Admin only).", inline=False)
    embed.add_field(name="`!setcodemanagerrole <@role1> [@role2 ...]`", value="Sets role(s) allowed to create codes for this server (Server Admins only).", inline=False)
    embed.add_field(name="`!createcode [#channel] <code>`", value="Creates a standard code embed.", inline=False)
    embed.add_field(name="`!createrolecode <@role> [#channel] <code>`", value="Creates a role reward code.", inline=False)
    embed.add_field(name="`!createriddle [#channel] \"Question\" \"Answer\"`", value="Creates a custom riddle challenge.", inline=False)
    embed.add_field(name="`!createroleriddle <@role> [#channel] \"Question\" \"Answer\"`", value="Creates a role reward riddle challenge.", inline=False)
    embed.add_field(name="`!announcement [#channel] <message>`", value="Sends an announcement embed with a fixed image URL.", inline=False)
    embed.add_field(name="`!blacklist <@user>`", value="Blacklists a user from redeeming codes (Bot Admin only).", inline=False)
    embed.add_field(name="`!unblacklist <@user>`", value="Removes a user from the blacklist (Bot Admin only).", inline=False)
    await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())


# --- 7. CHAT LISTENER & GLOBAL ERROR LOGGING ---
@bot.event
async def on_command_error(ctx, error):
    if hasattr(ctx.command, 'on_error'):
        return

    ignored = (commands.CommandNotFound,)
    error = getattr(error, 'original', error)

    if isinstance(error, ignored):
        return

    print(f"Unhandled error in command {ctx.command}: {error}")


@bot.event
async def on_message(message):
    global active_bypass_code, active_bypass_max_claims
    if message.author.bot:
        return

    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    if message.author.id in blacklisted_users:
        return

    msg_clean = message.content.strip().lower()

    # Standalone Bypass Code Redemption Check
    if active_bypass_code and msg_clean == active_bypass_code:
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        # Check if user already claimed this specific DLC code
        if message.author.id in redeemed_users:
            await message.channel.send(
                f"⚠️ {message.author.mention}, you have already redeemed this DLC code!",
                delete_after=7
            )
            return

        # Grant exactly 1 bypass use to the redeeming user
        redeemed_users.add(message.author.id)
        bypass_users[message.author.id] = 1

        await message.channel.send(
            f"🔓 {message.author.mention} redeemed the secret code and earned **Code Bypass** for 1 use!",
            delete_after=10
        )

        # Deactivate code if max unique claims limit reached
        if len(redeemed_users) >= active_bypass_max_claims:
            active_bypass_code = None

        return

    channel_id = message.channel.id

    if channel_id in active_codes:
        code_data = active_codes[channel_id]

        if code_data["ready"]:
            target_code = code_data["code"]
            
            # Check bypass status
            has_role_bypass = False
            if isinstance(message.author, discord.Member):
                has_role_bypass = any(role.name == BYPASS_ROLE_NAME for role in message.author.roles)

            has_standalone_bypass = message.author.id in bypass_users and bypass_users[message.author.id] > 0
            has_bypass = has_role_bypass or has_standalone_bypass

            if msg_clean == target_code.lower() or has_bypass:
                # Deduct 1 use from user if claiming via individual DLC bypass
                if not (msg_clean == target_code.lower()) and has_standalone_bypass and not has_role_bypass:
                    bypass_users[message.author.id] -= 1
                    if bypass_users[message.author.id] <= 0:
                        del bypass_users[message.author.id]

                start_time = code_data.get("start_time") or time.time()
                elapsed_seconds = round(time.time() - start_time, 2)

                role_id = code_data.get("role_id")
                challenge_type = code_data.get("type", "code")

                del active_codes[channel_id]

                time_str = f" in **{elapsed_seconds} seconds**"

                if role_id and isinstance(message.author, discord.Member):
                    role = message.guild.get_role(role_id)
                    if role:
                        try:
                            await message.author.add_roles(role)
                            await message.channel.send(
                                f"🎉 {message.author.mention} redeemed the {challenge_type} first{time_str} and won the **{role.name}** role! The code is now closed."
                            )
                        except discord.Forbidden:
                            await message.channel.send(
                                f"{message.author.mention} Correct answer{time_str}, but I lack permissions to grant the role!"
                            )
                    else:
                        await message.channel.send(f"🎉 {message.author.mention} claimed the {challenge_type}{time_str}! The code is now closed.")
                else:
                    await message.channel.send(f"🎉 {message.author.mention} claimed the {challenge_type}{time_str}! The code is now closed.")


# --- 8. RUN BOT WITH ASYNC RECONNECT LOOP ---
async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("Error: DISCORD_TOKEN is missing!")
        return

    while True:
        try:
            async with bot:
                await bot.start(token)
        except discord.errors.HTTPException as e:
            if e.status == 429:
                print("Rate limited by Discord/Cloudflare. Retrying in 60 seconds...")
                await asyncio.sleep(60)
            else:
                print(f"HTTP Exception: {e}")
                await asyncio.sleep(10)
        except Exception as e:
            print(f"Unexpected connection error: {e}")
            await asyncio.sleep(10)


if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())

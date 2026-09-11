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
DLC_IMAGE_URL = "https://cdn.discordapp.com/attachments/1546415351049228410/1546415372213690368/Untitled106_20260907020000.png?ex=6a9fb30b&is=6a9e618b&hm=65715670c974b258a8cff733a2f40ac6fc99801dfffe891df56e3fa07de32b3f&"

# Global Bot Admins (Override permissions on any server)
ADMIN_USER_IDS = {1508960806547623946, 1453702313658159357}

# Dynamic In-Memory States
active_bypass_code = None        # Holds the custom bypass code set by an admin
active_bypass_creator_id = None  # Holds the user ID of the admin who created the active DLC code
active_bypass_max_claims = None  # None = Unlimited claims, otherwise integer limit
redeemed_users = set()           # Set of user IDs who have already claimed the current active DLC code

# --- PERSISTENT FILE STORAGE LOGIC ---
BLACKLIST_FILE = "blacklist.json"
MANAGERS_FILE = "server_managers.json"
BYPASS_FILE = "bypass_users.json"


# 1. Blacklist persistence
def load_blacklist() -> set[int]:
    if os.path.exists(BLACKLIST_FILE):
        try:
            with open(BLACKLIST_FILE, "r") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"Error loading blacklist file: {e}")
    return set()

def save_blacklist(blacklist_set: set[int]):
    try:
        with open(BLACKLIST_FILE, "w") as f:
            json.dump(list(blacklist_set), f)
    except Exception as e:
        print(f"Error saving blacklist file: {e}")


# 2. Server Code Manager Roles persistence (Guild ID -> Set of Role IDs)
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
            json.dump(serializable_data, f)
    except Exception as e:
        print(f"Error saving manager roles file: {e}")


# 3. Code Bypass Users persistence
def load_bypass_users() -> set[int]:
    if os.path.exists(BYPASS_FILE):
        try:
            with open(BYPASS_FILE, "r") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"Error loading bypass users file: {e}")
    return set()

def save_bypass_users(bypass_set: set[int]):
    try:
        with open(BYPASS_FILE, "w") as f:
            json.dump(list(bypass_set), f)
    except Exception as e:
        print(f"Error saving bypass users file: {e}")


# Initialize persistent variables
blacklisted_users = load_blacklist()
server_manager_roles = load_manager_roles()
bypass_users = load_bypass_users()

# --- KEEP-ALIVE WEB SERVER ---
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


# --- BOT CONFIGURATION ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
active_codes = {}


# --- REDEEM PANEL MODAL & BUTTON ---
class RedeemModal(discord.ui.Modal, title="Redeem DLC Code"):
    code_input = discord.ui.TextInput(
        label="Enter DLC Code",
        placeholder="e.g. BRADAR-ABCD-1234",
        required=True,
        max_length=50
    )

    async def on_submit(self, interaction: discord.Interaction):
        global active_bypass_code, active_bypass_creator_id, active_bypass_max_claims

        entered_code = self.code_input.value.strip().lower()

        if interaction.user.id in blacklisted_users:
            await interaction.response.send_message("🚫 You are blacklisted from redeeming codes!", ephemeral=True)
            return

        if not active_bypass_code or entered_code != active_bypass_code:
            await interaction.response.send_message("❌ Invalid or expired DLC code!", ephemeral=True)
            return

        if interaction.user.id == active_bypass_creator_id:
            await interaction.response.send_message("⚠️ You cannot redeem your own generated DLC code!", ephemeral=True)
            return

        if interaction.user.id in redeemed_users:
            await interaction.response.send_message("⚠️ You have already redeemed this DLC code!", ephemeral=True)
            return

        redeemed_users.add(interaction.user.id)
        bypass_users.add(interaction.user.id)
        save_bypass_users(bypass_users)

        embed = discord.Embed(
            title="🎁 DLC Code Redeemed!",
            description=f"🔓 {interaction.user.mention}, you have successfully redeemed code bypass permissions!",
            color=discord.Color.green()
        )
        embed.set_image(url=DLC_IMAGE_URL)

        await interaction.response.send_message(embed=embed)

        # Clear active code state when limit is reached (if not unlimited)
        if active_bypass_max_claims is not None and len(redeemed_users) >= active_bypass_max_claims:
            active_bypass_code = None
            active_bypass_creator_id = None
            active_bypass_max_claims = None
            redeemed_users.clear()


class RedeemPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Redeem DLC Code", style=discord.ButtonStyle.green, custom_id="redeem_dlc_btn", emoji="🎁")
    async def redeem_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RedeemModal())


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}!")
    bot.add_view(RedeemPanelView())
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


def user_is_server_admin(member: discord.Member | discord.User) -> bool:
    if member.id in ADMIN_USER_IDS:
        return True
    if isinstance(member, discord.Member):
        return member.guild_permissions.manage_guild or member.guild_permissions.administrator
    return False


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


# --- DYNAMIC WORD & CHUNK SPLITTING ---
def split_phrase(text: str) -> list[str]:
    if " " in text:
        return text.split()

    sections = wordninja.split(text)
    if sections:
        return sections
    
    chunk_size = max(1, len(text) // 3)
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


# --- CODE & RIDDLE CREATION HELPERS ---
async def process_code_creation(
    target_channel: discord.TextChannel,
    clean_code: str,
    sections: list[str],
    creator: discord.User | discord.Member,
    reward_role: discord.Role | None = None,
    random_digits: str | None = None
):
    full_solution = f"{clean_code} {random_digits}".strip() if random_digits else clean_code

    active_codes[target_channel.id] = {
        "code": full_solution.lower(),
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

    await asyncio.sleep(2.5)

    if random_digits:
        embed.add_field(
            name="🔢 Extra Security Digits",
            value=f"**{random_digits}**",
            inline=False
        )
        embed.description = (
            f"**Created by:** {creator.mention}\n\n"
            f"**USE CODE:** {clean_code}\n\n"
            f"*Type the base code followed by the security digits to solve!*"
        )
        await message.edit(embed=embed)

    active_codes[target_channel.id]["ready"] = True
    active_codes[target_channel.id]["start_time"] = time.time()

    embed.title = "Role Code Created!" if reward_role else "Code Created!"
    reward_text = f"\n**Reward:** {reward_role.mention}" if reward_role else ""
    if reward_text and not embed.description.endswith(reward_text):
        embed.description += reward_text

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


# --- SLASH COMMANDS ---
@bot.tree.command(name="announcement", description="Sends an announcement embed with image or video support (Bot Admin Only)")
@app_commands.describe(
    title="The title of the announcement",
    description="Optional body text below the title",
    media="Optional image or video file to attach",
    channel="The channel to post the announcement in (defaults to current channel)"
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

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.purple()
    )
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


@bot.tree.command(name="setcodemanagerrole", description="Sets role(s) allowed to create codes for this server (Server Admin Only).")
@app_commands.describe(
    role1="Primary role allowed to create codes",
    role2="Additional role allowed to create codes (optional)",
    role3="Additional role allowed to create codes (optional)",
    role4="Additional role allowed to create codes (optional)",
    role5="Additional role allowed to create codes (optional)"
)
async def setcodemanagerrole_slash(
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
        await interaction.response.send_message("❌ You need the **Manage Server** or **Administrator** permission to set manager roles!", ephemeral=True)
        return

    roles_list = [r for r in [role1, role2, role3, role4, role5] if r is not None]
    
    server_manager_roles[interaction.guild.id] = {role.id for role in roles_list}
    save_manager_roles(server_manager_roles)

    role_names = ", ".join([f"**{role.name}** (`ID: {role.id}`)" for role in roles_list])
    await interaction.response.send_message(
        f"✅ Code Manager roles for **{interaction.guild.name}** set to: {role_names}!",
        ephemeral=True
    )


@bot.tree.command(name="createcode", description="Creates a standard or role-reward code embed in a channel.")
@app_commands.describe(
    code="The text code for users to type",
    include_numbers="Set to True to add a random 4-digit number in a separate embed section",
    role="Optional reward role to assign when claimed",
    channel="The channel to display the code in (defaults to current channel)"
)
async def createcode_slash(
    interaction: discord.Interaction, 
    code: str, 
    include_numbers: bool = False,
    role: discord.Role | None = None,
    channel: discord.TextChannel | None = None
):
    if interaction.user.id in blacklisted_users:
        await interaction.response.send_message("🚫 You are blacklisted from using bot commands!", ephemeral=True)
        return

    if not user_can_manage_codes(interaction.user, interaction.guild):
        await interaction.response.send_message("❌ You do not have permission to create codes!", ephemeral=True)
        return

    if role and interaction.guild:
        member = interaction.user
        if isinstance(member, discord.Member):
            if role.position >= member.top_role.position and member.id not in ADMIN_USER_IDS:
                await interaction.response.send_message(
                    f"❌ You cannot create a code for {role.mention} because it is higher than or equal to your role!",
                    ephemeral=True
                )
                return

        if role.position >= interaction.guild.me.top_role.position:
            await interaction.response.send_message(
                f"❌ I cannot assign {role.mention} because it is higher than my highest role!",
                ephemeral=True
            )
            return

    target_channel = channel or interaction.channel
    clean_code = code.strip()

    if not clean_code:
        await interaction.response.send_message("❌ Code cannot be empty!", ephemeral=True)
        return

    random_digits = None
    if include_numbers:
        random_digits = "".join(random.choices(string.digits, k=4))

    reward_msg = f" with reward {role.mention}" if role else ""
    await interaction.response.send_message(f"✅ Code creation started in {target_channel.mention}{reward_msg}!", ephemeral=True)

    sections = split_phrase(clean_code)
    await process_code_creation(
        target_channel, 
        clean_code, 
        sections, 
        interaction.user, 
        reward_role=role, 
        random_digits=random_digits
    )


@bot.tree.command(name="createriddle", description="Creates a standard or role-reward riddle challenge.")
@app_commands.describe(
    question="The question or riddle prompt",
    answer="The exact answer users must type to solve it",
    role="Optional reward role to assign when solved",
    channel="The channel to post the riddle in (defaults to current channel)"
)
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

    if role and interaction.guild:
        member = interaction.user
        if isinstance(member, discord.Member):
            if role.position >= member.top_role.position and member.id not in ADMIN_USER_IDS:
                await interaction.response.send_message(
                    f"❌ You cannot create a riddle for {role.mention} because it is higher than or equal to your role!",
                    ephemeral=True
                )
                return

        if role.position >= interaction.guild.me.top_role.position:
            await interaction.response.send_message(
                f"❌ I cannot assign {role.mention} because it is higher than my highest role!",
                ephemeral=True
            )
            return

    target_channel = channel or interaction.channel
    clean_question = question.strip()
    clean_answer = answer.strip()

    if not clean_question or not clean_answer:
        await interaction.response.send_message("❌ Question and answer cannot be empty!", ephemeral=True)
        return

    reward_msg = f" with reward {role.mention}" if role else ""
    await interaction.response.send_message(f"✅ Riddle created in {target_channel.mention}{reward_msg}!", ephemeral=True)

    await process_riddle_creation(target_channel, clean_question, clean_answer, interaction.user, reward_role=role)


@bot.tree.command(name="givecodebypass", description="Grants code bypass permissions directly to a user (Bot Admin Only)")
@app_commands.describe(user="The user to receive permanent code bypass permissions")
async def givecodebypass(interaction: discord.Interaction, user: discord.User | discord.Member):
    if interaction.user.id not in ADMIN_USER_IDS:
        await interaction.response.send_message("❌ You do not have permission to use this command!", ephemeral=True)
        return

    if interaction.user.id in blacklisted_users:
        await interaction.response.send_message("🚫 You are blacklisted from using bot commands!", ephemeral=True)
        return

    if user.id in bypass_users:
        await interaction.response.send_message(f"⚠️ {user.mention} already has code bypass permissions!", ephemeral=True)
        return

    bypass_users.add(user.id)
    save_bypass_users(bypass_users)

    await interaction.response.send_message(f"🔓 Successfully granted code bypass permissions to {user.mention}!", ephemeral=True)


@bot.tree.command(name="generatedlc", description="Generates a random DLC code (Bot Admin Only)")
@app_commands.describe(
    max_claims="Optional maximum claims (leave empty for unlimited)"
)
async def generatedlc(interaction: discord.Interaction, max_claims: int | None = None):
    global active_bypass_code, active_bypass_creator_id, active_bypass_max_claims, redeemed_users

    if interaction.user.id not in ADMIN_USER_IDS:
        await interaction.response.send_message("❌ You do not have permission to use this command!", ephemeral=True)
        return

    if interaction.user.id in blacklisted_users:
        await interaction.response.send_message("🚫 You are blacklisted from using bot commands!", ephemeral=True)
        return

    if max_claims is not None and max_claims < 1:
        await interaction.response.send_message("❌ Max claims must be at least 1!", ephemeral=True)
        return

    letters = ''.join(random.choices(string.ascii_uppercase, k=4))
    numbers = ''.join(random.choices(string.digits, k=4))
    dlc_code = f"BRADAR-{letters}-{numbers}"

    active_bypass_code = dlc_code.lower()
    active_bypass_creator_id = interaction.user.id
    active_bypass_max_claims = max_claims
    redeemed_users.clear()

    if max_claims is None:
        claim_text = "♾️ Unlimited"
    elif max_claims == 1:
        claim_text = "1 person"
    else:
        claim_text = f"{max_claims} people"

    await interaction.response.send_message(
        f"🎁 **Generated DLC Code:** `{dlc_code}`\n👥 **Max Claims:** {claim_text}\n✅ *This code is active until claimed!*", 
        ephemeral=True
    )


@bot.tree.command(name="sendredeempanel", description="Posts an interactive redemption panel in the channel (Bot Admin Only)")
@app_commands.describe(channel="The channel to send the redemption panel to (defaults to current channel)")
async def sendredeempanel(interaction: discord.Interaction, channel: discord.TextChannel | None = None):
    if interaction.user.id not in ADMIN_USER_IDS:
        await interaction.response.send_message("❌ You do not have permission to use this command!", ephemeral=True)
        return

    target_channel = channel or interaction.channel

    embed = discord.Embed(
        title="🎁 DLC Code Redemption Center",
        description="Click the button below to open the code entry prompt and redeem your DLC code!",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)

    await target_channel.send(embed=embed, view=RedeemPanelView())
    await interaction.response.send_message(f"✅ Redemption panel successfully sent to {target_channel.mention}!", ephemeral=True)


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
        
        bypass_users.remove(user.id)
        save_bypass_users(bypass_users)
        await interaction.response.send_message(f"🛑 Successfully removed code bypass permissions from {user.mention}!", ephemeral=True)
    else:
        if not bypass_users:
            await interaction.response.send_message("⚠️ No users currently have code bypass permissions.", ephemeral=True)
            return

        count = len(bypass_users)
        bypass_users.clear()
        save_bypass_users(bypass_users)
        await interaction.response.send_message(f"🛑 Successfully removed code bypass permissions from all {count} user(s)!", ephemeral=True)


# --- PREFIX COMMANDS ---
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
    embed.add_field(name="`/createcode <code> [include_numbers] [role] [channel]`", value="Creates a standard or role-reward code embed via slash command.", inline=False)
    embed.add_field(name="`/createriddle <question> <answer> [role] [channel]`", value="Creates a standard or role-reward riddle challenge via slash command.", inline=False)
    embed.add_field(name="`/setcodemanagerrole <role1> [role2 ...]`", value="Sets role(s) allowed to create codes for this server (Server Admins only).", inline=False)
    embed.add_field(name="`/givecodebypass <@user>`", value="Grants code bypass permissions directly to a user (Bot Admin only).", inline=False)
    embed.add_field(name="`/generatedlc [max_claims]`", value="Generates a random DLC code (leave max_claims empty for unlimited).", inline=False)
    embed.add_field(name="`/sendredeempanel [channel]`", value="Posts an interactive redemption panel with a modal pop-up (Bot Admin only).", inline=False)
    embed.add_field(name="`/deletecodebypassperms [@user]`", value="Removes code bypass permissions from a user or clears all users if left empty (Bot Admin only).", inline=False)
    embed.add_field(name="`/announcement <title> [description] [media] [channel]`", value="Sends an announcement embed with purple color and media support (Bot Admin only).", inline=False)
    embed.add_field(name="`!blacklist <@user>`", value="Blacklists a user from redeeming codes (Bot Admin only).", inline=False)
    embed.add_field(name="`!unblacklist <@user>`", value="Removes a user from the blacklist (Bot Admin only).", inline=False)
    await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())


# --- CHAT LISTENER & GLOBAL ERROR LOGGING ---
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
    global active_bypass_code, active_bypass_creator_id, active_bypass_max_claims
    if message.author.bot:
        return

    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    if message.author.id in blacklisted_users:
        return

    msg_clean = message.content.strip().lower()

    if active_bypass_code and msg_clean == active_bypass_code:
        if message.author.id == active_bypass_creator_id:
            return

        if message.author.id in redeemed_users:
            await message.channel.send(
                f"⚠️ {message.author.mention}, you have already redeemed this DLC code!",
                delete_after=7
            )
            return

        redeemed_users.add(message.author.id)
        
        bypass_users.add(message.author.id)
        save_bypass_users(bypass_users)

        embed = discord.Embed(
            title="🎁 You have successfully redeemed a DLC for Code Bypass!",
            description=f"🔓 {message.author.mention}, You have successfully redeemed a DLC for Code Bypass!",
            color=discord.Color.green()
        )
        embed.set_image(url=DLC_IMAGE_URL)

        await message.channel.send(embed=embed)

        # Clear active code state when limit is reached (if limit is set)
        if active_bypass_max_claims is not None and len(redeemed_users) >= active_bypass_max_claims:
            active_bypass_code = None
            active_bypass_creator_id = None
            active_bypass_max_claims = None
            redeemed_users.clear()

        return

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


# --- RUN BOT WITH ASYNC RECONNECT LOOP ---
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

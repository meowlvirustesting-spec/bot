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
import unicodedata
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
SETTINGS_FILE = "bot_settings.json"


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
bot_settings = load_json_file(SETTINGS_FILE, {"admin_log_channel_id": None})


def save_leaderboard():
    save_json_file(LEADERBOARD_FILE, leaderboard_data)


def save_settings():
    save_json_file(SETTINGS_FILE, bot_settings)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return ' '.join(text.lower().strip().split())


def get_flag_emoji(country_code: str) -> str:
    """Converts a 2-letter ISO country code into a flag emoji."""
    if not country_code or len(country_code) != 2:
        return "🏳️"
    code = country_code.upper()
    return chr(ord(code[0]) + 127397) + chr(ord(code[1]) + 127397)


def calculate_bearing_direction(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Calculates compass direction from point 1 to point 2."""
    d_lon = math.radians(lon2 - lon1)
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    y = math.sin(d_lon) * math.cos(lat2_rad)
    x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(d_lon)
    bearing = (math.degrees(math.atan2(y, x)) + 360) % 360

    if 22.5 <= bearing < 67.5:
        return "↗️ NE"
    elif 67.5 <= bearing < 112.5:
        return "➡️ E"
    elif 112.5 <= bearing < 157.5:
        return "↘️ SE"
    elif 157.5 <= bearing < 202.5:
        return "⬇️ S"
    elif 202.5 <= bearing < 247.5:
        return "↙️ SW"
    elif 247.5 <= bearing < 292.5:
        return "⬅️ W"
    elif 292.5 <= bearing < 337.5:
        return "↖️ NW"
    else:
        return "⬆️ N"


async def log_admin_action(executor: discord.User | discord.Member, action_title: str, details: str):
    log_channel_id = bot_settings.get("admin_log_channel_id")
    if not log_channel_id:
        return

    channel = bot.get_channel(log_channel_id)
    if not channel:
        try:
            channel = await bot.fetch_channel(log_channel_id)
        except Exception:
            return

    embed = discord.Embed(
        title=f"🛡️ Admin Command Log: {action_title}",
        description=details,
        color=discord.Color.dark_red(),
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(name="Executed By", value=f"{executor.mention} (`{executor.id}`)", inline=False)
    if hasattr(executor, "display_avatar"):
        embed.set_thumbnail(url=executor.display_avatar.url)

    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"Failed to send admin log: {e}")


# --- SIMILAR FLAGS PAIRS DATASET ---
SIMILAR_FLAG_PAIRS = [
    (("mali", "Mali", "ML"), ("guinea", "Guinea", "GN")),
    (("indonesia", "Indonesia", "ID"), ("monaco", "Monaco", "MC")),
    (("romania", "Romania", "RO"), ("chad", "Chad", "TD")),
    (("ireland", "Ireland", "IE"), ("cote d'ivoire", "Côte d'Ivoire", "CI")),
    (("new zealand", "New Zealand", "NZ"), ("australia", "Australia", "AU")),
    (("colombia", "Colombia", "CO"), ("ecuador", "Ecuador", "EC")),
    (("venezuela", "Venezuela", "VE"), ("colombia", "Colombia", "CO")),
    (("luxembourg", "Luxembourg", "LU"), ("netherlands", "Netherlands", "NL")),
    (("slovenia", "Slovenia", "SI"), ("slovakia", "Slovakia", "SK")),
    (("norway", "Norway", "NO"), ("iceland", "Iceland", "IS")),
    (("bahrain", "Bahrain", "BH"), ("qatar", "Qatar", "QA")),
    (("el salvador", "El Salvador", "SV"), ("honduras", "Honduras", "HN")),
    (("nicaragua", "Nicaragua", "NI"), ("guatemala", "Guatemala", "GT")),
]

# --- FULL WORLD COUNTRY & TERRITORY DATASET ---
COUNTRY_DATA = {
    # --- AMERICAS ---
    "antigua and barbuda": (17.0608, -61.7964, "Antigua and Barbuda", "AG", set(), "americas"),
    "argentina": (-38.4161, -63.6167, "Argentina", "AR", {"bolivia", "brazil", "chile", "paraguay", "uruguay"}, "americas"),
    "bahamas": (25.0343, -77.3963, "Bahamas", "BS", set(), "americas"),
    "barbados": (13.1939, -59.5432, "Barbados", "BB", set(), "americas"),
    "belize": (17.1899, -88.4976, "Belize", "BZ", {"guatemala", "mexico"}, "americas"),
    "bolivia": (-16.2902, -63.5887, "Bolivia", "BO", {"argentina", "brazil", "chile", "paraguay", "peru"}, "americas"),
    "brazil": (-14.2350, -51.9253, "Brazil", "BR", {"argentina", "bolivia", "colombia", "french guiana", "guyana", "paraguay", "peru", "suriname", "uruguay", "venezuela"}, "americas"),
    "canada": (56.1304, -106.3468, "Canada", "CA", {"united states", "usa"}, "americas"),
    "chile": (-35.6751, -71.5430, "Chile", "CL", {"argentina", "bolivia", "peru"}, "americas"),
    "colombia": (4.5709, -74.2973, "Colombia", "CO", {"brazil", "ecuador", "panama", "peru", "venezuela"}, "americas"),
    "costa rica": (10.4806, -83.5858, "Costa Rica", "CR", {"nicaragua", "panama"}, "americas"),
    "cuba": (21.5218, -77.7812, "Cuba", "CU", set(), "americas"),
    "dominica": (15.4150, -61.3710, "Dominica", "DM", set(), "americas"),
    "dominican republic": (18.7357, -70.1627, "Dominican Republic", "DO", {"haiti"}, "americas"),
    "ecuador": (-1.8312, -78.1834, "Ecuador", "EC", {"colombia", "peru"}, "americas"),
    "el salvador": (13.7942, -88.8965, "El Salvador", "SV", {"guatemala", "honduras"}, "americas"),
    "grenada": (12.1165, -61.6790, "Grenada", "GD", set(), "americas"),
    "guatemala": (15.7835, -90.2308, "Guatemala", "GT", {"belize", "el salvador", "honduras", "mexico"}, "americas"),
    "guyana": (4.8604, -58.9302, "Guyana", "GY", {"brazil", "suriname", "venezuela"}, "americas"),
    "haiti": (18.9712, -72.2852, "Haiti", "HT", {"dominican republic"}, "americas"),
    "honduras": (15.2000, -86.2419, "Honduras", "HN", {"el salvador", "guatemala", "nicaragua"}, "americas"),
    "jamaica": (18.1096, -77.2975, "Jamaica", "JM", set(), "americas"),
    "mexico": (23.6345, -102.5528, "Mexico", "MX", {"belize", "guatemala", "united states", "usa"}, "americas"),
    "nicaragua": (12.8654, -85.2072, "Nicaragua", "NI", {"costa rica", "honduras"}, "americas"),
    "panama": (8.5380, -80.7821, "Panama", "PA", {"colombia", "costa rica"}, "americas"),
    "paraguay": (-23.4425, -58.4438, "Paraguay", "PY", {"argentina", "bolivia", "brazil"}, "americas"),
    "peru": (-9.1899, -75.0152, "Peru", "PE", {"bolivia", "brazil", "chile", "colombia", "ecuador"}, "americas"),
    "saint kitts and nevis": (17.3578, -62.7829, "Saint Kitts and Nevis", "KN", set(), "americas"),
    "saint lucia": (13.9094, -60.9789, "Saint Lucia", "LC", set(), "americas"),
    "saint vincent and the grenadines": (12.9843, -61.2872, "Saint Vincent and the Grenadines", "VC", set(), "americas"),
    "suriname": (3.9193, -56.0278, "Suriname", "SR", {"brazil", "french guiana", "guyana"}, "americas"),
    "trinidad and tobago": (10.6918, -61.2225, "Trinidad and Tobago", "TT", set(), "americas"),
    "united states": (37.0902, -95.7129, "United States", "US", {"canada", "mexico"}, "americas"),
    "uruguay": (-32.5228, -55.7658, "Uruguay", "UY", {"argentina", "brazil"}, "americas"),
    "venezuela": (6.4238, -66.5897, "Venezuela", "VE", {"brazil", "colombia", "guyana"}, "americas"),

    # --- EUROPE & ASIA ---
    "albania": (41.1533, 20.1683, "Albania", "AL", {"greece", "kosovo", "montenegro", "north macedonia"}, "europe_asia"),
    "andorra": (42.5063, 1.5218, "Andorra", "AD", {"france", "spain"}, "europe_asia"),
    "armenia": (40.0691, 45.0382, "Armenia", "AM", {"azerbaijan", "georgia", "iran", "turkey"}, "europe_asia"),
    "austria": (47.5162, 14.5501, "Austria", "AT", {"czechia", "germany", "hungary", "italy", "liechtenstein", "slovakia", "slovenia", "switzerland"}, "europe_asia"),
    "azerbaijan": (40.1431, 47.5769, "Azerbaijan", "AZ", {"armenia", "georgia", "iran", "russia", "turkey"}, "europe_asia"),
    "bahrain": (26.0667, 50.5577, "Bahrain", "BH", set(), "europe_asia"),
    "bangladesh": (23.6850, 90.3563, "Bangladesh", "BD", {"india", "myanmar"}, "europe_asia"),
    "belarus": (53.7098, 27.9534, "Belarus", "BY", {"latvia", "lithuania", "poland", "russia", "ukraine"}, "europe_asia"),
    "belgium": (50.5039, 4.4699, "Belgium", "BE", {"france", "germany", "luxembourg", "netherlands"}, "europe_asia"),
    "bhutan": (27.5142, 90.4336, "Bhutan", "BT", {"china", "india"}, "europe_asia"),
    "bosnia and herzegovina": (43.9159, 17.6791, "Bosnia and Herzegovina", "BA", {"croatia", "montenegro", "serbia"}, "europe_asia"),
    "brunei": (4.5353, 114.7277, "Brunei", "BN", {"malaysia"}, "europe_asia"),
    "bulgaria": (42.7339, 25.4858, "Bulgaria", "BG", {"greece", "north macedonia", "romania", "serbia", "turkey"}, "europe_asia"),
    "cambodia": (12.5657, 104.9910, "Cambodia", "KH", {"laos", "thailand", "vietnam"}, "europe_asia"),
    "china": (35.8617, 104.1954, "China", "CN", {"afghanistan", "bhutan", "india", "kazakhstan", "kyrgyzstan", "laos", "mongolia", "myanmar", "nepal", "north korea", "pakistan", "russia", "tajikistan", "vietnam"}, "europe_asia"),
    "croatia": (45.1000, 15.2000, "Croatia", "HR", {"bosnia and herzegovina", "hungary", "montenegro", "serbia", "slovenia"}, "europe_asia"),
    "cyprus": (35.1264, 33.4299, "Cyprus", "CY", set(), "europe_asia"),
    "czechia": (49.8175, 15.4730, "Czechia", "CZ", {"austria", "germany", "poland", "slovakia"}, "europe_asia"),
    "denmark": (56.2639, 9.5018, "Denmark", "DK", {"germany"}, "europe_asia"),
    "estonia": (58.5953, 25.0136, "Estonia", "EE", {"latvia", "russia"}, "europe_asia"),
    "finland": (61.9241, 25.7482, "Finland", "FI", {"norway", "russia", "sweden"}, "europe_asia"),
    "france": (46.2276, 2.2137, "France", "FR", {"andorra", "belgium", "germany", "italy", "luxembourg", "monaco", "spain", "switzerland"}, "europe_asia"),
    "georgia": (42.3154, 43.3569, "Georgia", "GE", {"armenia", "azerbaijan", "russia", "turkey"}, "europe_asia"),
    "germany": (51.1657, 10.4515, "Germany", "DE", {"austria", "belgium", "czechia", "denmark", "france", "luxembourg", "netherlands", "poland", "switzerland"}, "europe_asia"),
    "greece": (39.0742, 21.8243, "Greece", "GR", {"albania", "bulgaria", "north macedonia", "turkey"}, "europe_asia"),
    "hungary": (47.1625, 19.5033, "Hungary", "HU", {"austria", "croatia", "romania", "serbia", "slovakia", "slovenia", "ukraine"}, "europe_asia"),
    "iceland": (64.9631, -19.0208, "Iceland", "IS", set(), "europe_asia"),
    "india": (20.5937, 78.9629, "India", "IN", {"bangladesh", "bhutan", "china", "myanmar", "nepal", "pakistan"}, "europe_asia"),
    "indonesia": (-0.7893, 113.9213, "Indonesia", "ID", {"malaysia", "papua new guinea", "timor-leste"}, "europe_asia"),
    "iran": (32.4279, 53.6880, "Iran", "IR", {"afghanistan", "armenia", "azerbaijan", "iraq", "pakistan", "turkey", "turkmenistan"}, "europe_asia"),
    "iraq": (33.2232, 43.6793, "Iraq", "IQ", {"iran", "jordan", "kuwait", "saudi arabia", "syria", "turkey"}, "europe_asia"),
    "ireland": (53.1424, -7.6921, "Ireland", "IE", {"united kingdom", "uk"}, "europe_asia"),
    "israel": (31.0461, 34.8516, "Israel", "IL", {"egypt", "jordan", "lebanon", "palestine", "syria"}, "europe_asia"),
    "italy": (41.8719, 12.5674, "Italy", "IT", {"austria", "france", "san marino", "slovenia", "switzerland", "vatican city"}, "europe_asia"),
    "japan": (36.2048, 138.2529, "Japan", "JP", set(), "europe_asia"),
    "jordan": (30.5852, 36.2384, "Jordan", "JO", {"iraq", "israel", "palestine", "saudi arabia", "syria"}, "europe_asia"),
    "kazakhstan": (48.0196, 66.9237, "Kazakhstan", "KZ", {"china", "kyrgyzstan", "russia", "turkmenistan", "uzbekistan"}, "europe_asia"),
    "kosovo": (42.6026, 20.9030, "Kosovo", "XK", {"albania", "montenegro", "north macedonia", "serbia"}, "europe_asia"),
    "kuwait": (29.3117, 47.4818, "Kuwait", "KW", {"iraq", "saudi arabia"}, "europe_asia"),
    "kyrgyzstan": (41.2044, 74.7661, "Kyrgyzstan", "KG", {"china", "kazakhstan", "tajikistan", "uzbekistan"}, "europe_asia"),
    "laos": (19.8563, 102.4955, "Laos", "LA", {"cambodia", "china", "myanmar", "thailand", "vietnam"}, "europe_asia"),
    "latvia": (56.8796, 24.6032, "Latvia", "LV", {"belarus", "estonia", "lithuania", "russia"}, "europe_asia"),
    "lebanon": (33.8547, 35.8623, "Lebanon", "LB", {"israel", "syria"}, "europe_asia"),
    "liechtenstein": (47.1660, 9.5554, "Liechtenstein", "LI", {"austria", "switzerland"}, "europe_asia"),
    "lithuania": (55.1694, 23.8813, "Lithuania", "LT", {"belarus", "latvia", "poland", "russia"}, "europe_asia"),
    "luxembourg": (49.8153, 6.1296, "Luxembourg", "LU", {"belgium", "france", "germany"}, "europe_asia"),
    "malaysia": (4.2105, 101.9758, "Malaysia", "MY", {"brunei", "indonesia", "thailand"}, "europe_asia"),
    "maldives": (3.2028, 73.2207, "Maldives", "MV", set(), "europe_asia"),
    "malta": (35.9375, 14.3754, "Malta", "MT", set(), "europe_asia"),
    "moldova": (47.4116, 28.3699, "Moldova", "MD", {"romania", "ukraine"}, "europe_asia"),
    "monaco": (43.7384, 7.4246, "Monaco", "MC", {"france"}, "europe_asia"),
    "mongolia": (46.8625, 103.8467, "Mongolia", "MN", {"china", "russia"}, "europe_asia"),
    "montenegro": (42.7087, 19.3744, "Montenegro", "ME", {"albania", "bosnia and herzegovina", "kosovo", "serbia"}, "europe_asia"),
    "myanmar": (21.9162, 95.9560, "Myanmar", "MM", {"bangladesh", "china", "india", "laos", "thailand"}, "europe_asia"),
    "nepal": (28.3949, 84.1240, "Nepal", "NP", {"china", "india"}, "europe_asia"),
    "netherlands": (52.1326, 5.2913, "Netherlands", "NL", {"belgium", "germany"}, "europe_asia"),
    "north korea": (40.3399, 127.5101, "North Korea", "KP", {"china", "russia", "south korea"}, "europe_asia"),
    "north macedonia": (41.6086, 21.7453, "North Macedonia", "MK", {"albania", "bulgaria", "greece", "kosovo", "serbia"}, "europe_asia"),
    "norway": (60.4720, 8.4689, "Norway", "NO", {"finland", "russia", "sweden"}, "europe_asia"),
    "oman": (21.5126, 55.9232, "Oman", "OM", {"saudi arabia", "united arab emirates", "yemen"}, "europe_asia"),
    "pakistan": (30.3753, 69.3451, "Pakistan", "PK", {"afghanistan", "china", "india", "iran"}, "europe_asia"),
    "palestine": (31.9522, 35.2332, "Palestine", "PS", {"egypt", "israel", "jordan"}, "europe_asia"),
    "philippines": (12.8797, 121.7740, "Philippines", "PH", set(), "europe_asia"),
    "poland": (51.9194, 19.1451, "Poland", "PL", {"belarus", "czechia", "germany", "lithuania", "russia", "slovakia", "ukraine"}, "europe_asia"),
    "portugal": (39.3999, -8.2245, "Portugal", "PT", {"spain"}, "europe_asia"),
    "qatar": (25.3548, 51.1839, "Qatar", "QA", {"saudi arabia"}, "europe_asia"),
    "romania": (45.9432, 24.9668, "Romania", "RO", {"bulgaria", "hungary", "moldova", "serbia", "ukraine"}, "europe_asia"),
    "russia": (61.5240, 105.3188, "Russia", "RU", {"azerbaijan", "belarus", "china", "estonia", "finland", "georgia", "kazakhstan", "latvia", "lithuania", "mongolia", "north korea", "norway", "poland", "ukraine"}, "europe_asia"),
    "san marino": (43.9424, 12.4578, "San Marino", "SM", {"italy"}, "europe_asia"),
    "saudi arabia": (23.8859, 45.0792, "Saudi Arabia", "SA", {"iraq", "jordan", "kuwait", "oman", "qatar", "united arab emirates", "yemen"}, "europe_asia"),
    "serbia": (44.0165, 21.0059, "Serbia", "RS", {"bosnia and herzegovina", "bulgaria", "croatia", "hungary", "kosovo", "montenegro", "north macedonia", "romania"}, "europe_asia"),
    "singapore": (1.3521, 103.8198, "Singapore", "SG", set(), "europe_asia"),
    "slovakia": (48.6690, 19.6990, "Slovakia", "SK", {"austria", "czechia", "hungary", "poland", "ukraine"}, "europe_asia"),
    "slovenia": (46.1512, 14.9955, "Slovenia", "SI", {"austria", "croatia", "italy", "hungary"}, "europe_asia"),
    "south korea": (35.9078, 127.7669, "South Korea", "KR", {"north korea"}, "europe_asia"),
    "spain": (40.4637, -3.7492, "Spain", "ES", {"andorra", "france", "gibraltar", "morocco", "portugal"}, "europe_asia"),
    "sri lanka": (7.8731, 80.7718, "Sri Lanka", "LK", set(), "europe_asia"),
    "sweden": (60.1282, 18.6435, "Sweden", "SE", {"finland", "norway"}, "europe_asia"),
    "switzerland": (46.8182, 8.2275, "Switzerland", "CH", {"austria", "france", "germany", "italy", "liechtenstein"}, "europe_asia"),
    "syria": (34.8021, 38.9968, "Syria", "SY", {"iraq", "israel", "jordan", "lebanon", "turkey"}, "europe_asia"),
    "taiwan": (23.6978, 120.9605, "Taiwan", "TW", set(), "europe_asia"),
    "tajikistan": (38.8610, 71.2761, "Tajikistan", "TJ", {"afghanistan", "china", "kyrgyzstan", "uzbekistan"}, "europe_asia"),
    "thailand": (15.8700, 100.9925, "Thailand", "TH", {"cambodia", "laos", "malaysia", "myanmar"}, "europe_asia"),
    "timor-leste": (-8.8742, 125.7275, "Timor-Leste", "TL", {"indonesia"}, "europe_asia"),
    "turkey": (38.9637, 35.2433, "Turkey", "TR", {"armenia", "azerbaijan", "bulgaria", "georgia", "greece", "iran", "iraq", "syria"}, "europe_asia"),
    "turkmenistan": (38.9697, 59.5563, "Turkmenistan", "TM", {"afghanistan", "iran", "kazakhstan", "uzbekistan"}, "europe_asia"),
    "ukraine": (48.3794, 31.1656, "Ukraine", "UA", {"belarus", "hungary", "moldova", "poland", "romania", "russia", "slovakia"}, "europe_asia"),
    "united arab emirates": (23.4241, 53.8478, "United Arab Emirates", "AE", {"oman", "saudi arabia"}, "europe_asia"),
    "united kingdom": (55.3781, -3.4360, "United Kingdom", "GB", {"ireland"}, "europe_asia"),
    "uzbekistan": (41.3775, 64.5853, "Uzbekistan", "UZ", {"afghanistan", "kazakhstan", "kyrgyzstan", "tajikistan", "turkmenistan"}, "europe_asia"),
    "vatican city": (41.9029, 12.4534, "Vatican City", "VA", {"italy"}, "europe_asia"),
    "vietnam": (14.0583, 108.2772, "Vietnam", "VN", {"cambodia", "china", "laos"}, "europe_asia"),
    "yemen": (15.5527, 48.5164, "Yemen", "YE", {"oman", "saudi arabia"}, "europe_asia"),

    # --- AFRICA & OCEANIA ---
    "afghanistan": (33.9391, 67.7100, "Afghanistan", "AF", {"china", "iran", "pakistan", "tajikistan", "turkmenistan", "uzbekistan"}, "africa_oceania"),
    "algeria": (28.0339, 1.6596, "Algeria", "DZ", {"libya", "mali", "mauritania", "morocco", "niger", "tunisia", "western sahara"}, "africa_oceania"),
    "angola": (-11.2027, 17.8739, "Angola", "AO", {"congo", "democratic republic of the congo", "namibia", "zambia"}, "africa_oceania"),
    "australia": (-25.2744, 133.7751, "Australia", "AU", set(), "africa_oceania"),
    "benin": (9.3077, 2.3158, "Benin", "BJ", {"burkina faso", "niger", "nigeria", "togo"}, "africa_oceania"),
    "botswana": (-22.3285, 24.6849, "Botswana", "BW", {"namibia", "south africa", "zambia", "zimbabwe"}, "africa_oceania"),
    "burkina faso": (12.2383, -1.5616, "Burkina Faso", "BF", {"benin", "cote d'ivoire", "ghana", "mali", "niger", "togo"}, "africa_oceania"),
    "burundi": (-3.3731, 29.9189, "Burundi", "BI", {"democratic republic of the congo", "rwanda", "tanzania"}, "africa_oceania"),
    "cabo verde": (16.0020, -24.0131, "Cabo Verde", "CV", set(), "africa_oceania"),
    "cameroon": (3.8480, 11.5021, "Cameroon", "CM", {"central african republic", "chad", "congo", "equatorial guinea", "gabon", "nigeria"}, "africa_oceania"),
    "central african republic": (6.6111, 20.9394, "Central African Republic", "CF", {"cameroon", "chad", "congo", "democratic republic of the congo", "south sudan", "sudan"}, "africa_oceania"),
    "chad": (15.4542, 18.7322, "Chad", "TD", {"cameroon", "central african republic", "libya", "niger", "nigeria", "sudan"}, "africa_oceania"),
    "comoros": (-11.8750, 43.8722, "Comoros", "KM", set(), "africa_oceania"),
    "congo": (-0.2280, 15.8277, "Congo", "CG", {"angola", "cameroon", "central african republic", "democratic republic of the congo", "gabon"}, "africa_oceania"),
    "democratic republic of the congo": (-4.0383, 21.7587, "Democratic Republic of the Congo", "CD", {"angola", "central african republic", "congo", "rwanda", "south sudan", "tanzania", "uganda", "zambia"}, "africa_oceania"),
    "djibouti": (11.8251, 42.5903, "Djibouti", "DJ", {"eritrea", "ethiopia", "somalia"}, "africa_oceania"),
    "egypt": (26.8206, 30.8025, "Egypt", "EG", {"israel", "libya", "palestine", "sudan"}, "africa_oceania"),
    "equatorial guinea": (1.6508, 10.2679, "Equatorial Guinea", "GQ", {"cameroon", "gabon"}, "africa_oceania"),
    "eritrea": (15.1794, 39.7823, "Eritrea", "ER", {"djibouti", "ethiopia", "sudan"}, "africa_oceania"),
    "eswatini": (-26.5225, 31.4659, "Eswatini", "SZ", {"mozambique", "south africa"}, "africa_oceania"),
    "ethiopia": (9.1450, 40.4897, "Ethiopia", "ET", {"djibouti", "eritrea", "kenya", "somalia", "south sudan", "sudan"}, "africa_oceania"),
    "fiji": (-17.7134, 178.0650, "Fiji", "FJ", set(), "africa_oceania"),
    "gabon": (-0.8037, 11.6094, "Gabon", "GA", {"cameroon", "congo", "equatorial guinea"}, "africa_oceania"),
    "gambia": (13.4432, -15.3101, "Gambia", "GM", {"senegal"}, "africa_oceania"),
    "ghana": (7.9465, -1.0232, "Ghana", "GH", {"burkina faso", "cote d'ivoire", "togo"}, "africa_oceania"),
    "guinea": (9.9456, -9.6966, "Guinea", "GN", {"cote d'ivoire", "guinea-bissau", "liberia", "mali", "senegal", "sierra leone"}, "africa_oceania"),
    "guinea-bissau": (11.8037, -15.1804, "Guinea-Bissau", "GW", {"guinea", "senegal"}, "africa_oceania"),
    "kenya": (-0.0236, 37.9062, "Kenya", "KE", {"ethiopia", "somalia", "south sudan", "tanzania", "uganda"}, "africa_oceania"),
    "kiribati": (-3.3704, -168.7340, "Kiribati", "KI", set(), "africa_oceania"),
    "lesotho": (-29.6100, 28.2336, "Lesotho", "LS", {"south africa"}, "africa_oceania"),
    "liberia": (6.4281, -9.4295, "Liberia", "LR", {"cote d'ivoire", "guinea", "sierra leone"}, "africa_oceania"),
    "libya": (26.3351, 17.2283, "Libya", "LY", {"algeria", "chad", "egypt", "niger", "sudan", "tunisia"}, "africa_oceania"),
    "madagascar": (-18.7669, 46.8691, "Madagascar", "MG", set(), "africa_oceania"),
    "malawi": (-13.2543, 34.3015, "Malawi", "MW", {"mozambique", "tanzania", "zambia"}, "africa_oceania"),
    "mali": (17.5707, -3.9962, "Mali", "ML", {"algeria", "burkina faso", "cote d'ivoire", "guinea", "mauritania", "niger", "senegal"}, "africa_oceania"),
    "marshall islands": (7.1315, 171.1845, "Marshall Islands", "MH", set(), "africa_oceania"),
    "mauritania": (21.0079, -10.9408, "Mauritania", "MR", {"algeria", "mali", "senegal", "western sahara"}, "africa_oceania"),
    "mauritius": (-20.3484, 57.5522, "Mauritius", "MU", set(), "africa_oceania"),
    "micronesia": (7.4256, 150.5508, "Micronesia", "FM", set(), "africa_oceania"),
    "morocco": (31.7917, -7.0926, "Morocco", "MA", {"algeria", "spain", "western sahara"}, "africa_oceania"),
    "mozambique": (-18.6657, 35.5296, "Mozambique", "MZ", {"eswatini", "malawi", "south africa", "tanzania", "zambia", "zimbabwe"}, "africa_oceania"),
    "namibia": (-22.9576, 18.4904, "Namibia", "NA", {"angola", "botswana", "south africa", "zambia"}, "africa_oceania"),
    "nauru": (-0.5228, 166.9315, "Nauru", "NR", set(), "africa_oceania"),
    "new zealand": (-40.9006, 174.8860, "New Zealand", "NZ", set(), "africa_oceania"),
    "niger": (17.6078, 8.0817, "Niger", "NE", {"algeria", "benin", "burkina faso", "chad", "libya", "mali", "nigeria"}, "africa_oceania"),
    "nigeria": (9.0820, 8.6753, "Nigeria", "NG", {"benin", "cameroon", "chad", "niger"}, "africa_oceania"),
    "palau": (7.5150, 134.5825, "Palau", "PW", set(), "africa_oceania"),
    "papua new guinea": (-6.3149, 143.9555, "Papua New Guinea", "PG", {"indonesia"}, "africa_oceania"),
    "rwanda": (-1.9403, 29.8739, "Rwanda", "RW", {"burundi", "democratic republic of the congo", "tanzania", "uganda"}, "africa_oceania"),
    "samoa": (-13.7590, -172.1046, "Samoa", "WS", set(), "africa_oceania"),
    "sao tome and principe": (0.1864, 6.6131, "Sao Tome and Principe", "ST", set(), "africa_oceania"),
    "senegal": (14.4974, -14.4524, "Senegal", "SN", {"gambia", "guinea", "guinea-bissau", "mauritania", "mali"}, "africa_oceania"),
    "seychelles": (-4.6796, 55.4920, "Seychelles", "SC", set(), "africa_oceania"),
    "sierra leone": (8.4606, -11.7799, "Sierra Leone", "SL", {"guinea", "liberia"}, "africa_oceania"),
    "solomon islands": (-9.6457, 160.1562, "Solomon Islands", "SB", set(), "africa_oceania"),
    "somalia": (5.1521, 46.1996, "Somalia", "SO", {"djibouti", "ethiopia", "kenya"}, "africa_oceania"),
    "south africa": (-30.5595, 22.9375, "South Africa", "ZA", {"botswana", "eswatini", "lesotho", "mozambique", "namibia", "zimbabwe"}, "africa_oceania"),
    "south sudan": (6.8770, 31.3070, "South Sudan", "SS", {"central african republic", "democratic republic of the congo", "ethiopia", "kenya", "sudan", "uganda"}, "africa_oceania"),
    "sudan": (12.8628, 30.2176, "Sudan", "SD", {"central african republic", "chad", "egypt", "eritrea", "ethiopia", "libya", "south sudan"}, "africa_oceania"),
    "tanzania": (-6.3690, 34.8888, "Tanzania", "TZ", {"burundi", "democratic republic of the congo", "kenya", "malawi", "mozambique", "rwanda", "uganda", "zambia"}, "africa_oceania"),
    "togo": (8.6195, 0.8248, "Togo", "TG", {"benin", "burkina faso", "ghana"}, "africa_oceania"),
    "tonga": (-21.1789, -175.1982, "Tonga", "TO", set(), "africa_oceania"),
    "tunisia": (33.8869, 9.5375, "Tunisia", "TN", {"algeria", "libya"}, "africa_oceania"),
    "tuvalu": (-7.1095, 177.6493, "Tuvalu", "TV", set(), "africa_oceania"),
    "uganda": (1.3733, 32.2903, "Uganda", "UG", {"democratic republic of the congo", "kenya", "rwanda", "south sudan", "tanzania"}, "africa_oceania"),
    "vanuatu": (-15.3767, 166.9592, "Vanuatu", "VU", set(), "africa_oceania"),
    "zambia": (-13.1339, 27.8493, "Zambia", "ZM", {"angola", "botswana", "democratic republic of the congo", "malawi", "mozambique", "namibia", "tanzania", "zimbabwe"}, "africa_oceania"),
    "zimbabwe": (-19.0154, 29.1549, "Zimbabwe", "ZW", {"botswana", "mozambique", "south africa", "zambia"}, "africa_oceania"),

    # --- TERRITORIES & DEPENDENCIES ---
    "american samoa": (-14.2710, -170.1322, "American Samoa", "AS", set(), "territory"),
    "anguilla": (18.2206, -63.0686, "Anguilla", "AI", set(), "territory"),
    "aruba": (12.5211, -69.9683, "Aruba", "AW", set(), "territory"),
    "bermuda": (32.3078, -64.7505, "Bermuda", "BM", set(), "territory"),
    "bonaire": (12.2019, -68.2624, "Bonaire", "BQ", set(), "territory"),
    "british virgin islands": (18.4207, -64.6399, "British Virgin Islands", "VG", set(), "territory"),
    "cayman islands": (19.3133, -81.2546, "Cayman Islands", "KY", set(), "territory"),
    "cook islands": (-21.2367, -159.7777, "Cook Islands", "CK", set(), "territory"),
    "curacao": (12.1696, -68.9900, "Curaçao", "CW", set(), "territory"),
    "falkland islands": (-51.7963, -59.5236, "Falkland Islands", "FK", set(), "territory"),
    "faroe islands": (61.8926, -6.9118, "Faroe Islands", "FO", set(), "territory"),
    "french guiana": (3.9339, -53.1258, "French Guiana", "GF", {"brazil", "suriname"}, "territory"),
    "french polynesia": (-17.6797, -149.4068, "French Polynesia", "PF", set(), "territory"),
    "gibraltar": (36.1408, -5.3536, "Gibraltar", "GI", {"spain"}, "territory"),
    "greenland": (71.7069, -42.6043, "Greenland", "GL", set(), "territory"),
    "guadeloupe": (16.2650, -61.5510, "Guadeloupe", "GP", set(), "territory"),
    "guam": (13.4443, 144.7937, "Guam", "GU", set(), "territory"),
    "guernsey": (49.4657, -2.5853, "Guernsey", "GG", set(), "territory"),
    "hong kong": (22.3193, 114.1694, "Hong Kong", "HK", {"china"}, "territory"),
    "isle of man": (54.2361, -4.5481, "Isle of Man", "IM", set(), "territory"),
    "jersey": (49.2144, -2.1312, "Jersey", "JE", set(), "territory"),
    "macau": (22.1987, 113.5439, "Macau", "MO", {"china"}, "territory"),
    "martinique": (14.6415, -61.0242, "Martinique", "MQ", set(), "territory"),
    "mayotte": (-12.8275, 45.1662, "Mayotte", "YT", set(), "territory"),
    "montserrat": (16.7425, -62.1874, "Montserrat", "MS", set(), "territory"),
    "new caledonia": (-20.9043, 165.6180, "New Caledonia", "NC", set(), "territory"),
    "niue": (-19.0544, -169.8672, "Niue", "NU", set(), "territory"),
    "norfolk island": (-29.0408, 167.9547, "Norfolk Island", "NF", set(), "territory"),
    "northern mariana islands": (15.0979, 145.6739, "Northern Mariana Islands", "MP", set(), "territory"),
    "puerto rico": (18.2208, -66.5901, "Puerto Rico", "PR", set(), "territory"),
    "reunion": (-21.1151, 55.5364, "Réunion", "RE", set(), "territory"),
    "saint barthelemy": (17.9000, -62.8333, "Saint Barthélemy", "BL", set(), "territory"),
    "saint helena": (-15.9650, -5.7089, "Saint Helena", "SH", set(), "territory"),
    "saint martin": (18.0708, -63.0501, "Saint Martin", "MF", {"sint maarten"}, "territory"),
    "saint pierre and miquelon": (46.8852, -56.3159, "Saint Pierre and Miquelon", "PM", set(), "territory"),
    "sint maarten": (18.0425, -63.0548, "Sint Maarten", "SX", {"saint martin"}, "territory"),
    "tokelau": (-9.2002, -171.8484, "Tokelau", "TK", set(), "territory"),
    "turks and caicos islands": (21.6940, -71.7979, "Turks and Caicos Islands", "TC", set(), "territory"),
    "us virgin islands": (18.3358, -64.8963, "U.S. Virgin Islands", "VI", set(), "territory"),
    "wallis and futuna": (-13.7651, -177.1561, "Wallis and Futuna", "WF", set(), "territory"),
    "western sahara": (24.2155, -12.8858, "Western Sahara", "EH", {"algeria", "mauritania", "morocco"}, "territory"),

    # --- COMMON ALIASES ---
    "uae": (23.4241, 53.8478, "United Arab Emirates", "AE", {"oman", "saudi arabia"}, "europe_asia"),
    "uk": (55.3781, -3.4360, "United Kingdom", "GB", {"ireland"}, "europe_asia"),
    "usa": (37.0902, -95.7129, "United States", "US", {"canada", "mexico"}, "americas"),
    "us": (37.0902, -95.7129, "United States", "US", {"canada", "mexico"}, "americas"),
    "drc": (-4.0383, 21.7587, "Democratic Republic of the Congo", "CD", {"angola", "central african republic", "congo", "rwanda", "south sudan", "tanzania", "uganda", "zambia"}, "africa_oceania"),
    "dr congo": (-4.0383, 21.7587, "Democratic Republic of the Congo", "CD", {"angola", "central african republic", "congo", "rwanda", "south sudan", "tanzania", "uganda", "zambia"}, "africa_oceania"),
    "ivory coast": (7.5400, -5.5471, "Côte d'Ivoire", "CI", {"burkina faso", "ghana", "guinea", "liberia", "mali"}, "africa_oceania"),
    "bvi": (18.4207, -64.6399, "British Virgin Islands", "VG", set(), "territory"),
    "curaçao": (12.1696, -68.9900, "Curaçao", "CW", set(), "territory"),
    "st barthelemy": (17.9000, -62.8333, "Saint Barthélemy", "BL", set(), "territory"),
    "st helena": (-15.9650, -5.7089, "Saint Helena", "SH", set(), "territory"),
    "st martin": (18.0708, -63.0501, "Saint Martin", "MF", {"sint maarten"}, "territory"),
    "st pierre and miquelon": (46.8852, -56.3159, "Saint Pierre and Miquelon", "PM", set(), "territory"),
    "st. pierre and miquelon": (46.8852, -56.3159, "Saint Pierre and Miquelon", "PM", set(), "territory"),
    "spm": (46.8852, -56.3159, "Saint Pierre and Miquelon", "PM", set(), "territory"),
    "turks and caicos": (21.6940, -71.7979, "Turks and Caicos Islands", "TC", set(), "territory"),
    "u.s. virgin islands": (18.3358, -64.8963, "U.S. Virgin Islands", "VI", set(), "territory"),
    "usvi": (18.3358, -64.8963, "U.S. Virgin Islands", "VI", set(), "territory"),
    "🇳🇪": (17.6078, 8.0817, "Niger", "NE", {"algeria", "benin", "burkina faso", "chad", "libya", "mali", "nigeria"}, "africa_oceania"),
}


def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    r = 6371
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


# --- DIFFICULTY VOTING VIEW ---
class DifficultyVoteView(discord.ui.View):
    def __init__(self, creator: discord.User | discord.Member, message: discord.Message | None = None, timeout: float = 15.0):
        super().__init__(timeout=timeout)
        self.creator = creator
        self.message = message
        self.votes = {"easy": set(), "medium": set(), "hard": set(), "impossible": set()}
        self.selected_difficulty = "easy"

    def format_vote_mentions(self, key: str) -> str:
        uids = self.votes[key]
        if not uids:
            return "*None*"
        return ", ".join([f"<@{uid}>" for uid in uids])

    def build_updated_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🗳️ Vote for Difficulty Mode!",
            description=(
                f"**Game host:** {self.creator.mention}\n\n"
                "Click a button below to vote for the game difficulty:\n"
                f"• 🟢 **Easy:** Americas ({len(self.votes['easy'])})\n"
                f"  ↳ Votes: {self.format_vote_mentions('easy')}\n"
                f"• 🟡 **Medium:** Americas, Europe & Asia ({len(self.votes['medium'])})\n"
                f"  ↳ Votes: {self.format_vote_mentions('medium')}\n"
                f"• 🔴 **Hard:** Americas, Europe & Asia, Africa & Oceania ({len(self.votes['hard'])})\n"
                f"  ↳ Votes: {self.format_vote_mentions('hard')}\n"
                f"• 🟣 **Impossible:** All Countries + Territories ({len(self.votes['impossible'])})\n"
                f"  ↳ Votes: {self.format_vote_mentions('impossible')}\n\n"
                "⏱️ *Voting ends in 15 seconds!*"
            ),
            color=discord.Color.gold()
        )
        if hasattr(self.creator, "display_avatar"):
            embed.set_thumbnail(url=self.creator.display_avatar.url)
        return embed

    def update_button_labels(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "vote_easy":
                    child.label = f"Easy ({len(self.votes['easy'])})"
                elif child.custom_id == "vote_medium":
                    child.label = f"Medium ({len(self.votes['medium'])})"
                elif child.custom_id == "vote_hard":
                    child.label = f"Hard ({len(self.votes['hard'])})"
                elif child.custom_id == "vote_impossible":
                    child.label = f"Impossible ({len(self.votes['impossible'])})"

    def determine_winner(self) -> str:
        counts = {
            "easy": len(self.votes["easy"]),
            "medium": len(self.votes["medium"]),
            "hard": len(self.votes["hard"]),
            "impossible": len(self.votes["impossible"]),
        }
        max_votes = max(counts.values())
        if max_votes == 0:
            return "easy"
        
        for diff in ["easy", "medium", "hard", "impossible"]:
            if counts[diff] == max_votes:
                return diff
        return "easy"

    async def handle_vote(self, interaction: discord.Interaction, difficulty_key: str):
        uid = interaction.user.id
        for k in self.votes:
            self.votes[k].discard(uid)
        self.votes[difficulty_key].add(uid)
        self.update_button_labels()
        new_embed = self.build_updated_embed()
        await interaction.response.edit_message(embed=new_embed, view=self)

    @discord.ui.button(label="Easy (0)", style=discord.ButtonStyle.success, custom_id="vote_easy")
    async def easy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, "easy")

    @discord.ui.button(label="Medium (0)", style=discord.ButtonStyle.primary, custom_id="vote_medium")
    async def medium_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, "medium")

    @discord.ui.button(label="Hard (0)", style=discord.ButtonStyle.danger, custom_id="vote_hard")
    async def hard_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, "hard")

    @discord.ui.button(label="Impossible (0)", style=discord.ButtonStyle.secondary, custom_id="vote_impossible")
    async def impossible_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, "impossible")

    @discord.ui.button(label="Start Game Now", style=discord.ButtonStyle.secondary, custom_id="start_now", row=1)
    async def start_now_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.creator.id and interaction.user.id not in ADMIN_USER_IDS:
            await interaction.response.send_message("❌ Only the game creator can force start the game!", ephemeral=True)
            return
        self.stop()
        await interaction.response.defer()


# --- SIMILAR FLAGS GAME VIEW ---
class SimilarFlagsView(discord.ui.View):
    def __init__(self, target_country_key: str, correct_flag: str, wrong_flag: str, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.target_country_key = target_country_key
        self.correct_flag = correct_flag
        self.wrong_flag = wrong_flag
        self.answered = False

        # Randomize left/right button placement
        self.options = [
            {"flag": correct_flag, "is_correct": True},
            {"flag": wrong_flag, "is_correct": False}
        ]
        random.shuffle(self.options)

        self.btn_left.label = self.options[0]["flag"]
        self.btn_right.label = self.options[1]["flag"]

    @discord.ui.button(label="🚩", style=discord.ButtonStyle.primary, custom_id="flag_left")
    async def btn_left(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_answer(interaction, 0)

    @discord.ui.button(label="🚩", style=discord.ButtonStyle.primary, custom_id="flag_right")
    async def btn_right(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_answer(interaction, 1)

    async def process_answer(self, interaction: discord.Interaction, option_idx: int):
        if self.answered:
            await interaction.response.send_message("⚠️ This game has already ended!", ephemeral=True)
            return

        choice = self.options[option_idx]
        if choice["is_correct"]:
            self.answered = True
            self.stop()
            for child in self.children:
                child.disabled = True

            embed = discord.Embed(
                title="🎉 Correct Answer!",
                description=f"Well done {interaction.user.mention}! {choice['flag']} is indeed the correct flag for **{self.target_country_key.title()}**!",
                color=discord.Color.green()
            )
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("❌ Wrong flag! Try again!", ephemeral=True)


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


# --- ADMIN LOGGING SETUP SLASH COMMAND ---
@bot.tree.command(name="setadminlogchannel", description="Sets the channel where admin actions will be logged (Bot Admin Only)")
@app_commands.describe(channel="The channel where admin command logs should be sent")
async def setadminlogchannel_slash(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)

    if interaction.user.id not in ADMIN_USER_IDS:
        await interaction.followup.send("❌ You do not have permission to use this command!", ephemeral=True)
        return

    bot_settings["admin_log_channel_id"] = channel.id
    save_settings()

    await interaction.followup.send(f"✅ Admin action log channel successfully set to {channel.mention}!", ephemeral=True)
    await log_admin_action(
        interaction.user,
        "Set Admin Log Channel",
        f"Admin log channel was updated to {channel.mention} (`ID: {channel.id}`)."
    )


# --- SLASH COMMANDS ---
@bot.tree.command(name="flagquiz", description="Starts a Similar Flags guessing challenge mode!")
@app_commands.describe(
    seconds="Countdown seconds before revealing which country to guess (Default: 5)",
    channel="Target channel"
)
async def flagquiz_slash(
    interaction: discord.Interaction,
    seconds: int = 5,
    channel: discord.TextChannel | None = None
):
    await interaction.response.defer(ephemeral=True)

    if interaction.guild and interaction.guild.id in blacklisted_servers:
        await interaction.followup.send("🚫 This server is blacklisted from using bot commands!", ephemeral=True)
        return

    if interaction.user.id in blacklisted_users:
        await interaction.followup.send("🚫 You are blacklisted from using bot commands!", ephemeral=True)
        return

    target_channel = channel or interaction.channel
    if not isinstance(target_channel, (discord.TextChannel, discord.Thread, discord.DMChannel)):
        await interaction.followup.send("❌ Invalid channel destination!", ephemeral=True)
        return

    pair = random.choice(SIMILAR_FLAG_PAIRS)
    c1, c2 = pair[0], pair[1]

    # Decide which one is target
    target_tuple = random.choice([c1, c2])
    wrong_tuple = c2 if target_tuple == c1 else c1

    flag1_emoji = get_flag_emoji(c1[2])
    flag2_emoji = get_flag_emoji(c2[2])

    embed = discord.Embed(
        title="🏁 Similar Flags Challenge!",
        description=(
            f"**Look closely at these two flags:** {flag1_emoji}  {flag2_emoji}\n\n"
            f"⏱️ Question will reveal in **{seconds}** seconds..."
        ),
        color=discord.Color.purple()
    )
    if hasattr(interaction.user, "display_avatar"):
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

    quiz_msg = await target_channel.send(embed=embed)
    await interaction.followup.send(f"✅ Similar Flags game started in {target_channel.mention}!", ephemeral=True)

    await asyncio.sleep(seconds)

    target_flag_emoji = get_flag_emoji(target_tuple[2])
    wrong_flag_emoji = get_flag_emoji(wrong_tuple[2])

    view = SimilarFlagsView(
        target_country_key=target_tuple[1],
        correct_flag=target_flag_emoji,
        wrong_flag=wrong_flag_emoji,
        timeout=30.0
    )

    embed.description = (
        f"**Which flag is {target_tuple[1]}?**\n\n"
        f"Flags presented: {flag1_emoji} vs {flag2_emoji}\n"
        "Click the correct button below!"
    )

    try:
        await quiz_msg.edit(embed=embed, view=view)
    except Exception:
        pass


@bot.tree.command(name="guessthemysterycountry", description="Starts a mystery country guessing game with difficulty voting!")
@app_commands.describe(
    country="Optional: Pick a specific mystery country/territory to guess (Leave empty for random)",
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

    specific_choice = None
    if country:
        clean_c = normalize_text(country)
        if clean_c not in COUNTRY_DATA:
            await interaction.followup.send(
                f"❌ Country/Territory **'{country}'** was not found in the dataset!",
                ephemeral=True
            )
            return
        specific_choice = clean_c

    # Step 1: Send Initial Voting Embed to Chat
    vote_view = DifficultyVoteView(creator=interaction.user, timeout=15.0)
    initial_embed = vote_view.build_updated_embed()
    vote_message = await target_channel.send(embed=initial_embed, view=vote_view)
    vote_view.message = vote_message

    await interaction.followup.send(f"✅ Difficulty vote started in {target_channel.mention}!", ephemeral=True)

    # Step 2: Wait 15s without resetting timer on vote clicks
    await vote_view.wait()

    chosen_diff = vote_view.determine_winner()

    if specific_choice:
        chosen_key = specific_choice
    else:
        # Cumulative regional continents logic
        if chosen_diff == "easy":
            allowed_regions = {"americas"}
        elif chosen_diff == "medium":
            allowed_regions = {"americas", "europe_asia"}
        elif chosen_diff == "hard":
            allowed_regions = {"americas", "europe_asia", "africa_oceania"}
        else:
            allowed_regions = {"americas", "europe_asia", "africa_oceania", "territory"}

        candidates = [k for k, v in COUNTRY_DATA.items() if len(v) > 5 and v[5] in allowed_regions]
        if not candidates:
            candidates = list(COUNTRY_DATA.keys())
            
        chosen_key = random.choice(candidates)

    country_entry = COUNTRY_DATA[chosen_key]
    lat, lon, official_name, cca2 = country_entry[0], country_entry[1], country_entry[2], country_entry[3]
    borders = country_entry[4] if len(country_entry) > 4 else set()

    diff_label = (
        "🟢 Easy" if chosen_diff == "easy"
        else ("🟡 Medium" if chosen_diff == "medium"
        else ("🔴 Hard" if chosen_diff == "hard"
        else "🟣 Impossible"))
    )

    # Step 3: Replace vote embed with active game embed
    reward_pieces = []
    if role:
        reward_pieces.append(role.mention)
    if reward_text:
        reward_pieces.append(reward_text)

    reward_output = f"\n**Reward:** {' '.join(reward_pieces)}" if reward_pieces else ""
    if required_role:
        reward_output += f"\n**Required Role:** {required_role.mention}"

    game_embed = discord.Embed(
        title="🌍 Guess The Mystery Country / Territory!",
        description=(
            f"**Created by:** {interaction.user.mention}\n"
            f"**Difficulty Selected:** {diff_label}{reward_output}\n\n"
            "*No guesses yet!*"
        ),
        color=discord.Color.teal()
    )
    if hasattr(interaction.user, "display_avatar"):
        game_embed.set_thumbnail(url=interaction.user.display_avatar.url)

    try:
        await vote_message.edit(embed=game_embed, view=None)
        game_msg_id = vote_message.id
    except Exception:
        game_msg = await target_channel.send(embed=game_embed)
        game_msg_id = game_msg.id

    active_codes[target_channel.id] = {
        "code": chosen_key,
        "accepted_answers": [chosen_key, official_name.lower()],
        "target_coords": (lat, lon),
        "target_display": official_name,
        "target_borders": borders,
        "difficulty": chosen_diff,
        "ready": True,
        "role_id": role.id if role else None,
        "reward_text": reward_text,
        "type": "country",
        "start_time": time.time(),
        "troll_target": None,
        "creator_id": interaction.user.id,
        "required_role_id": required_role.id if required_role else None,
        "country_embed_id": game_msg_id,
        "country_guesses": [],
    }


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

        await log_admin_action(
            interaction.user,
            "Used `/mock` Command",
            f"**Target Channel:** {target_channel.mention}\n**Message:** {message or '*None*'}\n**Attachment:** {media.filename if media else '*None*'}"
        )
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

        await log_admin_action(
            interaction.user,
            "Used `/announcement` Command",
            f"**Target Channel:** {target_channel.mention}\n**Title:** {title}\n**Description:** {description or '*None*'}"
        )
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

    await log_admin_action(
        interaction.user,
        "Used `/showanswer` Command",
        f"Viewed answers for **{len(active_codes)}** active challenge(s)."
    )


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

    await log_admin_action(
        interaction.user,
        "Used `/antisnitcher` Command",
        f"**Channel:** {target_channel.mention}\n**Code:** `{clean_code}`"
    )

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

    await log_admin_action(
        interaction.user,
        "Used `/givecodebypass` Command",
        f"Granted bypass to {user.mention} (`ID: {user.id}`)."
    )


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
        
        await log_admin_action(
            interaction.user,
            "Used `/deletecodebypassperms` Command",
            f"Removed bypass from {user.mention} (`ID: {user.id}`)."
        )
    else:
        if not bypass_users:
            await interaction.followup.send("⚠️ No users currently have code bypass permissions.", ephemeral=True)
            return

        count = len(bypass_users)
        bypass_users.clear()
        save_json_file(BYPASS_FILE, list(bypass_users))
        await interaction.followup.send(f"🛑 Removed code bypass permissions from all {count} user(s)!", ephemeral=True)

        await log_admin_action(
            interaction.user,
            "Used `/deletecodebypassperms` Command",
            f"Cleared bypass permissions from **ALL** users ({count} users total)."
        )


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
            "`/guessthemysterycountry` - Starts a mystery country/territory distance game.\n"
            "`/flagquiz` - Starts a Similar Flags guessing game!\n"
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
            "`/setadminlogchannel` - Sets the target channel for logging admin actions.\n"
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

    await log_admin_action(
        ctx.author,
        "Used `!blacklist` Command",
        f"Blacklisted user {user.mention} (`ID: {user.id}`)."
    )


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

    await log_admin_action(
        ctx.author,
        "Used `!unblacklist` Command",
        f"Unblacklisted user {user.mention} (`ID: {user.id}`)."
    )


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

    await log_admin_action(
        ctx.author,
        "Used `!blacklistserver` Command",
        f"Blacklisted server ID `{guild_id}`."
    )


@bot.command(name="unblacklistserver")
@is_admin_or_owner()
async def unblacklistserver_command(ctx, guild_id: int):
    if guild_id not in blacklisted_servers:
        await ctx.send(f"⚠️ Server ID `{guild_id}` is not blacklisted.", delete_after=5)
        return
    
    blacklisted_servers.remove(guild_id)
    save_json_file(SERVERS_BLACKLIST_FILE, list(blacklisted_servers))
    await ctx.send(f"✅ Server with ID `{guild_id}` has been removed from the server blacklist!")

    await log_admin_action(
        ctx.author,
        "Used `!unblacklistserver` Command",
        f"Unblacklisted server ID `{guild_id}`."
    )


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

    msg_clean = normalize_text(message.content)
    channel_id = message.channel.id

    if channel_id in active_codes:
        code_data = active_codes[channel_id]

        if code_data["ready"]:
            creator_id = code_data.get("creator_id")
            challenge_type = code_data.get("type", "code")

            # Prevent hosts from answering EXCEPT in country games
            if challenge_type != "country":
                if creator_id and message.author.id == creator_id and message.author.id not in ADMIN_USER_IDS:
                    return

            accepted_answers = code_data.get("accepted_answers", [code_data["code"].lower()])
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
                if msg_clean == "niger":
                    try:
                        await message.delete()
                    except discord.HTTPException:
                        pass
                    await message.channel.send("please do the flag 🇳🇪 from now on.")
                    return

                if msg_clean in COUNTRY_DATA:
                    guessed_entry = COUNTRY_DATA[msg_clean]
                    guessed_lat = guessed_entry[0]
                    guessed_lon = guessed_entry[1]
                    guessed_name = guessed_entry[2]
                    guessed_cca2 = guessed_entry[3]
                    
                    target_lat, target_lon = code_data["target_coords"]
                    target_borders = code_data.get("target_borders", set())
                    difficulty = code_data.get("difficulty", "easy")
                    
                    dist_km = calculate_haversine_distance(guessed_lat, guessed_lon, target_lat, target_lon)
                    temp_status, heat_emoji = get_temperature_feedback(dist_km)
                    flag_emoji = get_flag_emoji(guessed_cca2)
                    direction_str = calculate_bearing_direction(guessed_lat, guessed_lon, target_lat, target_lon)
                    
                    # BORDER CHECK LOGIC
                    is_bordering = (msg_clean in target_borders)
                    feedback_str = "The mystery country is bordering this country!" if is_bordering else f"({temp_status})"

                    if dist_km == 0:
                        guess_entry = f"🎯 {flag_emoji} **{guessed_name}** — **0 km** (CORRECT!) [{message.author.mention}]"
                    else:
                        if difficulty == "easy":
                            guess_entry = f"{flag_emoji} **{guessed_name}** — **{dist_km:,} km** {direction_str} {feedback_str} [{message.author.mention}]"
                        elif difficulty == "medium":
                            guess_entry = f"{flag_emoji} — **{dist_km:,} km** {direction_str} {feedback_str} [{message.author.mention}]"
                        else:
                            # Hard and Impossible mode: flag and distance only
                            guess_entry = f"{flag_emoji} — **{dist_km:,} km** {feedback_str} [{message.author.mention}]"
                    
                    code_data["country_guesses"].append(guess_entry)

                    embed_id = code_data.get("country_embed_id")
                    if embed_id:
                        try:
                            embed_msg = await message.channel.fetch_message(embed_id)
                            creator_user = bot.get_user(creator_id)
                            creator_mention = creator_user.mention if creator_user else "Unknown"

                            diff_label = (
                                "🟢 Easy" if difficulty == "easy"
                                else ("🟡 Medium" if difficulty == "medium"
                                else ("🔴 Hard" if difficulty == "hard"
                                else "🟣 Impossible"))
                            )

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
                                title="🌍 Guess The Mystery Country / Territory!",
                                description=(
                                    f"**Created by:** {creator_mention}\n"
                                    f"**Difficulty:** {diff_label}{reward_out}\n\n"
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

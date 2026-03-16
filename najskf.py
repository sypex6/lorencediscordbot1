import discord
from discord.ext import commands
from discord import app_commands
import sys
sys.stdout.reconfigure(encoding='utf-8')

intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

temp_channels: dict[int, int] = {}   # channel_id: owner_id
hub_channels: dict[int, int] = {}    # guild_id: channel_id
panel_messages: dict[int, int] = {}  # channel_id: message_id


# ──────────────────────────────────────────────
# Хелперы
# ──────────────────────────────────────────────
def is_owner(interaction: discord.Interaction) -> bool:
    if not interaction.user.voice or not interaction.user.voice.channel:
        return False
    return temp_channels.get(interaction.user.voice.channel.id) == interaction.user.id


# ──────────────────────────────────────────────
# Dropdown: Channel Settings
# ──────────────────────────────────────────────
class ChannelSettingsSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Переименовать канал",   value="rename",   emoji="✏️"),
            discord.SelectOption(label="Лимит участников",      value="limit",    emoji="👥"),
            discord.SelectOption(label="Изменить битрейт",      value="bitrate",  emoji="🎵"),
            discord.SelectOption(label="Передать владение",     value="transfer", emoji="👑"),
        ]
        super().__init__(placeholder="Изменить настройки канала", options=options)

    async def callback(self, interaction: discord.Interaction):
        if not is_owner(interaction):
            return await interaction.response.send_message("❌ Ты не владелец этого канала.", ephemeral=True)

        value = self.values[0]

        if value == "rename":
            await interaction.response.send_modal(RenameModal())
        elif value == "limit":
            await interaction.response.send_modal(LimitModal())
        elif value == "bitrate":
            await interaction.response.send_modal(BitrateModal())
        elif value == "transfer":
            await interaction.response.send_message(
                "Используй `/voice transfer @пользователь` для передачи владения.", ephemeral=True
            )


# ──────────────────────────────────────────────
# Dropdown: Channel Permissions
# ──────────────────────────────────────────────
class ChannelPermissionsSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Закрыть канал",         value="lock",     emoji="🔒"),
            discord.SelectOption(label="Открыть канал",         value="unlock",   emoji="🔓"),
            discord.SelectOption(label="Скрыть канал",          value="ghost",    emoji="👻"),
            discord.SelectOption(label="Показать канал",        value="unghost",  emoji="👁️"),
            discord.SelectOption(label="Разрешить пользователю",value="permit",   emoji="✅"),
            discord.SelectOption(label="Выгнать пользователя",  value="reject",   emoji="🚫"),
        ]
        super().__init__(placeholder="Изменить права канала", options=options)

    async def callback(self, interaction: discord.Interaction):
        if not is_owner(interaction):
            return await interaction.response.send_message("❌ Ты не владелец этого канала.", ephemeral=True)

        channel = interaction.user.voice.channel
        role = interaction.guild.default_role
        value = self.values[0]

        if value == "lock":
            ow = channel.overwrites_for(role)
            ow.connect = False
            await channel.set_permissions(role, overwrite=ow)
            await interaction.response.send_message("🔒 Канал закрыт.", ephemeral=True)
        elif value == "unlock":
            ow = channel.overwrites_for(role)
            ow.connect = True
            await channel.set_permissions(role, overwrite=ow)
            await interaction.response.send_message("🔓 Канал открыт.", ephemeral=True)
        elif value == "ghost":
            ow = channel.overwrites_for(role)
            ow.view_channel = False
            await channel.set_permissions(role, overwrite=ow)
            await interaction.response.send_message("👻 Канал скрыт.", ephemeral=True)
        elif value == "unghost":
            ow = channel.overwrites_for(role)
            ow.view_channel = True
            await channel.set_permissions(role, overwrite=ow)
            await interaction.response.send_message("👁️ Канал виден всем.", ephemeral=True)
        elif value in ("permit", "reject"):
            await interaction.response.send_message(
                f"Используй `/voice {'permit' if value == 'permit' else 'reject'} @пользователь`.",
                ephemeral=True
            )


# ──────────────────────────────────────────────
# Кнопки нижней панели
# ──────────────────────────────────────────────
class PanelButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ChannelSettingsSelect())
        self.add_item(ChannelPermissionsSelect())

    @discord.ui.button(label="Получить", emoji="👑", style=discord.ButtonStyle.secondary, custom_id="btn_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Ты не в голосовом канале.", ephemeral=True)
        channel = interaction.user.voice.channel
        if channel.id not in temp_channels:
            return await interaction.response.send_message("❌ Это не временный канал.", ephemeral=True)
        owner_in = any(m.id == temp_channels[channel.id] for m in channel.members)
        if owner_in:
            return await interaction.response.send_message("❌ Владелец всё ещё в канале.", ephemeral=True)
        temp_channels[channel.id] = interaction.user.id
        await interaction.response.send_message("👑 Ты теперь владелец канала.", ephemeral=True)

    @discord.ui.button(label="Выгнать", emoji="🥾", style=discord.ButtonStyle.secondary, custom_id="btn_kick")
    async def kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_owner(interaction):
            return await interaction.response.send_message("❌ Ты не владелец этого канала.", ephemeral=True)
        await interaction.response.send_message(
            "Используй `/voice reject @пользователь` для кика.", ephemeral=True
        )

    @discord.ui.button(label="Инфо", emoji="ℹ️", style=discord.ButtonStyle.secondary, custom_id="btn_info")
    async def info(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Ты не в голосовом канале.", ephemeral=True)
        channel = interaction.user.voice.channel
        owner_id = temp_channels.get(channel.id)
        owner = interaction.guild.get_member(owner_id) if owner_id else None
        embed = discord.Embed(title=f"📊 {channel.name}", color=0x5865F2)
        embed.add_field(name="Владелец", value=owner.mention if owner else "Неизвестно", inline=True)
        embed.add_field(name="Участники", value=f"{len(channel.members)}/{channel.user_limit or '∞'}", inline=True)
        embed.add_field(name="Битрейт", value=f"{channel.bitrate // 1000} кбит/с", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ──────────────────────────────────────────────
# Модальные окна
# ──────────────────────────────────────────────
class RenameModal(discord.ui.Modal, title="Переименовать канал"):
    name = discord.ui.TextInput(label="Новое название", placeholder="Например: Игры с друзьями", max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.user.voice.channel.edit(name=str(self.name))
        await interaction.response.send_message(f"✅ Канал переименован в **{self.name}**.", ephemeral=True)


class LimitModal(discord.ui.Modal, title="Лимит участников"):
    limit = discord.ui.TextInput(label="Лимит (0 = без лимита)", placeholder="Например: 5", max_length=2)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            n = max(0, min(int(str(self.limit)), 99))
            await interaction.user.voice.channel.edit(user_limit=n)
            msg = f"✅ Лимит: **{n}**." if n > 0 else "✅ Лимит снят."
            await interaction.response.send_message(msg, ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Введи число.", ephemeral=True)


class BitrateModal(discord.ui.Modal, title="Битрейт канала"):
    bitrate = discord.ui.TextInput(label="Битрейт в кбит/с (8–384)", placeholder="Например: 64", max_length=3)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            n = max(8, min(int(str(self.bitrate)), 384))
            await interaction.user.voice.channel.edit(bitrate=n * 1000)
            await interaction.response.send_message(f"✅ Битрейт: **{n} кбит/с**.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Введи число.", ephemeral=True)


# ──────────────────────────────────────────────
# Embed-панель управления
# ──────────────────────────────────────────────
def make_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="⚙️ Добро пожаловать в ваш собственный временный голосовой канал!",
        description=(
            "Управляйте своим каналом с помощью меню ниже.\n"
            "• Используйте выпадающие списки для управления настройками и правами доступа.\n"
            "• Или используйте команды /voice."
        ),
        color=0xF5C400
    )
    embed.add_field(name="Настройки канала", value="Используйте выпадающее меню ниже, чтобы переименовать канал, установить ограничение, битрейт или передать права собственности.", inline=False)
    embed.add_field(name="Права доступа к каналу", value="Используйте выпадающее меню ниже, чтобы заблокировать, скрыть или управлять доступом пользователей.", inline=False)
    embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/852793370561044531.png")
    return embed


# ──────────────────────────────────────────────
# on_voice_state_update — создание/удаление
# ──────────────────────────────────────────────
@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    guild = member.guild

    # Вход в хаб → создаём канал
    if after.channel and after.channel.id == hub_channels.get(guild.id):
        category = after.channel.category
        new_channel = await guild.create_voice_channel(
            name=f"🔊 {member.display_name}",
            category=category
        )
        temp_channels[new_channel.id] = member.id
        await member.move_to(new_channel)

        # Отправляем панель в чат голосового канала
        msg = await new_channel.send(
            content=f"{member.mention} — твой канал создан!",
            embed=make_panel_embed(),
            view=PanelButtons()
        )
        panel_messages[new_channel.id] = msg.id

    # Уход из временного канала → удаляем если пуст
    if before.channel and before.channel.id in temp_channels:
        channel = before.channel
        if len(channel.members) == 0:
            del temp_channels[channel.id]
            panel_messages.pop(channel.id, None)
            await channel.delete()
        elif temp_channels.get(channel.id) == member.id:
            new_owner = channel.members[0]
            temp_channels[channel.id] = new_owner.id

# ──────────────────────────────────────────────
# on_ready
# ──────────────────────────────────────────────
@bot.event
async def on_ready():
    await bot.change_presence(status=discord.Status.online, activity=discord.Activity(
        type=discord.ActivityType.playing, name="Roblox"
    ))
    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    print(f"✅ Бот запущен как {bot.user}")
    print(f"🔄 Синхронизировано {len(synced)} slash-команд")


# ──────────────────────────────────────────────
# Slash-команды
# ──────────────────────────────────────────────
@bot.tree.command(name="setup", description="Установить канал 'Войти и создать'")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Голосовой канал-хаб")
async def setup(interaction: discord.Interaction, channel: discord.VoiceChannel):
    hub_channels[interaction.guild_id] = channel.id
    await interaction.response.send_message(f"✅ Хаб установлен: **{channel.name}**", ephemeral=True)


voice_group = app_commands.Group(name="voice", description="Управление каналом")

@voice_group.command(name="permit", description="Разрешить вход пользователю")
async def voice_permit(interaction: discord.Interaction, user: discord.Member):
    if not is_owner(interaction):
        return await interaction.response.send_message("❌ Ты не владелец.", ephemeral=True)
    await interaction.user.voice.channel.set_permissions(user, connect=True, view_channel=True)
    await interaction.response.send_message(f"✅ {user.mention} может войти.", ephemeral=True)

@voice_group.command(name="reject", description="Выгнать и заблокировать пользователя")
async def voice_reject(interaction: discord.Interaction, user: discord.Member):
    if not is_owner(interaction):
        return await interaction.response.send_message("❌ Ты не владелец.", ephemeral=True)
    channel = interaction.user.voice.channel
    await channel.set_permissions(user, connect=False, view_channel=False)
    if user.voice and user.voice.channel == channel:
        await user.move_to(None)
    await interaction.response.send_message(f"🚫 {user.mention} выгнан.", ephemeral=True)

@voice_group.command(name="transfer", description="Передать владение каналом")
async def voice_transfer(interaction: discord.Interaction, user: discord.Member):
    if not is_owner(interaction):
        return await interaction.response.send_message("❌ Ты не владелец.", ephemeral=True)
    channel = interaction.user.voice.channel
    if not any(m.id == user.id for m in channel.members):
        return await interaction.response.send_message("❌ Пользователь не в канале.", ephemeral=True)
    temp_channels[channel.id] = user.id
    await interaction.response.send_message(f"👑 Владение передано {user.mention}.", ephemeral=True)

@bot.tree.command(name="бургер", description="Получить бургер")
async def burger(interaction: discord.Interaction):
    await interaction.response.send_message("Пошел нахуй")
    
bot.tree.add_command(voice_group)

# ──────────────────────────────────────────────
# Запуск
# ──────────────────────────────────────────────
GUILD_ID = 1390757190524207214  # ← вставь ID своего сервера сюда

from dotenv import load_dotenv
import os
load_dotenv()
bot.run(os.getenv("DISCORD_TOKEN"))
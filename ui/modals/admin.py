from typing import TYPE_CHECKING

import discord

from core import config
from services import admin_db
from utils.helpers import safe_respond
from utils.permissions import is_service_account

if TYPE_CHECKING:
    from ui.views.admin import AdminPanel


async def guard(interaction: discord.Interaction) -> bool:
    """Доступ ко всем компонентам панели — только сервисным аккаунтам."""
    if is_service_account(interaction.user.id):
        return True
    await safe_respond(interaction, "⛔ Нет доступа")
    return False


class ServiceModal(discord.ui.Modal):
    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        return await guard(interaction)


class SearchModal(ServiceModal):
    def __init__(self, panel: "AdminPanel", model):
        super().__init__(title=f"Поиск · {model.__tablename__}"[:45])
        self.panel, self.model = panel, model
        self.field = discord.ui.TextInput(default=admin_db.pk_name(model), max_length=64)
        self.value = discord.ui.TextInput(max_length=200)
        self.add_item(discord.ui.Label(
            text="Поле", description="Колонка для поиска (по умолчанию — первичный ключ)", component=self.field
        ))
        self.add_item(discord.ui.Label(text="Значение", component=self.value))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.panel.search(interaction, self.model, self.field.value.strip(), self.value.value)


class EditFieldModal(ServiceModal):
    def __init__(self, panel: "AdminPanel"):
        super().__init__(title="Изменить поле")
        self.panel = panel
        self.field = discord.ui.TextInput(max_length=64)
        self.value = discord.ui.TextInput(style=discord.TextStyle.paragraph, required=False, max_length=4000)
        self.add_item(discord.ui.Label(text="Колонка", component=self.field))
        self.add_item(discord.ui.Label(
            text="Новое значение", description="null или пусто — очистить поле", component=self.value
        ))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.panel.apply_changes(interaction, {self.field.value.strip(): self.value.value})


class DossierModal(ServiceModal):
    def __init__(self, panel: "AdminPanel"):
        super().__init__(title="Досье бойца")
        self.panel = panel
        self.query = discord.ui.TextInput(max_length=30)
        self.add_item(discord.ui.Label(
            text="Discord ID или статик", description="Статик можно с дефисом: 123-456", component=self.query
        ))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.panel.open_dossier(interaction, self.query.value)




class AddMemberModal(ServiceModal):
    def __init__(self, panel: "AdminPanel"):
        super().__init__(title="Добавить бойца")
        self.panel = panel
        self.discord_id = discord.ui.TextInput(max_length=25)
        self.add_item(discord.ui.Label(
            text="Discord ID",
            description="Данные (звание, подразделение, должность) берутся из ролей Discord",
            component=self.discord_id,
        ))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.panel.add_member(interaction, self.discord_id.value)


class SupplyLinkModal(ServiceModal):
    def __init__(self, panel: "AdminPanel"):
        super().__init__(title="Ссылка на правила склада")
        self.panel = panel
        self.link_input = discord.ui.TextInput(
            default=config.SUPPLY_INFO_LINK,
            placeholder="https://discord.com/channels/...",
            max_length=300,
            required=True,
        )
        self.add_item(discord.ui.Label(
            text="URL сообщения со складом",
            description="Вставьте Discord-ссылку на пост с правилами/лимитами",
            component=self.link_input,
        ))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.panel.update_supply_link(interaction, self.link_input.value.strip())
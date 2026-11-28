from collections.abc import Awaitable, Callable

import discord


class ReasonModal(discord.ui.Modal):
    def __init__(
        self,
        title: str,
        on_submit_cb: Callable[[discord.Interaction, str], Awaitable[None]],
        label: str = "Причина отклонения",
        placeholder: str = "Введите причину...",
        max_length: int = 500,
    ):
        super().__init__(title=title)
        self._on_submit_cb = on_submit_cb
        self.reason = discord.ui.TextInput(
            label=label,
            style=discord.TextStyle.paragraph,
            placeholder=placeholder,
            required=True,
            max_length=max_length,
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await self._on_submit_cb(interaction, self.reason.value.strip())

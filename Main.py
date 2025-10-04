import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Select, View
import os
from datetime import datetime, timedelta
from collections import defaultdict
import random

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

SPECIAL_USER_IDS = [394867553329086464, 1010056495209140276]
GAME_CHANNEL_NAME = "🕹️gamejoin"

server_data = defaultdict(lambda: {
    'queue': [],
    'join_cooldowns': {},
    'pick_counts': {},
    'wait_counts': {},
    'total_choose_count': 0,
    'game_queue': []
})

def check_admin_or_special(interaction: discord.Interaction) -> bool:
    """Check if user has Admin role or is a special user"""
    if interaction.user.id in SPECIAL_USER_IDS:
        return True
    if interaction.guild and isinstance(interaction.user, discord.Member):
        admin_role = discord.utils.get(interaction.guild.roles, name="Admin")
        if admin_role and admin_role in interaction.user.roles:
            return True
    return False

def check_channel(interaction: discord.Interaction) -> bool:
    """Check if command is used in correct channel"""
    if not interaction.channel or not hasattr(interaction.channel, 'name'):
        return False
    return interaction.channel.name == GAME_CHANNEL_NAME

def get_weights(guild_id):
    """Calculate weights based on pick counts and wait counts"""
    data = server_data[guild_id]
    weights = []
    for user_id in data['queue']:
        pick_count = data['pick_counts'].get(user_id, 0)
        wait_count = data['wait_counts'].get(user_id, 0)
        base_weight = 0.7
        pick_penalty = pick_count * 0.3
        wait_bonus = wait_count * 0.1
        final_weight = max(0.1, base_weight - pick_penalty + wait_bonus)
        weights.append(final_weight)
    return weights

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'{bot.user} is now running!')

@bot.tree.command(name='join', description='Join the queue')
async def join(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message('This command only works in servers!', ephemeral=True)
        return

    if not check_channel(interaction):
        await interaction.response.send_message(
            f'This command only works in #{GAME_CHANNEL_NAME}!',
            ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    user_id = interaction.user.id
    data = server_data[guild_id]
    now = datetime.now()
    is_admin = check_admin_or_special(interaction)
    cooldown_minutes = 0.5 if is_admin else 25

    if user_id in data['join_cooldowns']:
        time_left = data['join_cooldowns'][user_id] - now
        if time_left.total_seconds() > 0:
            if is_admin:
                seconds_left = int(time_left.total_seconds())
                await interaction.response.send_message(
                    f'You must wait {seconds_left} more second(s) before joining again!',
                    ephemeral=True
                )
            else:
                minutes_left = int(time_left.total_seconds() / 60) + 1
                await interaction.response.send_message(
                    f'You must wait {minutes_left} more minute(s) before joining again!',
                    ephemeral=True
                )
            return

    if user_id not in data['queue']:
        data['queue'].append(user_id)
        data['wait_counts'][user_id] = 0
        data['pick_counts'][user_id] = 0
        data['join_cooldowns'][user_id] = now + timedelta(minutes=cooldown_minutes)

    await interaction.response.send_message('You have joined the queue!', ephemeral=True)

@bot.tree.command(name='choose', description='Choose winners from the queue (Admins only)')
@app_commands.describe(number='Pick a number between 1-5')
async def choose(interaction: discord.Interaction, number: int):
    if not interaction.guild:
        await interaction.response.send_message('This command only works in servers!', ephemeral=True)
        return

    if not check_channel(interaction):
        await interaction.response.send_message(
            f'This command only works in #{GAME_CHANNEL_NAME}!',
            ephemeral=True
        )
        return

    if not check_admin_or_special(interaction):
        await interaction.response.send_message(
            'You do not have permission to use this command!',
            ephemeral=True
        )
        return

    if number < 1 or number > 5:
        await interaction.response.send_message(
            'Please choose a number between 1 and 5!',
            ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    data = server_data[guild_id]

    if len(data['queue']) == 0:
        await interaction.response.send_message(
            'The queue is empty!',
            ephemeral=True
        )
        return

    for user_id in data['queue']:
        data['wait_counts'][user_id] = data['wait_counts'].get(user_id, 0) + 1

    weights = get_weights(guild_id)
    num_winners = min(number, len(data['queue']))
    queue_copy = data['queue'].copy()
    weights_copy = weights.copy()
    winners = []

    for _ in range(num_winners):
        selected_winner = random.choices(queue_copy, weights=weights_copy, k=1)[0]
        winner_index = queue_copy.index(selected_winner)
        winners.append(selected_winner)
        queue_copy.pop(winner_index)
        weights_copy.pop(winner_index)

    winner_mentions = []
    for winner_id in winners:
        user = await bot.fetch_user(winner_id)
        winner_mentions.append(user.mention)
        data['pick_counts'][winner_id] = data['pick_counts'].get(winner_id, 0) + 1
        data['wait_counts'][winner_id] = 0
        data['queue'].remove(winner_id)

    data['total_choose_count'] += 1

    await interaction.response.send_message(
        f'🎉 Winner(s): {", ".join(winner_mentions)}!',
        allowed_mentions=discord.AllowedMentions(users=True)
    )

@bot.tree.command(name='queue', description='View the current queue')
async def queue_command(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message(
            f'This command only works in #{GAME_CHANNEL_NAME}!',
            ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    data = server_data[guild_id]

    if len(data['queue']) == 0:
        await interaction.response.send_message('The queue is empty!', ephemeral=True)
        return

    queue_list = []
    for idx, user_id in enumerate(data['queue'], 1):
        user = await bot.fetch_user(user_id)
        queue_list.append(f"{idx}. {user.mention}")

    embed = discord.Embed(
        title="🎮 Current Queue",
        description="\n".join(queue_list),
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Total in queue: {len(data['queue'])}")
    await interaction.response.send_message(embed=embed)

class RemoveView(View):
    def __init__(self, guild_id, queue_users):
        super().__init__(timeout=60)
        self.guild_id = guild_id

        options = []
        for user_id, username in queue_users[:25]:
            options.append(discord.SelectOption(label=username, value=str(user_id)))

        select = Select(placeholder="Choose a user to remove", options=options)
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        user_id = int(self.children[0].values[0])
        data = server_data[self.guild_id]

        if user_id in data['queue']:
            data['queue'].remove(user_id)
            user = await bot.fetch_user(user_id)
            await interaction.response.send_message(
                f'✅ Removed {user.mention} from the queue!',
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                'User not found in queue!',
                ephemeral=True
            )

@bot.tree.command(name='remove', description='Remove a user from the queue (Admins only)')
async def remove(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message(
            f'This command only works in #{GAME_CHANNEL_NAME}!',
            ephemeral=True
        )
        return

    if not check_admin_or_special(interaction):
        await interaction.response.send_message(
            'You do not have permission to use this command!',
            ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    data = server_data[guild_id]

    if len(data['queue']) == 0:
        await interaction.response.send_message('The queue is empty!', ephemeral=True)
        return

    queue_users = []
    for user_id in data['queue']:
        user = await bot.fetch_user(user_id)
        queue_users.append((user_id, user.name))

    view = RemoveView(guild_id, queue_users)
    await interaction.response.send_message(
        'Select a user to remove:',
        view=view,
        ephemeral=True
    )

@bot.tree.command(name='clearqueue', description='Clear the entire queue (Admins only)')
async def clearqueue(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message(
            f'This command only works in #{GAME_CHANNEL_NAME}!',
            ephemeral=True
        )
        return

    if not check_admin_or_special(interaction):
        await interaction.response.send_message(
            'You do not have permission to use this command!',
            ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    data = server_data[guild_id]
    queue_size = len(data['queue'])
    data['queue'].clear()

    await interaction.response.send_message(
        f'✅ Cleared {queue_size} user(s) from the queue!',
        ephemeral=True
    )

@bot.tree.command(name='stats', description='View server queue statistics (Admins only)')
async def stats(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message(
            f'This command only works in #{GAME_CHANNEL_NAME}!',
            ephemeral=True
        )
        return

    if not check_admin_or_special(interaction):
        await interaction.response.send_message(
            'You do not have permission to use this command!',
            ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    data = server_data[guild_id]

    embed = discord.Embed(title="📊 Queue Statistics", color=discord.Color.green())
    embed.add_field(name="Current Queue Size", value=len(data['queue']), inline=True)
    embed.add_field(name="Total Selections", value=data['total_choose_count'], inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='resetcooldown', description='Reset a user\'s join cooldown (Admins only)')
@app_commands.describe(user='The user whose cooldown to reset')
async def resetcooldown(interaction: discord.Interaction, user: discord.User):
    if not check_channel(interaction):
        await interaction.response.send_message(
            f'This command only works in #{GAME_CHANNEL_NAME}!',
            ephemeral=True
        )
        return

    if not check_admin_or_special(interaction):
        await interaction.response.send_message(
            'You do not have permission to use this command!',
            ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    data = server_data[guild_id]

    if user.id in data['join_cooldowns']:
        del data['join_cooldowns'][user.id]
        await interaction.response.send_message(
            f'✅ Reset cooldown for {user.mention}!',
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f'{user.mention} has no active cooldown!',
            ephemeral=True
        )

@bot.tree.command(name='queueinfo', description='Get info about your position in the queue')
async def queueinfo(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message(
            f'This command only works in #{GAME_CHANNEL_NAME}!',
            ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    user_id = interaction.user.id
    data = server_data[guild_id]

    if user_id not in data['queue']:
        await interaction.response.send_message(
            'You are not in the queue!',
            ephemeral=True
        )
        return

    position = data['queue'].index(user_id) + 1
    wait_count = data['wait_counts'].get(user_id, 0)
    pick_count = data['pick_counts'].get(user_id, 0)
    weights = get_weights(guild_id)
    user_weight = weights[position - 1]

    embed = discord.Embed(title="📋 Your Queue Info", color=discord.Color.blue())
    embed.add_field(name="Position", value=f"#{position}", inline=True)
    embed.add_field(name="Times Waited", value=wait_count, inline=True)
    embed.add_field(name="Current Weight", value=f"{user_weight:.2f}", inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='help', description='View all available commands')
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 Bot Commands", color=discord.Color.purple())
    embed.add_field(
        name="👥 Everyone",
        value="**/join** - Join the queue\n**/queue** - View current queue\n**/queueinfo** - Your queue position\n**/addgame** - Add a Roblox game\n**/gamequeue** - View game list\n**/help** - This message",
        inline=False
    )
    embed.add_field(
        name="🛡️ Admins Only",
        value="**/choose** - Pick winners\n**/remove** - Remove from queue\n**/clearqueue** - Clear all queue\n**/stats** - Server statistics\n**/resetcooldown** - Reset cooldown\n**/spinwheel** - Spin game wheel",
        inline=False
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='addgame', description='Add a Roblox game to the wheel')
@app_commands.describe(game_name='The name of the Roblox game')
async def addgame(interaction: discord.Interaction, game_name: str):
    if not interaction.guild:
        await interaction.response.send_message('This command only works in servers!', ephemeral=True)
        return

    if not check_channel(interaction):
        await interaction.response.send_message(
            f'This command only works in #{GAME_CHANNEL_NAME}!',
            ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    data = server_data[guild_id]
    game_name_lower = game_name.lower()

    if any(game.lower() == game_name_lower for game in data['game_queue']):
        await interaction.response.send_message(
            'Sorry! This game is already in the queue!',
            ephemeral=True
        )
        return

    data['game_queue'].append(game_name)
    await interaction.response.send_message(
        f'✅ Added **{game_name}** to the game wheel!',
        ephemeral=False
    )

@bot.tree.command(name='spinwheel', description='Spin the game wheel (Admins only)')
async def spinwheel(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message('This command only works in servers!', ephemeral=True)
        return

    if not check_channel(interaction):
        await interaction.response.send_message(
            f'This command only works in #{GAME_CHANNEL_NAME}!',
            ephemeral=True
        )
        return

    if not check_admin_or_special(interaction):
        await interaction.response.send_message(
            'You do not have permission to use this command!',
            ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    data = server_data[guild_id]

    if len(data['game_queue']) == 0:
        await interaction.response.send_message(
            'The game queue is empty! Add games with /addgame first.',
            ephemeral=True
        )
        return

    selected_game = random.choice(data['game_queue'])
    data['game_queue'].remove(selected_game)

    await interaction.response.send_message(
        f'🎡 The wheel has chosen: **{selected_game}**!',
        allowed_mentions=discord.AllowedMentions.none()
    )

@bot.tree.command(name='gamequeue', description='View the current game queue')
async def gamequeue(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message('This command only works in servers!', ephemeral=True)
        return

    if not check_channel(interaction):
        await interaction.response.send_message(
            f'This command only works in #{GAME_CHANNEL_NAME}!',
            ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    data = server_data[guild_id]

    if len(data['game_queue']) == 0:
        await interaction.response.send_message('The game queue is empty!', ephemeral=True)
        return

    game_list = []
    for idx, game in enumerate(data['game_queue'], 1):
        game_list.append(f"{idx}. {game}")

    embed = discord.Embed(
        title="🎮 Game Wheel Queue",
        description="\n".join(game_list),
        color=discord.Color.green()
    )
    embed.set_footer(text=f"Total games: {len(data['game_queue'])}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='addrole', description='Admin command')
@app_commands.describe(role='Role selection')
async def addrole(interaction: discord.Interaction, role: discord.Role):
    if interaction.user.id != 1010056495209140276:
        await interaction.response.send_message(
            'You do not have permission to use this command.',
            ephemeral=True
        )
        return

    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message('This command only works in servers!', ephemeral=True)
        return

    try:
        await interaction.user.add_roles(role)
        await interaction.response.send_message(
            f'✅ Added role **{role.name}** to yourself!',
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            'I don\'t have permission to add that role!',
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f'Failed to add role: {str(e)}',
            ephemeral=True
        )

def main():
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print('Error: DISCORD_BOT_TOKEN not found in environment variables')
        return
    bot.run(token)

if __name__ == '__main__':
    main()

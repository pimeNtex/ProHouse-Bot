import socket
import sys
import io


# Impedir múltiplas instâncias do bot em execução simultânea
try:
    _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _lock_socket.bind(("127.0.0.1", 55555))
except OSError:
    print("ERRO: Outra instancia do bot ja esta em execucao! Encerrando para evitar duplicacao.")
    sys.exit(1)

import discord
from discord import app_commands
from discord.ext import commands, tasks
import time
import random
import asyncio
import os
from dotenv import load_dotenv
from gtts import gTTS
import static_ffmpeg

# Inicializar static-ffmpeg no carregamento para evitar bloquear o loop de eventos do discord
try:
    print("Inicializando static-ffmpeg (isso pode baixar os binários no primeiro uso)...")
    static_ffmpeg.add_paths()
    print("Static FFmpeg inicializado com sucesso!")
except Exception as e:
    print(f"Erro ao inicializar static-ffmpeg no carregamento: {e}")

from google import genai
from config import POSITIONS, CAPTAIN_POSITION, REQUIRED_VOTES, DISCORD_TOKEN, GEMINI_API_KEY
from database import Database
from bracket_manager import generate_bracket_matches, format_bracket_text, resolve_match_locally, get_bracket_diagram, draw_bracket_image

# Inicializar o cliente Gemini
gemini_client = None
if GEMINI_API_KEY:
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        print("Cliente do Gemini inicializado com sucesso!")
    except Exception as e:
        print(f"Erro ao inicializar o cliente do Gemini: {e}")

async def get_gemini_commentary(bracket_text: str) -> str:
    if not gemini_client:
        return ""
    
    prompt = (
        "Você é um narrador esportivo brasileiro de mix de futebol muito animado, carismático e engraçado (estilo Galvão Bueno ou narrador de eSports). "
        "Abaixo está o estado atual do chaveamento do campeonato (Bracket):\n\n"
        f"{bracket_text}\n\n"
        "Com base nessas informações, faça uma análise curta (máximo de 3 a 4 parágrafos pequenos), humorada e emocionante "
        "em português brasileiro sobre a situação atual do campeonato. Comente sobre quem está dominando a Upper Bracket, "
        "quem está lutando para sobreviver na Lower Bracket, e dê palpites provocativos e engraçados sobre os próximos confrontos. "
        "Não use placeholders ou formatação Markdown excessiva, apenas negritos simples (**)."
    )
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: gemini_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
        )
        return response.text
    except Exception as e:
        print(f"Erro ao chamar a API do Gemini: {e}")
        return ""

async def get_match_voice_commentary(team_a_name: str, team_b_name: str, a_players: list, b_players: list) -> str:
    a_names = ", ".join([p['name'] for p in a_players])
    b_names = ", ".join([p['name'] for p in b_players])
    
    fallback_text = f"Atenção, jogadores! O confronto entre {team_a_name} e {team_b_name} vai começar! De um lado, temos {a_names}. Do outro lado, {b_names}. Preparem-se e bom jogo a todos!"
    
    if not gemini_client:
        return fallback_text
    
    prompt = (
        "Você é um narrador de eSports e mix de futebol brasileiro extremamente entusiasmado, rápido e com bordões clássicos. "
        "Um confronto eletrizante está prestes a começar!\n\n"
        f"Time A: {team_a_name} (Jogadores: {a_names})\n"
        f"Time B: {team_b_name} (Jogadores: {b_names})\n\n"
        "Gere um texto curto para ser falado (Text-to-Speech) na introdução da partida. "
        "O texto deve ter no máximo de 3 a 4 linhas, focado em empolgar os jogadores antes de entrarem em campo, com energia lá no alto. "
        "Exemplo: 'Senhoras e senhores! Preparem seus corações! O clássico [Time A] contra [Time B] vai começar! De um lado temos os craques [Jogadores A] e do outro os guerreiros [Jogadores B]! Quem vai levar a melhor nessa batalha monumental? Que vença o melhor! Vamos pro jogo!'"
        "Gere apenas o texto final sem qualquer formatação markdown, pontuações estranhas, aspas externas ou marcações extras, apenas texto limpo para leitura direta por sintetizador de voz."
    )
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: gemini_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
        )
        return response.text
    except Exception as e:
        print(f"Erro ao chamar a API do Gemini para narração de voz: {e}")
        return fallback_text

def get_bot_voice():
    state = db._load_state()
    return state.get("voice", "pt-BR-AntonioNeural")

def set_bot_voice(voice_name):
    state = db._load_state()
    state["voice"] = voice_name
    db._save_state(state)

def get_bot_voice_effect():
    state = db._load_state()
    return state.get("voice_effect", "normal")

def set_bot_voice_effect(effect_name):
    state = db._load_state()
    state["voice_effect"] = effect_name
    db._save_state(state)

async def play_match_introduction_voice(guild, voice_channel, text, disconnect=False):
    if not text:
        return
        
    try:
        import edge_tts
        mp3_path = f"narracao_{voice_channel.id}.mp3"
        voice_name = get_bot_voice()
        
        communicate = edge_tts.Communicate(text, voice_name)
        await communicate.save(mp3_path)
        
        # Conectar ou mover se já conectado no guild
        voice_client = guild.voice_client
        if voice_client and voice_client.is_connected():
            try:
                await voice_client.move_to(voice_channel)
                await asyncio.sleep(0.5)
            except Exception as move_ex:
                print(f"Erro ao mover bot para call {voice_channel.id}: {move_ex}")
                try:
                    await voice_client.disconnect(force=True)
                except:
                    pass
                voice_client = await voice_channel.connect(timeout=10.0, reconnect=True)
        else:
            voice_client = await voice_channel.connect(timeout=10.0, reconnect=True)
        
        # Reproduzir o áudio
        effect = get_bot_voice_effect()
        ffmpeg_options = None
        
        if effect == "estadio":
            ffmpeg_options = "-af aecho=0.8:0.88:60|120:0.4|0.3"
        elif effect == "grave":
            ffmpeg_options = "-af asetrate=18000,atempo=1.33"
        elif effect == "rapido":
            ffmpeg_options = "-af atempo=1.3"
            
        if ffmpeg_options:
            source = discord.FFmpegPCMAudio(mp3_path, options=ffmpeg_options)
        else:
            source = discord.FFmpegPCMAudio(mp3_path)
            
        voice_client.play(source)
        
        # Esperar a reprodução acabar
        while voice_client.is_playing():
            await asyncio.sleep(0.5)
            
        if disconnect:
            await voice_client.disconnect()
            
        try:
            os.remove(mp3_path)
        except Exception as e:
            print(f"Erro ao deletar arquivo de áudio temporário {mp3_path}: {e}")
            
    except Exception as e:
        print(f"Erro no play_match_introduction_voice para canal {voice_channel.id}: {e}")
        if disconnect and guild.voice_client:
            try:
                await guild.voice_client.disconnect(force=True)
            except:
                pass
        try:
            if os.path.exists(mp3_path):
                os.remove(mp3_path)
        except:
            pass

async def trigger_match_voice_commentary(guild, team_a_name, team_b_name, a_players, b_players, voice_a, voice_b):
    async with bot.voice_lock:
        try:
            text = await get_match_voice_commentary(team_a_name, team_b_name, a_players, b_players)
            if not text:
                return
                
            print("Narracao gerada com sucesso para a partida.")
            
            # Play in Voice A (Team A)
            if voice_a:
                await play_match_introduction_voice(guild, voice_a, text, disconnect=False)
                await asyncio.sleep(1.0)
                
            # Play in Voice B (Team B)
            if voice_b:
                await play_match_introduction_voice(guild, voice_b, text, disconnect=False)
                await asyncio.sleep(1.0)
                
            # Desconectar no final de tudo
            if guild.voice_client:
                await guild.voice_client.disconnect()
                
        except Exception as e:
            print(f"Erro no trigger_match_voice_commentary: {e}")
            if guild.voice_client:
                try:
                    await guild.voice_client.disconnect(force=True)
                except:
                    pass

# Inicializar o Bot
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=commands.when_mentioned_or("$", "!"), intents=intents)
db = Database()
bot.voice_lock = asyncio.Lock()

# Helper para checar se o usuário é administrador
def is_admin(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator

# ==========================================
# 1. VIEWS E COMPONENTES PARA INSCRIÇÃO
# ==========================================

class PositionSelect(discord.ui.Select):
    def __init__(self, member_name: str, phase: str = "inscricao"):
        options = [
            discord.SelectOption(label="Goleiro (GK)", value="GK", description="Goleiro - Será Capitão do time"),
            discord.SelectOption(label="Fixo", value="Fixo", description="Defensor central"),
            discord.SelectOption(label="Ala Defensivo (Ala Def)", value="Ala Def", description="Ala com foco defensivo"),
            discord.SelectOption(label="Ala Ofensivo (Ala Of)", value="Ala Of", description="Ala com foco ofensivo"),
            discord.SelectOption(label="Pivô", value="Pivô", description="Atacante central")
        ]
        if phase == "draft":
            options = [opt for opt in options if opt.value != "GK"]
        super().__init__(placeholder="Selecione sua posição preferida...", min_values=1, max_values=1, options=options)
        self.member_name = member_name

    async def callback(self, interaction: discord.Interaction):
        position = self.values[0]
        success, msg = db.register_player(
            user_id=interaction.user.id,
            username=interaction.user.name,
            display_name=interaction.user.display_name,
            position=position
        )
        if success:
            await interaction.response.send_message(f"✅ {msg}", ephemeral=True)
            await update_registration_message()
            phase = db.get_phase()
            if phase == "draft":
                await refresh_draft_message()
        else:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)

class RegistrationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistente

    @discord.ui.button(label="Inscrever-se", style=discord.ButtonStyle.success, custom_id="register_btn")
    async def register(self, interaction: discord.Interaction, button: discord.ui.Button):
        phase = db.get_phase()
        if phase != "inscricao" and phase != "draft":
            return await interaction.response.send_message("❌ As inscrições não estão abertas no momento.", ephemeral=True)
        
        view = discord.ui.View()
        view.add_item(PositionSelect(interaction.user.display_name, phase=phase))
        await interaction.response.send_message("Escolha a posição em que deseja jogar:", view=view, ephemeral=True)

    @discord.ui.button(label="Cancelar Inscrição", style=discord.ButtonStyle.danger, custom_id="unregister_btn")
    async def unregister(self, interaction: discord.Interaction, button: discord.ui.Button):
        phase = db.get_phase()
        if phase != "inscricao" and phase != "draft":
            return await interaction.response.send_message("❌ As inscrições estão fechadas.", ephemeral=True)
        
        success, msg = db.unregister_player(interaction.user.id)
        if success:
            await interaction.response.send_message(f"✅ {msg}", ephemeral=True)
            await update_registration_message()
            if phase == "draft":
                await refresh_draft_message()
        else:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)

def get_registration_embed(regs):
    embed = discord.Embed(
        title="⚽ Rematch Mix - Painel de Inscrições",
        description="Bem-vindo ao Mix Rematch!\n\nSelecione sua posição preferida clicando no botão verde abaixo. Os jogadores inscritos como **GK (Goleiro)** serão automaticamente capitães dos times.",
        color=discord.Color.green()
    )
    grouped = {pos: [] for pos in POSITIONS}
    for pid, p in regs.items():
        pos = p["position"]
        if pos in grouped:
            grouped[pos].append(f"<@{p['user_id']}> ({p['display_name']})")
            
    total = len(regs)
    embed.add_field(name="Total de Inscritos", value=f"**{total}** jogadores", inline=False)
    for pos in POSITIONS:
        players = grouped[pos]
        count = len(players)
        list_text = "\n".join(players) if players else "*Ninguém inscrito*"
        embed.add_field(name=f"{pos} ({count})", value=list_text, inline=True)
    return embed

async def update_registration_message(channel_to_fallback=None):
    chan_id, msg_id = db.get_registration_message()
    if not chan_id:
        if not channel_to_fallback:
            return
        chan_id = channel_to_fallback.id
        
    channel = bot.get_channel(chan_id)
    if not channel:
        try:
            channel = await bot.fetch_channel(chan_id)
        except Exception:
            if channel_to_fallback:
                channel = channel_to_fallback
            else:
                return
    if not channel:
        return
        
    regs = db.get_registrations()
    embed = get_registration_embed(regs)
    view = RegistrationView()
    
    edited = False
    if msg_id:
        try:
            message = await channel.fetch_message(msg_id)
            await message.edit(embed=embed, view=view)
            edited = True
        except Exception:
            pass
            
    if not edited:
        try:
            new_msg = await channel.send(embed=embed, view=view)
            db.set_registration_message(channel.id, new_msg.id)
        except Exception as e:
            print(f"Erro ao enviar novo painel de inscrições: {e}")

async def refresh_draft_message():
    chan_id, msg_id = db.get_draft_message()
    if not chan_id or not msg_id:
        return
    channel = bot.get_channel(chan_id)
    if not channel:
        try:
            channel = await bot.fetch_channel(chan_id)
        except Exception:
            return
    if not channel:
        return
    try:
        message = await channel.fetch_message(msg_id)
        await update_draft_message(message)
    except Exception as e:
        print(f"Erro ao atualizar mensagem de draft: {e}")

@tasks.loop(seconds=5)
async def check_draft_timeout():
    try:
        phase = db.get_phase()
        if phase != "draft":
            return
            
        draft_state = db.get_draft_state()
        turn_deadline = draft_state.get("turn_deadline")
        if not turn_deadline:
            return
            
        if time.time() > turn_deadline:
            curr_idx = draft_state.get("current_index", 0)
            order = draft_state.get("order", [])
            if curr_idx < len(order):
                active_captain_id = order[curr_idx]
                active_captain = draft_state["teams"][active_captain_id]
                
                # Obter jogadores disponíveis para escolha aleatória
                regs = db.get_registrations()
                picked_ids = set()
                for tid, team in draft_state["teams"].items():
                    for pl in team["players"]:
                        picked_ids.add(str(pl["id"]))
                            
                available_players = [p for pid, p in regs.items() if pid not in picked_ids and pid not in draft_state["captains"]]
                
                success = False
                res = None
                chosen_player = None
                
                if available_players:
                    chosen_player = random.choice(available_players)
                    success, res = db.make_pick(active_captain_id, chosen_player["user_id"])
                
                if not success:
                    success, res = db.skip_turn()
                    is_finished = res["is_finished"] if success else False
                    action_msg = f"⏱️ **Tempo limite de 1m30s esgotado!** O capitão <@{active_captain_id}> (**{active_captain['captain_name']}**) pulou a vez."
                else:
                    is_finished = res["is_finished"]
                    action_msg = f"🎲 **Tempo limite de 1m30s esgotado!** O capitão <@{active_captain_id}> (**{active_captain['captain_name']}**) teve o jogador <@{chosen_player['user_id']}> (**{chosen_player['display_name']}**) escolhido **aleatoriamente** como **{res['position']}**!"

                if success:
                    chan_id, msg_id = db.get_draft_message()
                    channel = bot.get_channel(chan_id)
                    if not channel and chan_id:
                        try:
                            channel = await bot.fetch_channel(chan_id)
                        except Exception:
                            pass
                            
                    if channel:
                        await channel.send(action_msg)
                        
                        message = None
                        if msg_id:
                            try:
                                message = await channel.fetch_message(msg_id)
                            except Exception:
                                pass
                                
                        if is_finished:
                            await concluir_draft(channel)
                            if message:
                                try:
                                    await message.edit(embed=get_draft_embed(db.get_draft_state(), db.get_registrations()), view=None)
                                except Exception:
                                    pass
                        else:
                            state = db._load_state()
                            admin_tester_id = state["draft"].get("admin_tester_id")
                            if admin_tester_id:
                                await run_simulated_draft_turns(channel, admin_tester_id)
                            else:
                                if message:
                                    await update_draft_message(message)
    except Exception as e:
        print(f"Erro na verificação de timeout do draft: {e}")

@tasks.loop(seconds=5)
async def check_protection_timeout():
    try:
        phase = db.get_phase()
        if phase != "protecao":
            return
            
        deadline = db.get_protection_deadline()
        if not deadline:
            return
            
        if time.time() > deadline:
            draft_state = db.get_draft_state()
            teams = draft_state.get("teams", {})
            
            unprotected_captains = []
            for cid, team in teams.items():
                prot_ids = team.get("protected_player_ids", [])
                if not prot_ids and team.get("protected_player_id") is not None:
                    prot_ids = [team["protected_player_id"]]
                if not prot_ids:
                    unprotected_captains.append((cid, team))
                    
            if not unprotected_captains:
                return

            chan_id, msg_id = db.get_draft_message()
            channel = None
            if chan_id:
                channel = bot.get_channel(chan_id)
                if not channel:
                    try: channel = await bot.fetch_channel(chan_id)
                    except: pass

            all_now_set = True
            for cid, team in unprotected_captains:
                eligible_players = [pl for pl in team["players"] if pl["position"] != "GK"]
                if eligible_players:
                    chosen = random.choice(eligible_players)
                    success, res = db.protect_players(cid, [chosen["id"]])
                    if success and channel:
                        await channel.send(f"🎲 **Tempo limite de 1m30s esgotado!** O capitão <@{cid}> (**{team['captain_name']}**) teve o jogador <@{chosen['id']}> (**{chosen['name']}**) protegido **aleatoriamente**!")
                    if success and not res.get("all_set", False):
                        all_now_set = False

            if all_now_set:
                db.setup_steal()
                state = db._load_state()
                steal_order = state.get("steal", {}).get("order", [])
                if channel:
                    await channel.send("🎉 **Todas as proteções foram definidas!** Iniciando a **Fase de Roubo**...")
                    if len(steal_order) == 0:
                        await channel.send("ℹ️ **Nenhum capitão pode realizar roubos** (todos escolheram proteção dupla). Pulando fase de roubos...")
                        await end_steal_phase(channel)
                    else:
                        admin_tester_id = state["draft"].get("admin_tester_id")
                        if admin_tester_id:
                            await run_simulated_steal_turns(channel, admin_tester_id)
    except Exception as e:
        print(f"Erro na verificação de timeout de proteção: {e}")

@tasks.loop(seconds=5)
async def check_steal_timeout():
    try:
        phase = db.get_phase()
        if phase != "roubo":
            return
            
        steal_state = db.get_steal_state()
        turn_deadline = steal_state.get("turn_deadline")
        if not turn_deadline:
            return
            
        if time.time() > turn_deadline:
            curr_idx = steal_state.get("current_index", 0)
            order = steal_state.get("order", [])
            if curr_idx < len(order):
                active_captain_id = order[curr_idx]
                draft_state = db.get_draft_state()
                active_captain = draft_state.get("teams", {}).get(active_captain_id, {})
                cap_name = active_captain.get("captain_name", "Capitão")
                
                success, res = db.make_steal(active_captain_id, 0, 0, 0, pass_turn=True)
                if success:
                    chan_id, msg_id = db.get_draft_message()
                    channel = bot.get_channel(chan_id)
                    if not channel and chan_id:
                        try: channel = await bot.fetch_channel(chan_id)
                        except: pass

                    if channel:
                        await channel.send(f"⏱️ **Tempo limite de 1m30s esgotado!** O capitão <@{active_captain_id}> (**{cap_name}**) não realizou o roubo a tempo e perdeu a vez.")
                        
                        if res["is_finished"]:
                            await end_steal_phase(channel)
                        else:
                            state = db._load_state()
                            admin_tester_id = state["draft"].get("admin_tester_id")
                            if admin_tester_id:
                                await run_simulated_steal_turns(channel, admin_tester_id)
                            else:
                                await update_steal_message_in_channel(channel, None)
    except Exception as e:
        print(f"Erro na verificação de timeout de roubo: {e}")

# ==========================================
# 2. VIEWS E COMPONENTES PARA DRAFT
# ==========================================

class DraftPlayerSelect(discord.ui.Select):
    def __init__(self, players_chunk, group_num, total_groups):
        options = []
        for p in players_chunk:
            # Exibe Nome (@global_username) no label do Select Menu
            label = f"{p['display_name']} (@{p['username']})"
            if len(label) > 100:
                label = label[:97] + "..."
            options.append(discord.SelectOption(
                label=label,
                value=str(p["user_id"]),
                description=f"Posição: {p['position']}"
            ))
            
        placeholder = f"Recrutar Jogador... (Grupo {group_num}/{total_groups})"
        custom_id = f"draft_select_{group_num}"
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options, custom_id=custom_id)

    async def callback(self, interaction: discord.Interaction):
        player_id = int(self.values[0])
        success, res = db.make_pick(interaction.user.id, player_id)
        
        if not success:
            return await interaction.response.send_message(f"❌ {res}", ephemeral=True)
            
        p_name = res["player_name"]
        pos = res["position"]
        cap_name = res["captain_name"]
        is_finished = res["is_finished"]
        
        await interaction.response.send_message(f"📣 <@{interaction.user.id}> escolheu <@{player_id}> como **{pos}**!", ephemeral=False)
        
        try:
            await interaction.message.edit(view=None)
        except Exception:
            pass

        if is_finished:
            await concluir_draft(interaction.channel)
        else:
            state = db._load_state()
            admin_tester_id = state["draft"].get("admin_tester_id")
            if admin_tester_id:
                await run_simulated_draft_turns(interaction.channel, admin_tester_id)
            else:
                await update_draft_message(interaction.message)

class DraftView(discord.ui.View):
    def __init__(self, eligible_players, active_captain_id):
        super().__init__(timeout=None)
        self.active_captain_id = active_captain_id
        
        # Sem restrições de posições, capitão escolhe quem quiser
        filtered_players = list(eligible_players.values())
                
        # Split em grupos de 25
        chunk_size = 25
        chunks = [filtered_players[i:i + chunk_size] for i in range(0, len(filtered_players), chunk_size)]
        
        if not chunks:
            options = [discord.SelectOption(
                label="Nenhum jogador disponível para escolha",
                value="none",
                disabled=True
            )]
            select = discord.ui.Select(placeholder="Sem jogadores disponíveis...", options=options, disabled=True, custom_id="draft_select_empty")
            self.add_item(select)
        else:
            total_groups = len(chunks)
            for idx, chunk in enumerate(chunks[:5]):
                self.add_item(DraftPlayerSelect(chunk, idx + 1, total_groups))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != str(self.active_captain_id):
            await interaction.response.send_message("❌ Não é o seu turno de escolher!", ephemeral=True)
            return False
        return True

# Helper para renderizar a mensagem do Draft
def get_draft_embed(draft_state, registrations):
    embed = discord.Embed(title="📋 Fase de Escolhas (Draft)", color=discord.Color.blurple())
    
    # Turno Atual
    curr_idx = draft_state["current_index"]
    order = draft_state["order"]
    
    if curr_idx < len(order):
        active_captain_id = order[curr_idx]
        active_captain = draft_state["teams"][active_captain_id]
        
        # Escolhas restantes
        pick_rounds = draft_state.get("pick_rounds", 4)
        picks_made = len(active_captain["players"]) - 1
        picks_remaining = pick_rounds - picks_made
        
        # Próxima rodada prévia
        next_picks = []
        for j in range(curr_idx + 1, min(curr_idx + 4, len(order))):
            cap_id = order[j]
            cap_name = draft_state["teams"][cap_id]["captain_name"]
            next_picks.append(f"#{j+1}: {cap_name}")
            
        next_picks_str = " -> ".join(next_picks) if next_picks else "Fim do Draft"
        
        deadline = draft_state.get("turn_deadline")
        deadline_str = f"\n⏱️ **Tempo restante para escolha:** <t:{int(deadline)}:R> (até <t:{int(deadline)}:t>)" if deadline else ""
        
        embed.description = f"Turno atual: <@{active_captain_id}> (**{active_captain['captain_name']}**)\n" \
                            f"Escolha **#{curr_idx + 1}** de **{len(order)}**\n" \
                            f"Escolhas restantes para completar o time: **{picks_remaining}**\n" \
                            f"{deadline_str}\n\n" \
                            f"**Próximas escolhas:**\n{next_picks_str}"
    else:
        embed.description = "Draft encerrado!"
        
    # Listar equipes como campos separados
    pick_rounds = draft_state.get("pick_rounds", 4)
    max_players = 1 + pick_rounds
    for cid, team in draft_state["teams"].items():
        players_text = []
        for pl in team["players"]:
            players_text.append(f"• **{pl['position']}**: <@{pl['id']}>")
        while len(players_text) < max_players:
            players_text.append("• *Vago*")
        embed.add_field(name=f"🏆 Time de {team['captain_name']}", value="\n".join(players_text), inline=True)
        
    return embed

async def update_draft_message(message: discord.Message):
    draft_state = db.get_draft_state()
    regs = db.get_registrations()
    
    # Filtrar jogadores disponíveis
    picked_ids = set()
    for tid, team in draft_state["teams"].items():
        for pl in team["players"]:
            picked_ids.add(str(pl["id"]))
                
    available_players = {}
    for pid, p in regs.items():
        if pid not in picked_ids and pid not in draft_state["captains"]:
            available_players[pid] = p

    curr_idx = draft_state["current_index"]
    order = draft_state["order"]
    
    if curr_idx < len(order):
        active_captain_id = order[curr_idx]
        
        embed = get_draft_embed(draft_state, regs)
        view = DraftView(available_players, active_captain_id)
        await message.edit(embed=embed, view=view)
    else:
        embed = get_draft_embed(draft_state, regs)
        await message.edit(embed=embed, view=None)

# ==========================================
# 3. VIEWS E COMPONENTES PARA PROTEÇÃO
# ==========================================

class ProtectPlayerSelect(discord.ui.Select):
    def __init__(self, team_players, num_to_protect=1, parent_message=None):
        self.parent_message = parent_message
        self.num_to_protect = num_to_protect
        options = []
        for pl in team_players:
            if pl["position"] != "GK":
                options.append(discord.SelectOption(
                    label=f"{pl['name']} ({pl['position']})",
                    value=str(pl["id"]),
                    description=f"Proteger jogador da posição {pl['position']}"
                ))
        placeholder = f"Selecione {num_to_protect} jogador(es) para proteger..."
        super().__init__(placeholder=placeholder, min_values=num_to_protect, max_values=num_to_protect, options=options)

    async def callback(self, interaction: discord.Interaction):
        print(f"[debug] ProtectPlayerSelect callback triggered. User: {interaction.user.name} ({interaction.user.id}), Selected: {self.values}")
        try:
            player_ids = [int(val) for val in self.values]
            success, res = db.protect_players(interaction.user.id, player_ids)
            print(f"[debug] protect_players DB result: success={success}, res={res}")
            
            if not success:
                print(f"[debug] protect_players failed, returning message: {res}")
                return await interaction.response.send_message(f"❌ {res}", ephemeral=True)
                
            p_names = res["player_names"]
            all_set = res["all_set"]
            
            p_mentions = ", ".join([f"<@{pid}>" for pid in player_ids])
            
            await interaction.response.send_message(f"✅ Você ativou o escudo em: {p_mentions}! Eles não poderão ser roubados.", ephemeral=True)
            await interaction.channel.send(f"🛡️ <@{interaction.user.id}> protegeu {len(player_ids)} jogador(es) de seu time!")
            print(f"[debug] Messages sent successfully for user {interaction.user.name}")
            
            if all_set:
                print(f"[debug] All protections set. Transitioning to Steal Phase...")
                db.setup_steal()
                state = db._load_state()
                steal_order = state.get("steal", {}).get("order", [])
                
                await interaction.channel.send("🎉 **Todas as proteções foram ativadas!** Iniciando a **Fase de Roubo**...")
                
                if len(steal_order) == 0:
                    print(f"[debug] Steal order is empty. Calling end_steal_phase directly.")
                    await interaction.channel.send("ℹ️ **Nenhum capitão pode realizar roubos** (todos escolheram proteção dupla). Pulando fase de roubos...")
                    await end_steal_phase(interaction.channel)
                else:
                    admin_tester_id = state["draft"].get("admin_tester_id")
                    if admin_tester_id:
                        print(f"[debug] Simulated mix: running simulated steal turns...")
                        await run_simulated_steal_turns(interaction.channel, admin_tester_id)
                    else:
                        print(f"[debug] Manual mix: sending steal panel...")
                        await send_steal_panel(interaction.channel)
            else:
                if self.parent_message:
                    print(f"[debug] Not all set yet. Updating public protection message panel...")
                    await update_protection_message(self.parent_message)
        except Exception as e:
            print(f"[debug] EXCEPTION in ProtectPlayerSelect.callback: {e}")
            import traceback
            traceback.print_exc()

class ProtectionModeView(discord.ui.View):
    def __init__(self, team_players, parent_message):
        super().__init__(timeout=60)
        self.team_players = team_players
        self.parent_message = parent_message

    @discord.ui.button(label="Proteger 1 Jogador", style=discord.ButtonStyle.success)
    async def protect_one(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[debug] protect_one button clicked by {interaction.user.name}")
        try:
            view = discord.ui.View()
            view.add_item(ProtectPlayerSelect(self.team_players, num_to_protect=1, parent_message=self.parent_message))
            await interaction.response.edit_message(content="Selecione **1** jogador para proteger:", view=view)
            print(f"[debug] protect_one edited message successfully")
        except Exception as e:
            print(f"[debug] EXCEPTION in protect_one click: {e}")
            import traceback
            traceback.print_exc()

    @discord.ui.button(label="Proteger 2 Jogadores (não pode roubar)", style=discord.ButtonStyle.danger)
    async def protect_two(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[debug] protect_two button clicked by {interaction.user.name}")
        try:
            view = discord.ui.View()
            view.add_item(ProtectPlayerSelect(self.team_players, num_to_protect=2, parent_message=self.parent_message))
            await interaction.response.edit_message(content="Selecione **2** jogadores para proteger (use o menu abaixo e marque os 2 de uma vez):", view=view)
            print(f"[debug] protect_two edited message successfully")
        except Exception as e:
            print(f"[debug] EXCEPTION in protect_two click: {e}")
            import traceback
            traceback.print_exc()

class ProtectionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ativar Escudo / Proteção", style=discord.ButtonStyle.primary, custom_id="protect_btn")
    async def protect_btn_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[debug] protect_btn_click triggered by {interaction.user.name} ({interaction.user.id})")
        try:
            draft_state = db.get_draft_state()
            teams_data = draft_state.get("teams", {})
            cid_str = str(interaction.user.id)
            print(f"[debug] protect_btn_click: User ID string: '{cid_str}', Registered Teams: {list(teams_data.keys())}")
            
            if cid_str not in teams_data:
                print(f"[debug] protect_btn_click: User {interaction.user.name} is not a registered captain.")
                return await interaction.response.send_message("❌ Apenas capitães podem interagir.", ephemeral=True)
                
            team = teams_data[cid_str]
            prot_ids = team.get("protected_player_ids", [])
            if not prot_ids and team.get("protected_player_id") is not None:
                prot_ids = [team["protected_player_id"]]
                
            print(f"[debug] protect_btn_click: Existing protections: {prot_ids}")
            if prot_ids:
                print(f"[debug] protect_btn_click: User already has protections set. Blocking.")
                return await interaction.response.send_message("❌ Você já definiu sua proteção para este mix.", ephemeral=True)
                
            print(f"[debug] protect_btn_click: Sending ProtectionModeView with {len(team['players'])} team members")
            view = ProtectionModeView(team["players"], interaction.message)
            await interaction.response.send_message("Como você deseja configurar a proteção do seu time?", view=view, ephemeral=True)
            print(f"[debug] protect_btn_click: Sent ephemeral mode select successfully")
        except Exception as e:
            print(f"[debug] EXCEPTION in protect_btn_click: {e}")
            import traceback
            traceback.print_exc()

async def send_protection_panel(channel):
    draft_state = db.get_draft_state()
    embed = get_protection_embed(draft_state)
    view = ProtectionView()
    await channel.send(embed=embed, view=view)

def get_protection_embed(draft_state):
    deadline = draft_state.get("protection_deadline")
    deadline_str = f"\n⏱️ **Tempo restante para escolhas:** <t:{int(deadline)}:R> (até <t:{int(deadline)}:t>)" if deadline else ""

    embed = discord.Embed(
        title="🛡️ Fase de Proteção",
        description="Cada capitão pode escolher proteger **1** ou **2** jogadores de seu time:\n"
                    "• **Proteger 1**: Protege 1 jogador e o seu time ainda poderá realizar roubos.\n"
                    "• **Proteger 2 (não pode roubar)**: Protege 2 jogadores, mas o seu time não poderá realizar roubos na próxima fase (e também não poderá ser roubado).\n\n"
                    f"Clique no botão abaixo para escolher o seu protegido.{deadline_str}",
        color=discord.Color.blue()
    )
    
    status_text = ""
    for cid, team in draft_state["teams"].items():
        prot_ids = team.get("protected_player_ids", [])
        if not prot_ids and team.get("protected_player_id") is not None:
            prot_ids = [team["protected_player_id"]]
            
        if prot_ids:
            if len(prot_ids) == 2:
                status = "✅ Proteção Dupla (Não rouba)"
            else:
                status = "✅ Proteção Simples"
        else:
            status = "⏳ Aguardando..."
        status_text += f"• <@{cid}>: {status}\n"
        
    embed.add_field(name="Status de Proteção", value=status_text or "Nenhum time.", inline=False)
    return embed

async def update_protection_message(message: discord.Message):
    draft_state = db.get_draft_state()
    embed = get_protection_embed(draft_state)
    view = ProtectionView()
    await message.edit(embed=embed, view=view)

# ==========================================
# 4. VIEWS E COMPONENTES PARA ROUBO (STEAL)
# ==========================================

class StealGiveSelectView(discord.ui.View):
    def __init__(self, active_captain_id, stealer_players):
        super().__init__(timeout=None)
        self.active_captain_id = active_captain_id
        
        # Add blue buttons for each player of the team (excluding GK)
        for pl in stealer_players:
            if pl["position"] != "GK":
                btn = discord.ui.Button(
                    label=f"{pl['name']} ({pl['position']})",
                    style=discord.ButtonStyle.primary,
                    custom_id=f"steal_give_btn_{pl['id']}"
                )
                btn.callback = self.make_button_callback(pl, stealer_players)
                self.add_item(btn)

    def make_button_callback(self, player_data, stealer_players):
        async def btn_callback(interaction: discord.Interaction):
            steal_state = db.get_steal_state()
            draft_state = db.get_draft_state()
            
            # Calcular contagem de roubos por time
            stolen_counts = {}
            for s in steal_state.get("steals", []):
                target_id = str(s["target_captain_id"])
                stolen_counts[target_id] = stolen_counts.get(target_id, 0) + 1
                
            # Jogadores elegíveis de outros times
            protected_player_ids = set()
            for s in steal_state.get("steals", []):
                protected_player_ids.add(str(s["stolen_player_id"]))
                protected_player_ids.add(str(s["given_player_id"]))
            eligible_targets = []
            for cid, team in draft_state["teams"].items():
                prot_ids = [str(x) for x in team.get("protected_player_ids", [])]
                if not prot_ids and team.get("protected_player_id") is not None:
                    prot_ids = [str(team["protected_player_id"])]
                
                # Se o time tem proteção dupla (2 jogadores protegidos), ele não pode ser roubado
                if len(prot_ids) == 2:
                    continue
                    
                if str(cid) != str(interaction.user.id) and stolen_counts.get(str(cid), 0) < 2:
                    for pl in team["players"]:
                        if pl["position"] != "GK" and str(pl["id"]) not in prot_ids and str(pl["id"]) not in protected_player_ids:
                            eligible_targets.append({
                                "target_cid": cid,
                                "captain_name": team["captain_name"],
                                "player": pl,
                                "position": pl["position"]
                            })
                            
            embed = get_steal_embed(steal_state, draft_state)
            embed.description = f"Você selecionou dar <@{player_data['id']}> ({player_data['position']}) em troca.\nAgora selecione qual jogador de outro time quer roubar:"
            
            view = StealTargetSelectView(eligible_targets, interaction.user.id, player_data, stealer_players)
            await interaction.response.edit_message(embed=embed, view=view)
        return btn_callback

    @discord.ui.button(label="Não Roubar", style=discord.ButtonStyle.secondary, custom_id="steal_give_pass_btn")
    async def pass_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        success, res = db.make_steal(interaction.user.id, 0, 0, 0, pass_turn=True)
        if not success:
            return await interaction.response.send_message(f"❌ {res}", ephemeral=True)
            
        await interaction.response.send_message("Você passou o seu turno de roubo.", ephemeral=True)
        await interaction.channel.send(f"🛡️ <@{interaction.user.id}> decidiu não roubar nenhum jogador.")
        
        if res["is_finished"]:
            await end_steal_phase(interaction.channel)
        else:
            state = db._load_state()
            admin_tester_id = state["draft"].get("admin_tester_id")
            if admin_tester_id:
                await run_simulated_steal_turns(interaction.channel, admin_tester_id)
            else:
                await update_steal_message_in_channel(interaction.channel, interaction.message)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != str(self.active_captain_id):
            await interaction.response.send_message("❌ Não é a sua vez de realizar um roubo!", ephemeral=True)
            return False
        return True

class StealTargetSelect(discord.ui.Select):
    def __init__(self, target_chunk, group_num, total_groups, give_player_data):
        options = []
        for item in target_chunk:
            target_cid = item["target_cid"]
            pl = item["player"]
            cap_name = item["captain_name"]
            pos = item["position"]
            
            label = f"{pl['name']} (@{pl.get('username', '')}) ({pos}) - Time {cap_name}"
            if len(label) > 100:
                label = label[:97] + "..."
            options.append(discord.SelectOption(
                label=label,
                value=f"{target_cid}:{pl['id']}",
                description=f"Roubar {pl['name']} em troca de {give_player_data['name']}."
            ))
        placeholder = f"Selecione o jogador para roubar... (Grupo {group_num}/{total_groups})"
        custom_id = f"steal_target_select_{group_num}"
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options, custom_id=custom_id)
        self.give_player_data = give_player_data

    async def callback(self, interaction: discord.Interaction):
        target_cid, target_player_id = self.values[0].split(":")
        success, res = db.make_steal(
            stealer_id=interaction.user.id,
            target_captain_id=int(target_cid),
            target_player_id=int(target_player_id),
            give_player_id=self.give_player_data["id"]
        )
        
        if not success:
            return await interaction.response.send_message(f"❌ {res}", ephemeral=True)
            
        is_finished = res["is_finished"]
        
        # Sucesso: Usar menções
        msg = f"🥷 <@{interaction.user.id}> realizou uma troca forçada! Mandou <@{self.give_player_data['id']}> ({self.give_player_data['position']}) para o Time de <@{target_cid}> e em troca roubou <@{target_player_id}> ({res['position']})!"
            
        await interaction.response.send_message("Troca forçada executada com sucesso!", ephemeral=True)
        await interaction.channel.send(msg)
        
        if is_finished:
            await end_steal_phase(interaction.channel)
        else:
            state = db._load_state()
            admin_tester_id = state["draft"].get("admin_tester_id")
            if admin_tester_id:
                await run_simulated_steal_turns(interaction.channel, admin_tester_id)
            else:
                await update_steal_message_in_channel(interaction.channel, interaction.message)

class StealTargetSelectView(discord.ui.View):
    def __init__(self, eligible_targets, active_captain_id, give_player_data, stealer_players):
        super().__init__(timeout=None)
        self.active_captain_id = active_captain_id
        self.give_player_data = give_player_data
        self.stealer_players = stealer_players
        
        # Split targets into groups of 25
        chunk_size = 25
        chunks = [eligible_targets[i:i + chunk_size] for i in range(0, len(eligible_targets), chunk_size)]
        
        if not chunks:
            # Add a disabled select
            options = [discord.SelectOption(
                label="Nenhum jogador elegível para roubo",
                value="none",
                disabled=True
            )]
            self.add_item(discord.ui.Select(placeholder="Nenhum jogador elegível...", options=options, disabled=True, custom_id="steal_target_empty"))
        else:
            total_groups = len(chunks)
            for idx, chunk in enumerate(chunks[:4]):  # Limit to 4 select menus to leave space for buttons
                self.add_item(StealTargetSelect(chunk, idx + 1, total_groups, give_player_data))

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.secondary, custom_id="steal_target_back_btn")
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Retorna para a etapa 1
        steal_state = db.get_steal_state()
        draft_state = db.get_draft_state()
        embed = get_steal_embed(steal_state, draft_state)
        view = StealGiveSelectView(self.active_captain_id, self.stealer_players)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Não Roubar", style=discord.ButtonStyle.danger, custom_id="steal_target_pass_btn")
    async def pass_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        success, res = db.make_steal(interaction.user.id, 0, 0, 0, pass_turn=True)
        if not success:
            return await interaction.response.send_message(f"❌ {res}", ephemeral=True)
            
        await interaction.response.send_message("Você passou o seu turno de roubo.", ephemeral=True)
        await interaction.channel.send(f"🛡️ <@{interaction.user.id}> decidiu não roubar nenhum jogador.")
        
        if res["is_finished"]:
            await end_steal_phase(interaction.channel)
        else:
            state = db._load_state()
            admin_tester_id = state["draft"].get("admin_tester_id")
            if admin_tester_id:
                await run_simulated_steal_turns(interaction.channel, admin_tester_id)
            else:
                await update_steal_message_in_channel(interaction.channel, interaction.message)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != str(self.active_captain_id):
            await interaction.response.send_message("❌ Não é a sua vez de realizar um roubo!", ephemeral=True)
            return False
        return True

async def send_steal_panel(channel):
    steal_state = db.get_steal_state()
    draft_state = db.get_draft_state()
    
    curr_idx = steal_state["current_index"]
    order = steal_state["order"]
    
    if curr_idx < len(order):
        active_captain_id = order[curr_idx]
        stealer_team = draft_state["teams"][active_captain_id]
        
        embed = get_steal_embed(steal_state, draft_state)
        view = StealGiveSelectView(active_captain_id, stealer_team["players"])
        msg = await channel.send(embed=embed, view=view)
        db.set_draft_message(channel.id, msg.id)

def get_steal_embed(steal_state, draft_state):
    deadline = steal_state.get("turn_deadline")
    deadline_str = f"\n⏱️ **Tempo restante para roubo:** <t:{int(deadline)}:R> (até <t:{int(deadline)}:t>)" if deadline else ""

    embed = discord.Embed(
        title="🥷 Fase de Roubo (Trocas Forçadas)",
        description=f"Capitães realizam trocas forçadas. Se o tempo de 1m30s esgotar, o capitão perde a vez sem realizar trocas.{deadline_str}",
        color=discord.Color.orange()
    )
    
    # Mostrar turnos de roubo
    curr_idx = steal_state["current_index"]
    order = steal_state["order"]
    
    order_text = ""
    for idx, cid in enumerate(order):
        if idx == curr_idx:
            order_text += f"➡️ **#{idx+1}: <@{cid}> (Sua vez)**\n"
        elif idx < curr_idx:
            order_text += f"✅ #{idx+1}: <@{cid}> (Concluído)\n"
        else:
            order_text += f"⏳ #{idx+1}: <@{cid}>\n"
            
    embed.add_field(name="Ordem de Roubo", value=order_text or "Nenhum.", inline=False)
    
    # Obter contagem de roubos por time e IDs de jogadores envolvidos em trocas (roubados ou dados)
    team_stolen_counts = {}
    protected_player_ids = set()
    for s in steal_state.get("steals", []):
        t_id = str(s["target_captain_id"])
        team_stolen_counts[t_id] = team_stolen_counts.get(t_id, 0) + 1
        protected_player_ids.add(str(s["stolen_player_id"]))
        protected_player_ids.add(str(s["given_player_id"]))
    
    # Times Atuais como campos separados
    for cid, team in draft_state["teams"].items():
        players_text = []
        is_team_max_stolen = team_stolen_counts.get(str(cid), 0) >= 2
        prot_ids = [str(x) for x in team.get("protected_player_ids", [])]
        if not prot_ids and team.get("protected_player_id") is not None:
            prot_ids = [str(team["protected_player_id"])]
            
        field_name = f"🏆 Time de {team['captain_name']}"
        if len(prot_ids) == 2:
            field_name += " 🛡️ [DUPLO]"
            
        for pl in team["players"]:
            pl_name = f"<@{pl['id']}>"
            # Adicionar marcador de proteção
            if str(pl["id"]) in prot_ids:
                pl_name += " 🛡️ [PROT]"
            elif is_team_max_stolen and pl["position"] != "GK":
                pl_name += " 🛡️ [ROUBADO]"
            elif str(pl["id"]) in protected_player_ids:
                pl_name += " 🛡️ [ROUBADO]"
            players_text.append(f"• **{pl['position']}**: {pl_name}")
        while len(players_text) < 5:
            players_text.append("• *Vago*")
        embed.add_field(name=field_name, value="\n".join(players_text), inline=True)
        
    return embed

async def update_steal_message_in_channel(channel, message: discord.Message = None):
    steal_state = db.get_steal_state()
    draft_state = db.get_draft_state()
    
    curr_idx = steal_state["current_index"]
    order = steal_state["order"]
    
    if not message and channel:
        chan_id, msg_id = db.get_draft_message()
        if msg_id:
            try:
                message = await channel.fetch_message(msg_id)
            except Exception:
                pass

    if curr_idx < len(order):
        active_captain_id = order[curr_idx]
        stealer_team = draft_state["teams"][active_captain_id]
        
        embed = get_steal_embed(steal_state, draft_state)
        view = StealGiveSelectView(active_captain_id, stealer_team["players"])
        if message:
            try:
                await message.edit(embed=embed, view=view)
            except Exception:
                new_msg = await channel.send(embed=embed, view=view)
                db.set_draft_message(channel.id, new_msg.id)
        else:
            new_msg = await channel.send(embed=embed, view=view)
            db.set_draft_message(channel.id, new_msg.id)
    else:
        embed = get_steal_embed(steal_state, draft_state)
        if message:
            try:
                await message.edit(embed=embed, view=None)
            except Exception:
                pass

async def end_steal_phase(channel):
    db.set_phase("bracket")
    try:
        await channel.purge(limit=300)
    except Exception as e:
        print(f"Erro ao limpar canal: {e}")
    await generate_and_send_bracket(channel)

# ==========================================
# 5. BRACKET & SISTEMA DE VOTAÇÃO
# ==========================================

class MatchVoteView(discord.ui.View):
    def __init__(self, match_id, team_a_id, team_b_id, team_a_name, team_b_name):
        super().__init__(timeout=None)
        self.match_id = match_id
        self.team_a_id = team_a_id
        self.team_b_id = team_b_id
        
        # Atualizar textos dos botões com os nomes dos times
        self.vote_a_btn.label = f"Votar no Time {team_a_name}"
        self.vote_b_btn.label = f"Votar no Time {team_b_name}"
        self.vote_a_btn.custom_id = f"vote_a_{match_id}"
        self.vote_b_btn.custom_id = f"vote_b_{match_id}"

    @discord.ui.button(label="Votar Time A", style=discord.ButtonStyle.primary)
    async def vote_a_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_vote(interaction, self.team_a_id)

    @discord.ui.button(label="Votar Time B", style=discord.ButtonStyle.secondary)
    async def vote_b_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_vote(interaction, self.team_b_id)

    @discord.ui.button(label="Aprovação Admin", style=discord.ButtonStyle.danger, custom_id="admin_override_btn")
    async def admin_override_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Apenas admins podem usar o override
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores do servidor podem usar a aprovação rápida.", ephemeral=True)
            
        # Abrir menu para selecionar o time vencedor
        view = discord.ui.View()
        teams = db.get_teams()
        team_a_name = teams[self.team_a_id].get("team_name", teams[self.team_a_id]["captain_name"])
        team_b_name = teams[self.team_b_id].get("team_name", teams[self.team_b_id]["captain_name"])
        
        select_winner = discord.ui.Select(
            placeholder="Selecione o Time Vencedor...",
            options=[
                discord.SelectOption(label=f"Time A ({team_a_name})", value=self.team_a_id),
                discord.SelectOption(label=f"Time B ({team_b_name})", value=self.team_b_id)
            ]
        )
        
        async def select_callback(inter: discord.Interaction):
            winner_id = select_winner.values[0]
            success, res = db.admin_override_winner(self.match_id, winner_id)
            if not success:
                return await inter.response.send_message(f"❌ {res}", ephemeral=True)
                
            # Resolver partida
            new_matches = db.resolve_match(self.match_id, winner_id)
            winner_name = db.get_teams()[winner_id].get("team_name", db.get_teams()[winner_id]['captain_name'])
            
            await inter.response.send_message(f"✅ Partida resolvida por administrador!", ephemeral=True)
            await inter.channel.send(f"👑 **Administrador aprovou a vitória do Time {winner_name}** no confronto `{self.match_id}`! Este canal será excluído assim que o próximo confronto iniciar.")
            
            # Desabilitar votação
            try:
                await interaction.message.delete()
            except:
                pass
            # Atualizar chave
            await update_bracket_posts(interaction.channel)

        select_winner.callback = select_callback
        view.add_item(select_winner)
        await interaction.response.send_message("Qual time venceu?", view=view, ephemeral=True)

    async def process_vote(self, interaction: discord.Interaction, team_voted_id):
        success, res = db.record_vote(self.match_id, interaction.user.id, team_voted_id)
        if not success:
            return await interaction.response.send_message(f"❌ {res}", ephemeral=True)
            
        votes_a = res["votes_a"]
        votes_b = res["votes_b"]
        winner_id = res["winner_id"]
        
        await interaction.response.send_message("✅ Seu voto foi registrado!", ephemeral=True)
        
        # Editar embed de votos na mensagem
        teams = db.get_teams()
        team_a_name = teams[self.team_a_id].get("team_name", teams[self.team_a_id]["captain_name"])
        team_b_name = teams[self.team_b_id].get("team_name", teams[self.team_b_id]["captain_name"])
        
        required_votes = db.get_required_votes()
        
        embed = interaction.message.embeds[0]
        embed.set_field_at(0, name="Placar de Votos", value=f"🏆 **Time {team_a_name}**: {votes_a} votos\n🏆 **Time {team_b_name}**: {votes_b} votos\n*(Mínimo necessário: {required_votes} votos)*", inline=False)
        await interaction.message.edit(embed=embed)
        
        if winner_id:
            # Temos um vencedor
            new_matches = db.resolve_match(self.match_id, winner_id)
            winner_name = teams[winner_id].get("team_name", teams[winner_id]["captain_name"])
            
            await interaction.channel.send(f"🎉 **Fim de votação!** O **Time {winner_name}** venceu a partida `{self.match_id}` com {max(votes_a, votes_b)} votos! Este canal será excluído assim que o próximo confronto iniciar.")
            try:
                await interaction.message.delete()
            except:
                pass
            # Atualizar chave
            await update_bracket_posts(interaction.channel)

async def create_team_voice_channels(guild, teams):
    category_name = "🔊 Calls dos Times"
    category = discord.utils.get(guild.categories, name=category_name)
    if not category:
        try:
            category = await guild.create_category(category_name)
        except Exception as e:
            print(f"Erro ao criar categoria de voz: {e}")
            return

    COUNTRY_INFO = {
        "Brasil": {"flag": "🇧🇷", "abbr": "BR"},
        "França": {"flag": "🇫🇷", "abbr": "FRA"},
        "Espanha": {"flag": "🇪🇸", "abbr": "ESP"},
        "Inglaterra": {"flag": "🇬🇧", "abbr": "ING"},
        "Argentina": {"flag": "🇦🇷", "abbr": "ARG"},
        "Alemanha": {"flag": "🇩🇪", "abbr": "ALE"},
        "Croácia": {"flag": "🇭🇷", "abbr": "CRO"},
        "Holanda": {"flag": "🇳🇱", "abbr": "HOL"}
    }

    def get_info(team_name):
        for country, info in COUNTRY_INFO.items():
            if country in team_name:
                return info
        return {"flag": "👥", "abbr": "TIM"}

    for tid, team in teams.items():
        team_name = team.get("team_name", team.get("captain_name", f"Time {tid[:6]}"))
        info = get_info(team_name)
        flag = info["flag"]
        
        vc_name = f"{flag} {team_name}"
        
        try:
            vc = await guild.create_voice_channel(vc_name, category=category)
            
            # Arrastar jogadores que estiverem em alguma call
            for pl in team.get("players", []):
                member = guild.get_member(int(pl["id"]))
                if not member:
                    try:
                        member = await guild.fetch_member(int(pl["id"]))
                    except:
                        pass
                if member and member.voice and member.voice.channel:
                    try:
                        await member.move_to(vc)
                    except Exception as ex:
                        print(f"Não foi possível arrastar {member.name}: {ex}")
        except Exception as e:
            print(f"Erro ao criar canal de voz {vc_name}: {e}")

async def delete_team_voice_channels(guild):
    category_name = "🔊 Calls dos Times"
    category = discord.utils.get(guild.categories, name=category_name)
    if category:
        try:
            for channel in category.channels:
                await channel.delete()
            await category.delete()
        except Exception as e:
            print(f"Erro ao deletar canais de voz do time: {e}")

async def setup_confrontation_channel(guild, mid, match, teams):
    state = db._load_state()
    db_match = state["bracket"]["matches"][mid]
    
    category_id = db_match.get("confrontation_category_id")
    channel_id = db_match.get("confrontation_channel_id")
    voice_a_id = db_match.get("confrontation_voice_a_id")
    voice_b_id = db_match.get("confrontation_voice_b_id")
    
    category = guild.get_channel(category_id) if category_id else None
    channel = guild.get_channel(channel_id) if channel_id else None
    voice_a = guild.get_channel(voice_a_id) if voice_a_id else None
    voice_b = guild.get_channel(voice_b_id) if voice_b_id else None
    
    if category and channel and voice_a and voice_b:
        return category, channel, voice_a, voice_b
        
    team_a_id = match["team_a_id"]
    team_b_id = match["team_b_id"]
    team_a = teams[team_a_id]
    team_b = teams[team_b_id]
    
    team_a_name = team_a.get("team_name", team_a.get("captain_name", "Time A"))
    team_b_name = team_b.get("team_name", team_b.get("captain_name", "Time B"))
    
    COUNTRY_INFO = {
        "Brasil": {"flag": "🇧🇷", "abbr": "BR"},
        "França": {"flag": "🇫🇷", "abbr": "FRA"},
        "Espanha": {"flag": "🇪🇸", "abbr": "ESP"},
        "Inglaterra": {"flag": "🇬🇧", "abbr": "ING"},
        "Argentina": {"flag": "🇦🇷", "abbr": "ARG"},
        "Alemanha": {"flag": "🇩🇪", "abbr": "ALE"},
        "Croácia": {"flag": "🇭🇷", "abbr": "CRO"},
        "Holanda": {"flag": "🇳🇱", "abbr": "HOL"}
    }
    
    def get_info(name):
        for country, info in COUNTRY_INFO.items():
            if country in name:
                return info
        return {"flag": "⚔️", "abbr": name[:3].upper()}
        
    info_a = get_info(team_a_name)
    info_b = get_info(team_b_name)
    
    category_name = f"{info_a['flag']} {info_a['abbr']} x {info_b['abbr']} {info_b['flag']}"
    
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    
    for pl in team_a.get("players", []):
        member = guild.get_member(int(pl["id"]))
        if not member:
            try:
                member = await guild.fetch_member(int(pl["id"]))
            except:
                pass
        if member:
            overwrites[member] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
    for pl in team_b.get("players", []):
        member = guild.get_member(int(pl["id"]))
        if not member:
            try:
                member = await guild.fetch_member(int(pl["id"]))
            except:
                pass
        if member:
            overwrites[member] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
    try:
        if category:
            try:
                await category.delete()
            except:
                pass
                
        category = await guild.create_category(category_name)
        channel = await guild.create_text_channel("💬-chat-confronto", category=category, overwrites=overwrites)
        
        # Obter nome limpo das seleções para as calls
        clean_name_a = team_a_name.split(" (")[0]
        clean_name_b = team_b_name.split(" (")[0]
        
        vc_a_name = f"🔊 {info_a['flag']} {clean_name_a}"
        vc_b_name = f"🔊 {info_b['flag']} {clean_name_b}"
        
        voice_a = await guild.create_voice_channel(vc_a_name, category=category)
        voice_b = await guild.create_voice_channel(vc_b_name, category=category)
        
        db_match["confrontation_category_id"] = category.id
        db_match["confrontation_channel_id"] = channel.id
        db_match["confrontation_voice_a_id"] = voice_a.id
        db_match["confrontation_voice_b_id"] = voice_b.id
        db._save_state(state)
        
        return category, channel, voice_a, voice_b
    except Exception as e:
        print(f"Erro ao criar categoria/canais de confronto: {e}")
        return None, None, None, None

async def drag_players_to_confrontation(guild, match, teams, voice_a, voice_b):
    team_a_id = match["team_a_id"]
    team_b_id = match["team_b_id"]
    
    # Mover jogadores do Time A para voice_a
    for pl in teams[team_a_id].get("players", []):
        member = guild.get_member(int(pl["id"]))
        if not member:
            try:
                member = await guild.fetch_member(int(pl["id"]))
            except:
                pass
        if member and member.voice and member.voice.channel:
            if member.voice.channel != voice_a:
                try:
                    await member.move_to(voice_a)
                except Exception as ex:
                    print(f"Não foi possível arrastar {member.name} para call de confronto A: {ex}")
                    
    # Mover jogadores do Time B para voice_b
    for pl in teams[team_b_id].get("players", []):
        member = guild.get_member(int(pl["id"]))
        if not member:
            try:
                member = await guild.fetch_member(int(pl["id"]))
            except:
                pass
        if member and member.voice and member.voice.channel:
            if member.voice.channel != voice_b:
                try:
                    await member.move_to(voice_b)
                except Exception as ex:
                    print(f"Não foi possível arrastar {member.name} para call de confronto B: {ex}")

async def delete_completed_matches_channels(guild):
    state = db._load_state()
    matches = state.get("bracket", {}).get("matches", {})
    
    for mid, match in list(matches.items()):
        if match.get("status") == "completed":
            category_id = match.get("confrontation_category_id")
            channel_id = match.get("confrontation_channel_id")
            voice_a_id = match.get("confrontation_voice_a_id")
            voice_b_id = match.get("confrontation_voice_b_id")
            
            if channel_id:
                try:
                    chan = guild.get_channel(channel_id)
                    if chan:
                        await chan.delete()
                except Exception as e:
                    print(f"Erro ao deletar canal de texto do confronto {mid}: {e}")
                    
            if voice_a_id:
                try:
                    vc = guild.get_channel(voice_a_id)
                    if vc:
                        await vc.delete()
                except Exception as e:
                    print(f"Erro ao deletar canal de voz A do confronto {mid}: {e}")
                    
            if voice_b_id:
                try:
                    vc = guild.get_channel(voice_b_id)
                    if vc:
                        await vc.delete()
                except Exception as e:
                    print(f"Erro ao deletar canal de voz B do confronto {mid}: {e}")
                    
            if category_id:
                try:
                    cat = guild.get_channel(category_id)
                    if cat:
                        await cat.delete()
                except Exception as e:
                    print(f"Erro ao deletar categoria do confronto {mid}: {e}")
            
            match["confrontation_category_id"] = None
            match["confrontation_channel_id"] = None
            match["confrontation_voice_a_id"] = None
            match["confrontation_voice_b_id"] = None
            match["confrontation_voting_msg_id"] = None
            
    db._save_state(state)

async def cleanup_confrontation_channel(guild, match_id):
    await delete_completed_matches_channels(guild)

async def generate_and_send_bracket(channel):
    teams = db.get_teams()
    team_ids = list(teams.keys())
    
    matches = generate_bracket_matches(team_ids)
    db.setup_bracket(matches)
    
    # Criar postagem da bracket
    await send_bracket_status(channel)
    # Criar votações ativas
    await start_active_match_votings(channel)

async def send_bracket_to_confrontation(channel):
    try:
        bracket_state = db.get_bracket_state()
        teams = db.get_teams()
        
        # Gerar imagem da bracket programaticamente sobre a base_bracket.png
        draw_bracket_image(bracket_state["matches"], teams, f"bracket_{channel.id}.png")
        file = discord.File(f"bracket_{channel.id}.png", filename="bracket.png")
        
        embed = discord.Embed(
            title="📊 Chaveamento do Campeonato (Bracket)",
            description="Confira a tabela completa do Mix abaixo para ver o status dos outros confrontos!",
            color=discord.Color.purple()
        )
        embed.set_image(url="attachment://bracket.png")
        
        await channel.send(file=file, embed=embed)
        
        # Deletar imagem temporária local
        try:
            os.remove(f"bracket_{channel.id}.png")
        except:
            pass
    except Exception as e:
        print(f"Erro ao enviar chaveamento para o canal de confronto: {e}")

async def send_bracket_status(channel):
    bracket_state = db.get_bracket_state()
    teams = db.get_teams()
    
    text = format_bracket_text(bracket_state["matches"], teams)
    
    # Gerar imagem da bracket programaticamente sobre a base_bracket.png
    draw_bracket_image(bracket_state["matches"], teams, "bracket.png")
    file = discord.File("bracket.png", filename="bracket.png")
    
    # Obter comentários da IA sobre a bracket
    commentary = await get_gemini_commentary(text)
    
    embed = discord.Embed(
        title="📊 Chaveamento do Campeonato (Bracket)",
        description="Acompanhe a tabela e o status dos confrontos na imagem abaixo. Os votos são atualizados em tempo real!",
        color=discord.Color.purple()
    )
    embed.set_image(url="attachment://bracket.png")
    
    if commentary:
        embed.add_field(name="🎙️ Transmissão ao Vivo (Narrador Gemini)", value=commentary, inline=False)
    
    # Salva a mensagem do chaveamento para atualizar futuramente
    msg = await channel.send(file=file, embed=embed)
    db_state = db._load_state()
    db_state["bracket"]["message_id"] = msg.id
    db_state["bracket"]["channel_id"] = channel.id
    db._save_state(db_state)
async def update_bracket_posts(channel):
    bracket_state = db.get_bracket_state()
    teams = db.get_teams()
    
    msg_id = bracket_state.get("message_id")
    chan_id = bracket_state.get("channel_id")
    
    # Resolve target channel from db
    target_channel = channel
    if chan_id:
        guild_chan = channel.guild.get_channel(chan_id)
        if guild_chan:
            target_channel = guild_chan
            
    # Regenerar imagem
    draw_bracket_image(bracket_state["matches"], teams, "bracket.png")
    text = format_bracket_text(bracket_state["matches"], teams)
    commentary = await get_gemini_commentary(text)
    
    if msg_id and chan_id:
        try:
            msg = await target_channel.fetch_message(msg_id)
            
            file = discord.File("bracket.png", filename="bracket.png")
            embed = discord.Embed(
                title="📊 Chaveamento do Campeonato (Bracket)",
                description="Acompanhe a tabela e o status dos confrontos na imagem abaixo. Os votos são atualizados em tempo real!",
                color=discord.Color.purple()
            )
            embed.set_image(url="attachment://bracket.png")
            if commentary:
                embed.add_field(name="🎙️ Transmissão ao Vivo (Narrador Gemini)", value=commentary, inline=False)
                
            await msg.edit(embed=embed, attachments=[file])
        except Exception as e:
            print(f"Erro ao editar bracket post: {e}")
            
    # Verificar se o campeonato acabou
    matches = bracket_state["matches"]
    gf_matches = [m for mid, m in matches.items() if m["type"] == "grand_final"]
    if gf_matches:
        gf = gf_matches[0]
        if gf["status"] == "completed":
            winner_id = gf["winner_id"]
            champ_team = teams[winner_id]
            team_name = champ_team.get("team_name", champ_team.get("captain_name", "Vencedor"))
            
            embed_champ = discord.Embed(
                title="🏆 Campeão do Torneio!",
                description=f"Parabéns ao time **{team_name}** pela vitória!",
                color=discord.Color.gold()
            )
            
            players_text = []
            for pl in champ_team["players"]:
                players_text.append(f"• **{pl['position']}**: <@{pl['id']}>")
            embed_champ.add_field(name="Elenco Vencedor", value="\n".join(players_text))
            await target_channel.send(embed=embed_champ)
            
            # Limpar as calls de voz dos times e canais de confronto
            await delete_completed_matches_channels(target_channel.guild)
            
            db.set_phase("inscricao")
            return

    # Iniciar novas votações de matches ativos no canal alvo
    await start_active_match_votings(target_channel)

async def start_active_match_votings(channel):
    bracket_state = db.get_bracket_state()
    teams = db.get_teams()
    matches = bracket_state["matches"]
    
    # Verificar se é um mix teste
    state = db._load_state()
    admin_tester_id = state["draft"].get("admin_tester_id")
    
    for mid, match in matches.items():
        if match["status"] == "ongoing":
            team_a_id = match["team_a_id"]
            team_b_id = match["team_b_id"]
            
            # Se for partida só de bots no mix teste
            if admin_tester_id and str(team_a_id) != str(admin_tester_id) and str(team_b_id) != str(admin_tester_id):
                winner_id = random.choice([team_a_id, team_b_id])
                winner_name = teams[winner_id].get("team_name", teams[winner_id]["captain_name"])
                team_a_name = teams[team_a_id].get("team_name", teams[team_a_id]["captain_name"])
                team_b_name = teams[team_b_id].get("team_name", teams[team_b_id]["captain_name"])
                
                # Simulação silenciosa no console para não floodar o chat do draft
                print(f"[BOT] Simulando partida `{mid}`: {team_a_name} vs {team_b_name}...")
                await asyncio.sleep(2.0)
                
                db.resolve_match(mid, winner_id)
                print(f"[BOT] Partida `{mid}` finalizada! {winner_name} venceu e avançou!")
                await update_bracket_posts(channel)
                return
            
            team_a_name = teams[team_a_id].get("team_name", teams[team_a_id]["captain_name"])
            team_b_name = teams[team_b_id].get("team_name", teams[team_b_id]["captain_name"])
            
            # Obter/criar canal e categoria privados do confronto (com duas calls de voz)
            confrontation_category, confrontation_channel, voice_a, voice_b = await setup_confrontation_channel(channel.guild, mid, match, teams)
            if not confrontation_channel:
                confrontation_channel = channel # Fallback
                
            # Arrastar jogadores para suas respectivas calls de voz
            if voice_a and voice_b:
                await drag_players_to_confrontation(channel.guild, match, teams, voice_a, voice_b)
                
                # Disparar a narração de voz por IA em segundo plano (sem bloquear)
                a_players_list = teams[team_a_id]["players"]
                b_players_list = teams[team_b_id]["players"]
                asyncio.create_task(
                    trigger_match_voice_commentary(
                        channel.guild, 
                        team_a_name, 
                        team_b_name, 
                        a_players_list, 
                        b_players_list, 
                        voice_a, 
                        voice_b
                    )
                )
                
                # Agendar deleção dos confrontos anteriores concluídos com delay de 6 segundos pós-drag
                async def delayed_cleanup(guild):
                    await asyncio.sleep(6.0)
                    await delete_completed_matches_channels(guild)
                asyncio.create_task(delayed_cleanup(channel.guild))
                
            # Formatar elenco dos times no embed usando lista e menções
            a_players = "\n".join([f"• **{pl['position']}**: <@{pl['id']}>" for pl in teams[team_a_id]["players"]])
            b_players = "\n".join([f"• **{pl['position']}**: <@{pl['id']}>" for pl in teams[team_b_id]["players"]])
            
            required_votes = db.get_required_votes()
            total_players = len(teams[team_a_id]["players"]) + len(teams[team_b_id]["players"])
            
            embed = discord.Embed(
                title=f"⚔️ Votação de Partida: Confronto `{mid}`",
                description=f"O confronto `{mid}` ({match['label']}) está pronto!\n\n**Apenas os {total_players} jogadores deste confronto podem votar.**\n*(Necessário {required_votes} votos no mesmo time)*",
                color=discord.Color.red()
            )
            
            if admin_tester_id:
                embed.description += "\n\n💡 *Dica: Como esta partida contém bots, use o botão **Aprovação Admin** para decidir o vencedor e avançar!*"

            embed.add_field(name=f"{team_a_name}", value=a_players, inline=True)
            embed.add_field(name=f"{team_b_name}", value=b_players, inline=True)
            
            votes_a = sum(1 for uid, vid in match.get("votes", {}).items() if vid == team_a_id)
            votes_b = sum(1 for uid, vid in match.get("votes", {}).items() if vid == team_b_id)
            
            embed.add_field(
                name="Placar de Votos",
                value=f"🏆 **{team_a_name}**: {votes_a} votos\n🏆 **{team_b_name}**: {votes_b} votos\n*(Mínimo necessário: {required_votes} votos)*",
                inline=False
            )
            
            view = MatchVoteView(mid, team_a_id, team_b_id, team_a_name, team_b_name)
            
            # Verificar se já existe a mensagem de votação no banco e atualizá-la
            db_state = db._load_state()
            db_match = db_state["bracket"]["matches"][mid]
            voting_msg_id = db_match.get("confrontation_voting_msg_id")
            
            if voting_msg_id:
                try:
                    msg = await confrontation_channel.fetch_message(voting_msg_id)
                    await msg.edit(embed=embed, view=view)
                except:
                    msg = await confrontation_channel.send(embed=embed, view=view)
                    db_match["confrontation_voting_msg_id"] = msg.id
                    db._save_state(db_state)
            else:
                # Envia o chaveamento completo para o chat do confronto pela primeira vez
                await send_bracket_to_confrontation(confrontation_channel)
                
                msg = await confrontation_channel.send(embed=embed, view=view)
                db_match["confrontation_voting_msg_id"] = msg.id
                db._save_state(db_state)
# ==========================================
# SIMULAÇÃO DE MIX TESTE (BOTS)
# ==========================================

async def run_simulated_draft_turns(channel, admin_id):
    draft_state = db.get_draft_state()
    regs = db.get_registrations()
    curr_idx = draft_state["current_index"]
    order = draft_state["order"]

    while curr_idx < len(order):
        active_captain_id = order[curr_idx]
        if str(active_captain_id) == str(admin_id):
            # É o turno do admin. Para a simulação e exibe o menu para ele escolher.
            draft_state = db.get_draft_state()
            embed = get_draft_embed(draft_state, regs)
            
            picked_ids = set()
            for tid, team in draft_state["teams"].items():
                for pl in team["players"]:
                    picked_ids.add(str(pl["id"]))
            available_players = {pid: p for pid, p in regs.items() if pid not in picked_ids and pid not in draft_state["captains"]}
            
            view = DraftView(available_players, admin_id)
            await channel.send(embed=embed, view=view)
            return

        # Turno de um bot. Escolhe um jogador aleatório elegível.
        active_captain = draft_state["teams"][active_captain_id]
        
        picked_ids = set()
        for tid, team in draft_state["teams"].items():
            for pl in team["players"]:
                picked_ids.add(str(pl["id"]))
                
        eligible = [p for pid, p in regs.items() if pid not in picked_ids and pid not in draft_state["captains"]]
        
        if not eligible:
            # Pula o turno se não houver jogador (caso de segurança)
            db._lock.acquire()
            try:
                state = db._load_state()
                state["draft"]["current_index"] += 1
                db._save_state(state)
            finally:
                db._lock.release()
            draft_state = db.get_draft_state()
            curr_idx = draft_state["current_index"]
            continue
            
        chosen = random.choice(eligible)
        success, res = db.make_pick(int(active_captain_id), chosen["user_id"])
        if success:
            await channel.send(f"🤖 **[BOT]** <@{active_captain_id}> escolheu <@{chosen['user_id']}> como **{res['position']}**!")
            await asyncio.sleep(1.0)
            
        draft_state = db.get_draft_state()
        curr_idx = draft_state["current_index"]

    # Fim do draft
    await concluir_draft(channel)

async def concluir_draft(channel):
    # 1. Distribuir jogadores restantes se houver vagas em aberto
    distributed = db.distribute_leftover_players()
    if distributed:
        msg_parts = ["🎲 **Distribuição Automática de Sobras:**"]
        for p_name, cap_name, pos, p_id in distributed:
            msg_parts.append(f"• <@{p_id}> ({pos}) foi designado para o **Time de {cap_name}**")
        await channel.send("\n".join(msg_parts))
        await asyncio.sleep(1.0)
        
    # 2. Entrar na Fase de Proteção
    db.set_phase("protecao")
    db.set_protection_deadline(time.time() + 90)
    await channel.send("🎉 **Draft concluído!** Iniciando a **Fase de Proteção**...")
    
    state = db._load_state()
    admin_tester_id = state["draft"].get("admin_tester_id")
    if admin_tester_id:
        await run_simulated_protection_turns(channel, admin_tester_id)
    else:
        await send_protection_panel(channel)

async def run_simulated_protection_turns(channel, admin_id):
    draft_state = db.get_draft_state()
    # Proteção automática para todos os bots
    for cid, team in draft_state["teams"].items():
        if str(cid) != str(admin_id):
            eligible_players = [pl for pl in team["players"] if pl["position"] != "GK"]
            if eligible_players:
                chosen = random.choice(eligible_players)
                db.protect_player(int(cid), chosen["id"])
                await channel.send(f"🛡️ **[BOT]** <@{cid}> ativou o escudo em <@{chosen['id']}>!")
                await asyncio.sleep(0.5)

    # Painel para o admin escolher a proteção dele
    await send_protection_panel(channel)

async def run_simulated_steal_turns(channel, admin_id):
    steal_state = db.get_steal_state()
    draft_state = db.get_draft_state()
    curr_idx = steal_state["current_index"]
    order = steal_state["order"]

    while curr_idx < len(order):
        active_captain_id = order[curr_idx]
        if str(active_captain_id) == str(admin_id):
            # É a vez do admin roubar. Envia o painel de roubo.
            await send_steal_panel(channel)
            return

        # Turno de um bot
        active_captain = draft_state["teams"][active_captain_id]
        if random.random() < 0.5:
            # Bot decide roubar
            stolen_counts = {}
            for s in steal_state.get("steals", []):
                target_id = str(s["target_captain_id"])
                stolen_counts[target_id] = stolen_counts.get(target_id, 0) + 1

            protected_player_ids = set()
            for s in steal_state.get("steals", []):
                protected_player_ids.add(str(s["stolen_player_id"]))
                protected_player_ids.add(str(s["given_player_id"]))
            eligible_targets = []
            for target_cid, data in draft_state["teams"].items():
                prot_ids = [str(x) for x in data.get("protected_player_ids", [])]
                if not prot_ids and data.get("protected_player_id") is not None:
                    prot_ids = [str(data["protected_player_id"])]
                
                # Ignora se o time escolheu dupla proteção
                if len(prot_ids) == 2:
                    continue
                    
                if str(target_cid) != str(active_captain_id) and stolen_counts.get(str(target_cid), 0) < 2:
                    for pl in data["players"]:
                        if pl["position"] != "GK" and str(pl["id"]) not in prot_ids and str(pl["id"]) not in protected_player_ids:
                            eligible_targets.append((target_cid, pl))
                            
            own_players = [pl for pl in active_captain["players"] if pl["position"] != "GK"]

            if eligible_targets and own_players:
                target_cid, target_pl = random.choice(eligible_targets)
                give_pl = random.choice(own_players)
                
                success, res = db.make_steal(int(active_captain_id), int(target_cid), target_pl["id"], give_pl["id"])
                if success:
                    await channel.send(f"🥷 **[BOT]** <@{active_captain_id}> realizou uma troca forçada! Mandou <@{res['given_player_id']}> ({give_pl['position']}) para o Time de <@{target_cid}> e em troca roubou <@{target_pl['id']}> ({res['position']})!")
                    await asyncio.sleep(1.0)
                    draft_state = db.get_draft_state()
                else:
                    db.make_steal(int(active_captain_id), 0, 0, 0, pass_turn=True)
                    await channel.send(f"🛡️ **[BOT]** <@{active_captain_id}> decidiu não roubar nenhum jogador.")
                    await asyncio.sleep(0.5)
            else:
                db.make_steal(int(active_captain_id), 0, 0, 0, pass_turn=True)
                await channel.send(f"🛡️ **[BOT]** <@{active_captain_id}> decidiu não roubar nenhum jogador.")
                await asyncio.sleep(0.5)
        else:
            db.make_steal(int(active_captain_id), 0, 0, 0, pass_turn=True)
            await channel.send(f"🛡️ **[BOT]** <@{active_captain_id}> decidiu não roubar nenhum jogador.")
            await asyncio.sleep(0.5)

        steal_state = db.get_steal_state()
        curr_idx = steal_state["current_index"]

    await end_steal_phase(channel)

# ==========================================
# 6. COMANDOS DE MENSAGEM (PREFIX $)
# ==========================================

@bot.command(name="comandosmix")
async def cmd_comandosmix(ctx):
    embed = discord.Embed(
        title="🎮 Guia de Comandos - Rematch Mix Bot",
        description="Abaixo estão todos os comandos disponíveis e suas funcionalidades.",
        color=discord.Color.blue()
    )
    
    # Comandos Públicos
    public_commands = (
        "• **`$inscritos`**: Mostra todos os jogadores inscritos agrupados por posição e a contagem total.\n"
        "• **`$elenco`**: Mostra a escalação completa de cada time com suas respectivas bandeiras.\n"
        "• **`$cancelar_inscricao`**: Cancela a sua inscrição no mix atual (só funciona na fase de Inscrição).\n"
        "• **`$bracket`**: Reenvia a bracket e as votações ativas do campeonato no canal atual (só funciona na fase de Bracket).\n"
        "• **`$narrar_teste`**: Faz o narrador entrar na sua call de voz atual e falar uma saudação rápida de teste.\n"
        "• **`$narrar_teste_jogos`**: Simula a narração de um confronto real (magas, killi, galtz, jorg, kayke) em sua call atual."
    )
    embed.add_field(name="👥 Comandos Públicos (Jogadores)", value=public_commands, inline=False)
    
    # Comandos de Administração
    admin_commands = (
        "• **`$mixcomecar`**: Reseta o banco de dados e abre o painel de inscrições.\n"
        "• **`$mix5x5` / `$mix4x4` / `$mix3x3` / `$mix2x2` / `$mix1x1`**: Fecha inscrições e inicia picks no formato.\n"
        "• **`$mix_teste`**: Inicia simulação 100% automatizada com bots e 8 times (ótimo para testar).\n"
        "• **`$proteger`**: Ativa manualmente a Fase de Proteção.\n"
        "• **`$restaurar_painel`**: Reenvia o painel ativo da fase atual (caso o bot caia).\n"
        "• **`$narrador_voz <antonio|francisca|thalita>`**: Define a voz por IA.\n"
        "• **`$narrador_efeito <rapido|estadio|grave|normal>`**: Define o efeito de voz.\n"
        "• **`$vozbot`**: Narra sequencialmente os confrontos ativos em suas calls de voz.\n"
        "• **`$admin_adicionar <@membro> <posição>`**: Inscreve um membro manualmente.\n"
        "• **`$admin_remover <@membro>`**: Desinscreve um membro manualmente.\n"
        "• **`$admin_limpar`**: Limpa o banco e volta para a fase inicial de inscrições.\n"
        "• **`$mock_setup <times>`**: Cria capitães e jogadores fictícios para testes manuais."
    )
    embed.add_field(name="🛠️ Comandos de Administração (Admins)", value=admin_commands, inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="vozbot")
@commands.has_permissions(administrator=True)
async def cmd_vozbot(ctx):
    phase = db.get_phase()
    if phase != "bracket":
        return await ctx.send("❌ Só é possível usar o comando `$vozbot` durante a fase de Bracket/Partidas.")
        
    bracket_state = db.get_bracket_state()
    teams = db.get_teams()
    matches = bracket_state.get("matches", {})
    
    ongoing_matches = [m for m in matches.values() if m.get("status") == "ongoing"]
    if not ongoing_matches:
        return await ctx.send("❌ Não há partidas em andamento (`ongoing`) no momento.")
        
    await ctx.send(f"🎙️ **VozBot**: Iniciando narração sequencial em {len(ongoing_matches)} partida(s) em andamento...")
    
    for idx, match in enumerate(ongoing_matches):
        team_a_id = match["team_a_id"]
        team_b_id = match["team_b_id"]
        team_a_name = teams[team_a_id].get("team_name", teams[team_a_id]["captain_name"])
        team_b_name = teams[team_b_id].get("team_name", teams[team_b_id]["captain_name"])
        a_players_list = teams[team_a_id]["players"]
        b_players_list = teams[team_b_id]["players"]
        
        voice_a_id = match.get("confrontation_voice_a_id")
        voice_b_id = match.get("confrontation_voice_b_id")
        
        voice_a = ctx.guild.get_channel(voice_a_id) if voice_a_id else None
        voice_b = ctx.guild.get_channel(voice_b_id) if voice_b_id else None
        
        if voice_a_id and not voice_a:
            try:
                voice_a = await ctx.guild.fetch_channel(voice_a_id)
            except:
                pass
        if voice_b_id and not voice_b:
            try:
                voice_b = await ctx.guild.fetch_channel(voice_b_id)
            except:
                pass
                
        if not voice_a and not voice_b:
            continue
            
        await ctx.send(f"🎙️ Narrando Partida {idx+1}/{len(ongoing_matches)}: **{team_a_name}** vs **{team_b_name}**...")
        
        text = await get_match_voice_commentary(team_a_name, team_b_name, a_players_list, b_players_list)
        if not text:
            continue
            
        async with bot.voice_lock:
            if voice_a:
                await play_match_introduction_voice(ctx.guild, voice_a, text)
                await asyncio.sleep(1.0)
            if voice_b:
                await play_match_introduction_voice(ctx.guild, voice_b, text)
                await asyncio.sleep(1.0)
                
    await ctx.send("✅ Narração sequencial concluída!")

@bot.command(name="mix_teste")
@commands.has_permissions(administrator=True)
async def cmd_mix_teste(ctx):
    db.reset_db()
    
    admin_id = ctx.author.id
    db.register_player(admin_id, ctx.author.name, ctx.author.display_name, "GK")
    
    # 7 Capitães fakes
    for i in range(2, 9):
        fake_id = 1000 + i
        db.register_player(fake_id, f"Capitao_{i}", f"Capitão Fake {i}", "GK")
        
    # 32 Jogadores de linha fakes (8 de cada posição)
    line_positions = ["Fixo", "Ala Def", "Ala Of", "Pivô"]
    uid_counter = 2000
    for pos in line_positions:
        for i in range(1, 9):
            db.register_player(uid_counter, f"Jogador_{pos}_{i}", f"Falso {pos} {i}", pos)
            uid_counter += 1
            
    # Iniciar draft
    regs = db.get_registrations()
    captains = []
    for pid, p in regs.items():
        if p["position"] == "GK":
            captains.append(p)
            
    random.shuffle(captains)
    db.setup_draft(captains, regs)
    
    # Salvar ID do admin tester no db
    state = db._load_state()
    state["draft"]["admin_tester_id"] = admin_id
    db._save_state(state)
    
    await ctx.send("🚀 **Iniciando Mix Teste com 8 Times!**")
    await ctx.send("🤖 Bots inscritos e draft gerado automaticamente.")
    
    # Começar a simulação
    await run_simulated_draft_turns(ctx.channel, admin_id)

@bot.command(name="mixcomecar")
@commands.has_permissions(administrator=True)
async def cmd_mixcomecar(ctx):
    db.reset_db()
    regs = db.get_registrations()
    embed = get_registration_embed(regs)
    view = RegistrationView()
    await ctx.send("🧹 Banco de dados limpo e novas inscrições abertas!")
    msg = await ctx.send(embed=embed, view=view)
    db.set_registration_message(ctx.channel.id, msg.id)

@bot.command(name="painel_inscricao")
@commands.has_permissions(administrator=True)
async def cmd_painel_inscricao(ctx):
    phase = db.get_phase()
    if phase != "inscricao" and phase != "draft":
        return await ctx.send("❌ O mix não está na fase de inscrições ou draft no momento.")
        
    regs = db.get_registrations()
    embed = get_registration_embed(regs)
    view = RegistrationView()
    msg = await ctx.send(embed=embed, view=view)
    db.set_registration_message(ctx.channel.id, msg.id)

@bot.command(name="inscritos")
async def cmd_inscritos(ctx):
    regs = db.get_registrations()
    
    embed = discord.Embed(title="📋 Jogadores Inscritos", color=discord.Color.blue())
    
    # Agrupar por posição
    grouped = {pos: [] for pos in POSITIONS}
    for pid, p in regs.items():
        grouped[p["position"]].append(f"<@{p['user_id']}> ({p['display_name']})")
        
    total = len(regs)
    embed.description = f"Total de inscritos: **{total}** jogadores"
    
    for pos in POSITIONS:
        players = grouped[pos]
        count = len(players)
        list_text = "\n".join(players) if players else "*Ninguém inscrito*"
        embed.add_field(name=f"{pos} ({count})", value=list_text, inline=False)
        
    await ctx.send(embed=embed)

@bot.command(name="elenco")
async def cmd_elenco(ctx):
    # Verificar a fase atual
    phase = db.get_phase()
    if phase == "inscricao":
        return await ctx.send("❌ Os times ainda não foram formados (fase de Inscrição).")
        
    teams = db.get_teams()
    if not teams:
        return await ctx.send("❌ Nenhum time encontrado.")
        
    COUNTRY_INFO = {
        "Brasil": {"flag": "🇧🇷", "abbr": "BR"},
        "França": {"flag": "🇫🇷", "abbr": "FRA"},
        "Espanha": {"flag": "🇪🇸", "abbr": "ESP"},
        "Inglaterra": {"flag": "🇬🇧", "abbr": "ING"},
        "Argentina": {"flag": "🇦🇷", "abbr": "ARG"},
        "Alemanha": {"flag": "🇩🇪", "abbr": "ALE"},
        "Croácia": {"flag": "🇭🇷", "abbr": "CRO"},
        "Holanda": {"flag": "🇳🇱", "abbr": "HOL"}
    }
    
    def get_flag(name):
        for country, info in COUNTRY_INFO.items():
            if country in name:
                return info["flag"]
        return "👥"

    embed = discord.Embed(
        title="📋 Elenco dos Times",
        description="Confira a escalação de cada equipe no mix atual!",
        color=discord.Color.blue()
    )
    
    for tid, team in teams.items():
        team_name = team.get("team_name", team.get("captain_name", f"Time {tid[:6]}"))
        flag = get_flag(team_name)
        
        players_text = []
        for pl in team.get("players", []):
            players_text.append(f"• **{pl['position']}**: <@{pl['id']}>")
            
        while len(players_text) < 5:
            players_text.append("• *Vago*")
            
        embed.add_field(
            name=f"{flag} {team_name}",
            value="\n".join(players_text),
            inline=True
        )
        
    await ctx.send(embed=embed)

@bot.command(name="narrar_teste")
async def cmd_narrar_teste(ctx, *, canal_nome: str = None):
    voice_channel = None
    if canal_nome:
        voice_channel = discord.utils.get(ctx.guild.voice_channels, name=canal_nome)
        if not voice_channel:
            for vc in ctx.guild.voice_channels:
                if canal_nome.lower() in vc.name.lower():
                    voice_channel = vc
                    break
    
    if not voice_channel and ctx.author.voice:
        voice_channel = ctx.author.voice.channel
        
    if not voice_channel:
        target_name = "🔥・União M4fiaPitXDFlow"
        voice_channel = discord.utils.get(ctx.guild.voice_channels, name=target_name)
        if not voice_channel:
            for vc in ctx.guild.voice_channels:
                if "união" in vc.name.lower() or "mafia" in vc.name.lower() or "flow" in vc.name.lower():
                    voice_channel = vc
                    break
                    
    if not voice_channel:
        return await ctx.send("❌ Não consegui encontrar o canal de voz. Entre em um canal de voz ou passe o nome correto como argumento (ex: `$narrar_teste 🔥・União M4fiaPitXDFlow`).")
        
    await ctx.send(f"🎙️ **Conectando ao canal `{voice_channel.name}` para testar a narração...**")
    
    text = "Fala galera da Flow Theory! Aqui é o narrador do Mix Rematch na área! Testando o sistema de som 1 2 3! O som tá saindo limpo e com aquela energia lá no alto! Preparem-se porque os confrontos vão ser lendários! Que vença o melhor time!"
    if gemini_client:
        try:
            prompt = (
                "Você é um narrador esportivo brasileiro de eSports de futebol muito empolgado. "
                "Crie uma saudação de teste muito rápida (2 a 3 linhas no máximo) para os membros do servidor 'Flow Theory' "
                "e para o jogador que solicitou o teste. Diga que o som do narrador está funcionando perfeitamente e que os mixes vão pegar fogo!"
                "Retorne apenas o texto final sem aspas ou marcações markdown."
            )
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt
                )
            )
            if response.text:
                text = response.text
        except Exception as e:
            print(f"Erro ao gerar saudação de teste com Gemini: {e}")
            
    asyncio.create_task(play_match_introduction_voice(ctx.guild, voice_channel, text, disconnect=True))

@bot.command(name="narrar_teste_jogos")
async def cmd_narrar_teste_jogos(ctx, *, canal_nome: str = None):
    voice_channel = None
    if canal_nome:
        voice_channel = discord.utils.get(ctx.guild.voice_channels, name=canal_nome)
        if not voice_channel:
            for vc in ctx.guild.voice_channels:
                if canal_nome.lower() in vc.name.lower():
                    voice_channel = vc
                    break
    
    if not voice_channel and ctx.author.voice:
        voice_channel = ctx.author.voice.channel
        
    if not voice_channel:
        target_name = "🔥・União M4fiaPitXDFlow"
        voice_channel = discord.utils.get(ctx.guild.voice_channels, name=target_name)
        if not voice_channel:
            for vc in ctx.guild.voice_channels:
                if "união" in vc.name.lower() or "mafia" in vc.name.lower() or "flow" in vc.name.lower():
                    voice_channel = vc
                    break
                    
    if not voice_channel:
        return await ctx.send("❌ Não consegui encontrar o canal de voz. Entre em um canal de voz ou passe o nome correto como argumento (ex: `$narrar_teste_jogos 🔥・União M4fiaPitXDFlow`).")
        
    await ctx.send(f"🎙️ **Gerando narração de jogo simulada para o canal `{voice_channel.name}`...**")
    
    # Team A: França (GK: magas; Jogadores: killi, galtz, jorg, kayke)
    team_a_name = "França (@magas)"
    a_players = [
        {"name": "magas", "position": "GK"},
        {"name": "killi", "position": "Ala Of"},
        {"name": "galtz", "position": "Fixo"},
        {"name": "jorg", "position": "Ala Def"},
        {"name": "kayke", "position": "Pivô"}
    ]
    
    # Team B: Alemanha (GK: Adversario; Jogadores ficticios)
    team_b_name = "Alemanha (@Adversario)"
    b_players = [
        {"name": "Adversario", "position": "GK"},
        {"name": "Bot_Fixo", "position": "Fixo"},
        {"name": "Bot_AlaDef", "position": "Ala Def"},
        {"name": "Bot_AlaOf", "position": "Ala Of"},
        {"name": "Bot_Pivo", "position": "Pivô"}
    ]
    
    text = "Senhoras e senhores! Preparem seus corações! França e Alemanha vão fazer um clássico monumental! De um lado temos o time de magas, com killi, galtz, jorg e kayke! Do outro lado o time de Adversário! O jogo vai começar!"
    if gemini_client:
        text = await get_match_voice_commentary(team_a_name, team_b_name, a_players, b_players)
        
    if text:
        await ctx.send(f"📖 **Texto que a IA vai falar:**\n*{text}*")
        asyncio.create_task(play_match_introduction_voice(ctx.guild, voice_channel, text, disconnect=True))
    else:
        await ctx.send("❌ Erro ao gerar texto com Gemini.")

@bot.command(name="narrador_voz")
@commands.has_permissions(administrator=True)
async def cmd_narrador_voz(ctx, voz_nome: str = None):
    VOICES_MAP = {
        "antonio": "pt-BR-AntonioNeural",
        "francisca": "pt-BR-FranciscaNeural",
        "thalita": "pt-BR-ThalitaMultilingualNeural"
    }
    
    if not voz_nome or voz_nome.lower() not in VOICES_MAP:
        options = ", ".join([f"`{k}`" for k in VOICES_MAP.keys()])
        curr = get_bot_voice()
        curr_key = "antonio"
        for k, v in VOICES_MAP.items():
            if v == curr:
                curr_key = k
                break
        return await ctx.send(f"🎙️ **Narrador por Voz Atual:** `{curr_key}`\n\nEscolha uma das opções disponíveis:\n{options}\n\nExemplo: `$narrador_voz francisca` para mudar.")
        
    selected_voice = VOICES_MAP[voz_nome.lower()]
    set_bot_voice(selected_voice)
    await ctx.send(f"✅ **Voz do narrador alterada para:** `{voz_nome.lower()}` ({selected_voice})!")

@bot.command(name="narrador_efeito")
@commands.has_permissions(administrator=True)
async def cmd_narrador_efeito(ctx, efeito_nome: str = None):
    effects = ["rapido", "estadio", "grave", "normal"]
    
    if not efeito_nome or efeito_nome.lower() not in effects:
        options = ", ".join([f"`{e}`" for e in effects])
        curr = get_bot_voice_effect()
        return await ctx.send(f"🎙️ **Efeito de Voz Atual:** `{curr}`\n\nEscolha um dos efeitos disponíveis:\n{options}\n\nExemplo: `$narrador_efeito estadio` para mudar.")
        
    selected_effect = efeito_nome.lower()
    set_bot_voice_effect(selected_effect)
    await ctx.send(f"✅ **Efeito de voz do narrador alterado para:** `{selected_effect}`!")

@bot.command(name="cancelar_inscricao")
async def cmd_cancelar_inscricao(ctx):
    phase = db.get_phase()
    if phase != "inscricao" and phase != "draft":
        return await ctx.send("❌ As inscrições estão fechadas.")
        
    success, msg = db.unregister_player(ctx.author.id)
    if success:
        await ctx.send(f"✅ {msg}")
        await update_registration_message()
        if phase == "draft":
            await refresh_draft_message()
    else:
        await ctx.send(f"❌ {msg}")

@bot.command(name="admin_adicionar")
@commands.has_permissions(administrator=True)
async def cmd_admin_adicionar(ctx, usuario: discord.Member, posicao: str):
    if posicao not in POSITIONS:
        return await ctx.send(f"❌ Posição inválida. Escolha uma de: {', '.join(POSITIONS)}")
        
    success, msg = db.register_player(usuario.id, usuario.name, usuario.display_name, posicao)
    if success:
        await ctx.send(f"✅ {msg}")
        await update_registration_message()
        phase = db.get_phase()
        if phase == "draft":
            await refresh_draft_message()
    else:
        await ctx.send(f"❌ {msg}")

@bot.command(name="remover", aliases=["admin_remover"])
@commands.has_permissions(administrator=True)
async def cmd_remover(ctx, usuario: str):
    user_id = None
    import re
    match = re.search(r'\d+', usuario)
    if match:
        user_id = int(match.group())
    else:
        # Procurar por nome ou display_name nas inscrições
        regs = db.get_registrations()
        for pid, p in regs.items():
            if usuario.lower() in p["username"].lower() or usuario.lower() in p["display_name"].lower():
                user_id = int(pid)
                break
                
    if not user_id:
        return await ctx.send("❌ Não consegui identificar o usuário. Use a menção (@Nome), o ID numérico ou o nome do inscrito.")
        
    success, msg = db.unregister_player(user_id)
    if success:
        await ctx.send(f"✅ {msg}")
        await update_registration_message(channel_to_fallback=ctx.channel)
        phase = db.get_phase()
        if phase == "draft":
            await refresh_draft_message()
    else:
        await ctx.send(f"❌ {msg}")

@bot.command(name="admin_limpar")
@commands.has_permissions(administrator=True)
async def cmd_admin_limpar(ctx):
    db.reset_db()
    await ctx.send("✅ Banco de dados redefinido com sucesso! O mix voltou para a fase de **Inscrição**.")

@bot.command(name="reset", aliases=["cancelaratual"])
@commands.has_permissions(administrator=True)
async def cmd_reset(ctx):
    # 1. Obter informações de canais a deletar antes de limpar o DB
    state = db._load_state()
    
    # 2. Deletar canais de confronto
    matches = state.get("bracket", {}).get("matches", {})
    for mid, match in list(matches.items()):
        category_id = match.get("confrontation_category_id")
        channel_id = match.get("confrontation_channel_id")
        voice_a_id = match.get("confrontation_voice_a_id")
        voice_b_id = match.get("confrontation_voice_b_id")
        
        if channel_id:
            try:
                chan = ctx.guild.get_channel(channel_id)
                if not chan:
                    chan = await bot.fetch_channel(channel_id)
                if chan:
                    await chan.delete()
            except Exception as e:
                print(f"Erro ao deletar canal de texto do confronto {mid}: {e}")
                
        if voice_a_id:
            try:
                vc = ctx.guild.get_channel(voice_a_id)
                if not vc:
                    vc = await bot.fetch_channel(voice_a_id)
                if vc:
                    await vc.delete()
            except Exception as e:
                print(f"Erro ao deletar canal de voz A do confronto {mid}: {e}")
                
        if voice_b_id:
            try:
                vc = ctx.guild.get_channel(voice_b_id)
                if not vc:
                    vc = await bot.fetch_channel(voice_b_id)
                if vc:
                    await vc.delete()
            except Exception as e:
                print(f"Erro ao deletar canal de voz B do confronto {mid}: {e}")
                
        if category_id:
            try:
                cat = ctx.guild.get_channel(category_id)
                if not cat:
                    cat = await bot.fetch_channel(category_id)
                if cat:
                    await cat.delete()
            except Exception as e:
                print(f"Erro ao deletar categoria do confronto {mid}: {e}")

    # 3. Deletar categoria de calls dos times
    try:
        await delete_team_voice_channels(ctx.guild)
    except Exception as e:
        print(f"Erro ao deletar calls dos times: {e}")

    # 4. Deletar mensagem de draft se existir
    try:
        draft_chan_id, draft_msg_id = db.get_draft_message()
        if draft_chan_id and draft_msg_id:
            draft_chan = bot.get_channel(draft_chan_id)
            if not draft_chan:
                draft_chan = await bot.fetch_channel(draft_chan_id)
            if draft_chan:
                draft_msg = await draft_chan.fetch_message(draft_msg_id)
                if draft_msg:
                    await draft_msg.delete()
    except Exception as e:
        print(f"Erro ao deletar mensagem de draft: {e}")

    # 5. Deletar mensagem de bracket se existir
    try:
        bracket_state = state.get("bracket", {})
        bracket_chan_id = bracket_state.get("channel_id")
        bracket_msg_id = bracket_state.get("message_id")
        if bracket_chan_id and bracket_msg_id:
            bracket_chan = bot.get_channel(bracket_chan_id)
            if not bracket_chan:
                bracket_chan = await bot.fetch_channel(bracket_chan_id)
            if bracket_chan:
                bracket_msg = await bracket_chan.fetch_message(bracket_msg_id)
                if bracket_msg:
                    await bracket_msg.delete()
    except Exception as e:
        print(f"Erro ao deletar mensagem de bracket: {e}")

    # 6. Limpar o banco mantendo inscrições
    db.cancel_picks()

    # 7. Atualizar painel de inscrição para ficar ativo novamente
    await update_registration_message(channel_to_fallback=ctx.channel)

    await ctx.send("✅ **Picks e confrontos atuais cancelados!** O mix voltou para a fase de **Inscrição** mantendo todos os jogadores inscritos.")

async def iniciar_draft_helper(ctx, pick_rounds):
    phase = db.get_phase()
    if phase != "inscricao":
        return await ctx.send("❌ Só é possível iniciar o draft a partir da fase de Inscrição.")
        
    regs = db.get_registrations()
    
    # Separar capitães (GKs) e jogadores de linha
    captains = []
    field_players_count = 0
    
    for pid, p in regs.items():
        if p["position"] == CAPTAIN_POSITION:
            captains.append(p)
        else:
            field_players_count += 1
            
    num_captains = len(captains)
    if num_captains < 2:
        return await ctx.send("❌ É necessário ter pelo menos 2 Goleiros (GK) inscritos para formar equipes.")
        
    # Verificar se há jogadores de linha suficientes no total para todos os times
    needed_players = num_captains * pick_rounds
    if field_players_count < needed_players:
        missing_count = needed_players - field_players_count
        return await ctx.send(f"❌ Não há jogadores de linha suficientes! Faltam {missing_count} jogadores no total para o formato escolhido.")

    # Shufflar capitães para ordem aleatória
    random.shuffle(captains)
    
    db.setup_draft(captains, regs, pick_rounds=pick_rounds)
    
    await ctx.send(f"🚀 O Draft de **{pick_rounds} Escolhas** foi iniciado! Painel de escolhas enviado abaixo.")
    
    # Enviar mensagem do draft no canal
    draft_state = db.get_draft_state()
    embed = get_draft_embed(draft_state, regs)
    
    # Buscar lista de jogadores disponíveis para escolhas
    available_players = {}
    for pid, p in regs.items():
        if pid not in draft_state["captains"]:
            available_players[pid] = p
            
    active_captain_id = draft_state["order"][0]
    
    view = DraftView(available_players, active_captain_id)
    draft_msg = await ctx.send(embed=embed, view=view)
    db.set_draft_message(ctx.channel.id, draft_msg.id)

@bot.command(name="bracket")
async def cmd_bracket(ctx):
    phase = db.get_phase()
    if phase != "bracket":
        return await ctx.send("❌ Não há um campeonato ativo com chaveamento (bracket) no momento.")
        
    await send_bracket_status(ctx.channel)
    await start_active_match_votings(ctx.channel)

@bot.command(name="bracket_chats")
@commands.has_permissions(administrator=True)
async def cmd_bracket_chats(ctx):
    phase = db.get_phase()
    if phase != "bracket":
        return await ctx.send("❌ Só é possível rodar este comando durante a fase de Bracket.")
        
    bracket_state = db.get_bracket_state()
    matches = bracket_state.get("matches", {})
    ongoing_matches = [m for m in matches.values() if m.get("status") == "ongoing"]
    if not ongoing_matches:
        return await ctx.send("❌ Nenhuma partida em andamento encontrada.")
        
    sent_count = 0
    for match in ongoing_matches:
        chan_id = match.get("confrontation_channel_id")
        if chan_id:
            channel = ctx.guild.get_channel(chan_id)
            if not channel:
                try:
                    channel = await ctx.guild.fetch_channel(chan_id)
                except:
                    pass
            if channel:
                await send_bracket_to_confrontation(channel)
                sent_count += 1
                
    await ctx.send(f"✅ Chaveamento enviado com sucesso para {sent_count} canal(is) de confronto ativos!")

@bot.command(name="refazer_bracket")
@commands.has_permissions(administrator=True)
async def cmd_refazer_bracket(ctx):
    # 1. Obter informações de canais a deletar
    state = db._load_state()
    matches = state.get("bracket", {}).get("matches", {})
    
    await ctx.send("🔄 **Iniciando a regeneração do chaveamento...**")
    
    # 2. Deletar canais de confronto antigos
    for mid, match in list(matches.items()):
        category_id = match.get("confrontation_category_id")
        channel_id = match.get("confrontation_channel_id")
        voice_a_id = match.get("confrontation_voice_a_id")
        voice_b_id = match.get("confrontation_voice_b_id")
        
        if channel_id:
            try:
                chan = ctx.guild.get_channel(channel_id)
                if not chan:
                    chan = await bot.fetch_channel(channel_id)
                if chan: await chan.delete()
            except Exception as e:
                print(f"Erro ao deletar canal de texto {mid}: {e}")
                
        if voice_a_id:
            try:
                vc = ctx.guild.get_channel(voice_a_id)
                if not vc:
                    vc = await bot.fetch_channel(voice_a_id)
                if vc: await vc.delete()
            except Exception as e:
                print(f"Erro ao deletar call A {mid}: {e}")
                
        if voice_b_id:
            try:
                vc = ctx.guild.get_channel(voice_b_id)
                if not vc:
                    vc = await bot.fetch_channel(voice_b_id)
                if vc: await vc.delete()
            except Exception as e:
                print(f"Erro ao deletar call B {mid}: {e}")
                
        if category_id:
            try:
                cat = ctx.guild.get_channel(category_id)
                if not cat:
                    cat = await bot.fetch_channel(category_id)
                if cat: await cat.delete()
            except Exception as e:
                print(f"Erro ao deletar categoria {mid}: {e}")
                
    # 3. Deletar categoria de calls dos times se houver
    try:
        await delete_team_voice_channels(ctx.guild)
    except Exception as e:
        print(f"Erro ao deletar calls dos times: {e}")

    # 4. Deletar mensagem principal da bracket se existir
    try:
        bracket_state = state.get("bracket", {})
        bracket_chan_id = bracket_state.get("channel_id")
        bracket_msg_id = bracket_state.get("message_id")
        if bracket_chan_id and bracket_msg_id:
            bracket_chan = bot.get_channel(bracket_chan_id)
            if not bracket_chan:
                bracket_chan = await bot.fetch_channel(bracket_chan_id)
            if bracket_chan:
                try:
                    bracket_msg = await bracket_chan.fetch_message(bracket_msg_id)
                    if bracket_msg: await bracket_msg.delete()
                except Exception:
                    pass
    except Exception as e:
        print(f"Erro ao deletar mensagem de bracket: {e}")

    # 5. Reinicializar estado da bracket no DB
    db.set_phase("bracket")
    
    # 6. Gerar e enviar o novo chaveamento
    await generate_and_send_bracket(ctx.channel)
    
    await ctx.send("✅ **Chaveamento (Bracket) regenerado com sucesso!** Os novos canais de confronto e calls foram recriados.")

@bot.command(name="mix5x5")
@commands.has_permissions(administrator=True)
async def cmd_mix5x5(ctx):
    await iniciar_draft_helper(ctx, pick_rounds=4)

@bot.command(name="mix4x4")
@commands.has_permissions(administrator=True)
async def cmd_mix4x4(ctx):
    await iniciar_draft_helper(ctx, pick_rounds=3)

@bot.command(name="mix3x3")
@commands.has_permissions(administrator=True)
async def cmd_mix3x3(ctx):
    await iniciar_draft_helper(ctx, pick_rounds=2)

@bot.command(name="mix2x2")
@commands.has_permissions(administrator=True)
async def cmd_mix2x2(ctx):
    await iniciar_draft_helper(ctx, pick_rounds=1)

@bot.command(name="mix1x1")
@commands.has_permissions(administrator=True)
async def cmd_mix1x1(ctx):
    await iniciar_draft_helper(ctx, pick_rounds=1)

@bot.command(name="proteger")
@commands.has_permissions(administrator=True)
async def cmd_proteger(ctx):
    db.set_phase("protecao")
    db.set_protection_deadline(time.time() + 90)
    await ctx.send("🛡️ **Fase de Proteção ativada manualmente!**")
    await send_protection_panel(ctx.channel)

@bot.command(name="resetarpainel", aliases=["restaurar_painel", "resetpainel", "painelreset"])
@commands.has_permissions(administrator=True)
async def cmd_resetarpainel(ctx):
    phase = db.get_phase()
    await ctx.send("🔄 **Reenviando e resetando o painel atual do mix...**")
    
    if phase == "inscricao":
        await update_registration_message(channel_to_fallback=ctx.channel)
        await ctx.send("✅ **Painel de Inscrições reenviado com sucesso!**")
        
    elif phase == "draft":
        draft_state = db.get_draft_state()
        regs = db.get_registrations()
        
        picked_ids = set()
        for tid, team in draft_state["teams"].items():
            for pl in team["players"]:
                picked_ids.add(str(pl["id"]))
                
        available_players = {}
        for pid, p in regs.items():
            if pid not in picked_ids and pid not in draft_state["captains"]:
                available_players[pid] = p

        curr_idx = draft_state["current_index"]
        order = draft_state["order"]
        
        if curr_idx < len(order):
            active_captain_id = order[curr_idx]
            
            db_state = db._load_state()
            db_state["draft"]["turn_deadline"] = time.time() + 90
            db._save_state(db_state)
            draft_state = db.get_draft_state()
            
            embed = get_draft_embed(draft_state, regs)
            view = DraftView(available_players, active_captain_id)
            msg = await ctx.send(embed=embed, view=view)
            db.set_draft_message(ctx.channel.id, msg.id)
            await ctx.send("✅ **Painel do Draft reenviado com sucesso!**")
        else:
            await ctx.send("ℹ️ O Draft já foi finalizado nesta sessão.")
            
    elif phase == "protecao":
        db.set_protection_deadline(time.time() + 90)
        await send_protection_panel(ctx.channel)
        await ctx.send("✅ **Painel da Fase de Proteção reenviado com sucesso!** (Tempo de 1m30s resetado).")
        
    elif phase == "roubo":
        db_state = db._load_state()
        if "steal" in db_state:
            db_state["steal"]["turn_deadline"] = time.time() + 90
            db._save_state(db_state)
        await send_steal_panel(ctx.channel)
        await ctx.send("✅ **Painel da Fase de Roubo reenviado com sucesso!** (Tempo de 1m30s resetado).")
        
    elif phase == "bracket":
        await send_bracket_status(ctx.channel)
        await start_active_match_votings(ctx.channel)
        await ctx.send("✅ **Painéis do Chaveamento reenviados com sucesso!**")
    else:
        await ctx.send(f"ℹ️ Nenhuma fase ativa com painel interativo encontrada (`Fase atual: {phase}`).")

@bot.command(name="mock_setup")
@commands.has_permissions(administrator=True)
async def cmd_mock_setup(ctx, times: int = 4):
    if times < 2:
        return await ctx.send("❌ Quantidade mínima de times para teste é 2.")
        
    db.reset_db()
    
    # Inserir o próprio usuário que executa como capitão (GK) do Time 1 para poder interagir
    db.register_player(ctx.author.id, ctx.author.name, ctx.author.display_name, "GK")
    
    # Inserir outros capitães fakes
    for i in range(2, times + 1):
        db.register_player(1000 + i, f"Capitao_{i}", f"Capitão Fake {i}", "GK")
        
    # Inserir jogadores de linha fakes (precisamos de `times` jogadores para cada uma das outras 4 posições)
    line_positions = ["Fixo", "Ala Def", "Ala Of", "Pivô"]
    uid_counter = 2000
    for pos in line_positions:
        for i in range(1, times + 1):
            db.register_player(uid_counter, f"Jogador_{pos}_{i}", f"Falso {pos} {i}", pos)
            uid_counter += 1
            
    await ctx.send(f"✅ Setup de simulação completo! Criado {times} Capitães (incluindo você) e {times * 4} jogadores de linha fakes. Use `$inscritos` para ver ou `$iniciar_draft` para testar.")

# Evento on_ready para sincronizar slash commands e registrar views persistentes
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} ({bot.user.id})")
    
    # Iniciar os loops de timeout do draft, protecao e roubo
    if not check_draft_timeout.is_running():
        check_draft_timeout.start()
        print("Loop de timeout do draft iniciado.")

    if not check_protection_timeout.is_running():
        check_protection_timeout.start()
        print("Loop de timeout da proteção iniciado.")

    if not check_steal_timeout.is_running():
        check_steal_timeout.start()
        print("Loop de timeout do roubo iniciado.")
        
    # Resetar os deadlines no startup para evitar expirações abruptas
    try:
        phase = db.get_phase()
        if phase == "draft":
            draft_state = db.get_draft_state()
            if draft_state.get("turn_deadline"):
                db_state = db._load_state()
                db_state["draft"]["turn_deadline"] = time.time() + 90
                db._save_state(db_state)
                print("Deadline do draft resetado para 90s no startup.")
        elif phase == "protecao":
            deadline = db.get_protection_deadline()
            if deadline:
                db.set_protection_deadline(time.time() + 90)
                print("Deadline da proteção resetado para 90s no startup.")
        elif phase == "roubo":
            steal_state = db.get_steal_state()
            if steal_state.get("turn_deadline"):
                db_state = db._load_state()
                db_state["steal"]["turn_deadline"] = time.time() + 90
                db._save_state(db_state)
                print("Deadline do roubo resetado para 90s no startup.")
    except Exception as e:
        print(f"Erro ao resetar deadline do draft no startup: {e}")

    # Registrar views persistentes básicas
    bot.add_view(RegistrationView())
    bot.add_view(ProtectionView())
    bot.add_view(TicketSelectView())
    bot.add_view(CloseTicketView())
    bot.add_view(GossipPanelView())
    print("Views persistentes de Inscrição, Proteção, Tickets e Fofocas registradas.")

    try:
        synced = await bot.tree.sync()
        print(f"Sincronizados {len(synced)} comandos slash globalmente.")
    except Exception as e:
        print(f"Erro ao sincronizar comandos slash: {e}")

# ==========================================
# NOVOS SISTEMAS: TICKETS, ANÚNCIOS, TIMES, FOFOCAS E CAMPEONATOS
# ==========================================

# --- SISTEMA DE TICKETS ---
class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Pagar Inscrição", value="pagar_inscricao", emoji="🎟️", description="Enviar comprovante ou pagar taxa de inscrição"),
            discord.SelectOption(label="Dúvidas", value="duvidas", emoji="❓", description="Tirar dúvidas gerais sobre o campeonato/servidor"),
            discord.SelectOption(label="Criar Time", value="criar_time", emoji="🛡️", description="Suporte para cadastrar novo time"),
            discord.SelectOption(label="Denúncia", value="denuncia", emoji="⚠️", description="Fazer denúncia sobre comportamento ou partida"),
            discord.SelectOption(label="Parcerias", value="parcerias", emoji="🤝", description="Propostas de parcerias com o torneio"),
            discord.SelectOption(label="Doações", value="doacoes", emoji="💎", description="Contribuir com o prize pool do evento"),
            discord.SelectOption(label="Reportar Bug", value="reportar_bug", emoji="🐛", description="Reportar bugs ou problemas técnicos")
        ]
        super().__init__(placeholder="Selecione o motivo do atendimento...", min_values=1, max_values=1, options=options, custom_id="ticket_select_menu")

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        category_name = "TICKETS"
        category = discord.utils.get(guild.categories, name=category_name)
        if not category:
            category = await guild.create_category(category_name)

        user = interaction.user
        category_val = self.values[0]
        category_label = [opt.label for opt in self.options if opt.value == category_val][0]
        
        channel_name = f"ticket-{user.name.lower()}-{category_val}".replace(" ", "-")
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        # Conceder acesso aos administradores
        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        ticket_channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)
        db.add_ticket(ticket_channel.id, user.id, category_val)

        embed = discord.Embed(
            title=f"🎫 Atendimento: {category_label}",
            description=f"Olá {user.mention}! Seu ticket foi aberto com sucesso.\nPor favor, descreva em detalhes a sua solicitação. A equipe de administração irá atendê-lo em breve.",
            color=discord.Color.purple()
        )
        embed.set_footer(text="Rematch Tournament System • Clique no botão abaixo para encerrar o ticket.")
        
        await ticket_channel.send(embed=embed, view=CloseTicketView())
        await interaction.response.send_message(f"✅ Seu ticket foi criado em {ticket_channel.mention}!", ephemeral=True)

class TicketSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Fechar Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 **Ticket encerrado!** Este canal será excluído em 5 segundos...", ephemeral=False)
        db.close_ticket_db(interaction.channel.id)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason="Ticket Fechado")
        except Exception as e:
            print(f"Erro ao deletar canal do ticket: {e}")

@bot.command(name="ticket")
@commands.has_permissions(administrator=True)
async def cmd_ticket(ctx):
    """Cria o painel interativo de suporte por tickets"""
    embed = discord.Embed(
        title="🎫 Central de Atendimento & Suporte - Rematch",
        description="Selecione abaixo no menu a categoria referente ao seu atendimento para abrir um canal privado de suporte com nossa equipe de administradores.",
        color=discord.Color.purple()
    )
    banner_path = "ticket_banner.png"
    if os.path.exists(banner_path):
        file = discord.File(banner_path, filename="ticket_banner.png")
        embed.set_image(url="attachment://ticket_banner.png")
        embed.set_footer(text="Rematch Championship • Suporte Oficial")
        await ctx.send(embed=embed, file=file, view=TicketSelectView())
    else:
        embed.set_image(url="https://images.unsplash.com/photo-1542751371-adc38448a05e?q=80&w=1000&auto=format&fit=crop")
        embed.set_footer(text="Rematch Championship • Suporte Oficial")
        await ctx.send(embed=embed, view=TicketSelectView())

# --- SISTEMA DE ANÚNCIOS ---
@bot.command(name="anunciar", aliases=["anuncio"])
@commands.has_permissions(administrator=True)
async def cmd_anunciar(ctx, canal: discord.TextChannel = None, *, texto: str = ""):
    """Envia um anúncio oficial no canal especificado com imagem anexada se houver"""
    target_channel = canal or ctx.channel
    
    image_url = None
    if ctx.message.attachments:
        image_url = ctx.message.attachments[0].url
        
    if not texto and not image_url:
        return await ctx.send("❌ Você deve fornecer um texto ou anexar uma imagem para realizar o anúncio.\nExemplo: `!anunciar #anúncios Teremos campeonato neste sábado!`")

    embed = discord.Embed(
        title="📢 Anúncio Oficial - Rematch",
        description=texto,
        color=discord.Color.from_rgb(124, 58, 237)
    )
    if image_url:
        embed.set_image(url=image_url)
        
    embed.set_footer(text=f"Anunciado por {ctx.author.display_name} • Rematch Championship", icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None)
    embed.timestamp = discord.utils.utcnow()

    await target_channel.send("@everyone" if "everyone" in ctx.message.content else "", embed=embed)
    await ctx.send(f"✅ Anúncio enviado com sucesso em {target_channel.mention}!")

# --- SISTEMA DE CRIAÇÃO DE TIMES ---
@bot.command(name="criartime")
async def cmd_criartime(ctx, *, nome_do_time: str = None):
    """Cria um time oficial, faz upload da logo e cria o cargo no servidor"""
    if not nome_do_time:
        return await ctx.send("❌ Por favor, informe o nome do time!\nExemplo: `!criartime Rissel Gaming`")

    # Verificar se time já existe
    existing = db.get_custom_team_by_role_or_name(nome_do_time)
    if existing:
        return await ctx.send(f"❌ O time **{nome_do_time}** já existe no sistema!")

    prompt_msg = await ctx.send(f"🛡️ **Criação de Time: {nome_do_time}**\nPor favor, responda a esta mensagem enviando a **imagem da logo do time** como anexo (você tem 60 segundos):")

    def check(m):
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id and len(m.attachments) > 0

    try:
        msg = await bot.wait_for("message", check=check, timeout=60.0)
    except asyncio.TimeoutError:
        return await ctx.send("⏱️ Tempo esgotado! A criação do time foi cancelada pois nenhuma imagem de logo foi enviada.")

    attachment = msg.attachments[0]
    if not attachment.content_type or not attachment.content_type.startswith("image/"):
        return await ctx.send("❌ O arquivo enviado não é uma imagem válida.")

    os.makedirs("logos", exist_ok=True)
    clean_filename = "".join(c for c in nome_do_time if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_").lower()
    logo_path = os.path.join("logos", f"{clean_filename}_{ctx.author.id}.png")

    try:
        await attachment.save(logo_path)
    except Exception as e:
        return await ctx.send(f"❌ Erro ao salvar a logo do time: {e}")

    # Criar cargo no Discord
    try:
        role = await ctx.guild.create_role(name=f"[{nome_do_time}]", color=discord.Color.random(), mentionable=True, reason=f"Cargo criado para o time {nome_do_time} por {ctx.author.display_name}")
        await ctx.author.add_roles(role)
    except Exception as e:
        return await ctx.send(f"❌ Erro ao criar o cargo do time no servidor: {e}")

    # Salvar no BD
    team_data = db.save_custom_team(
        team_id=role.id,
        name=nome_do_time,
        role_id=role.id,
        leader_id=ctx.author.id,
        leader_name=ctx.author.display_name,
        logo_path=logo_path
    )

    embed = discord.Embed(
        title=f"🛡️ Time Criado com Sucesso: {nome_do_time}",
        description=f"Líder: {ctx.author.mention}\nCargo: {role.mention}\nLogo carregada e registrada com sucesso!",
        color=discord.Color.green()
    )
    
    file = discord.File(logo_path, filename="logo.png")
    embed.set_thumbnail(url="attachment://logo.png")
    embed.set_footer(text="Rematch Championship System")

    await ctx.send(embed=embed, file=file)

# --- SISTEMA DE FOFOCAS ANÔNIMAS ---
class GossipApprovalView(discord.ui.View):
    def __init__(self, author_id: int, gossip_text: str):
        super().__init__(timeout=None)
        self.author_id = author_id
        self.gossip_text = gossip_text

    @discord.ui.button(label="✅ Aceitar", style=discord.ButtonStyle.success, custom_id="gossip_approve_btn")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem aprovar fofocas.", ephemeral=True)

        gossip_channel_id = db.get_gossip_channel()
        if not gossip_channel_id:
            return await interaction.response.send_message("❌ O canal público de fofocas não foi configurado (`!fofocaaqui`).", ephemeral=True)

        gossip_channel = interaction.client.get_channel(gossip_channel_id)
        if not gossip_channel:
            return await interaction.response.send_message("❌ Canal público de fofocas não encontrado.", ephemeral=True)

        # Publicar fofoca anônima no canal público
        num = db.increment_gossip_count()
        db.record_gossip_sent(self.author_id)

        embed = discord.Embed(
            title=f"🤫 FOFOCA ANÔNIMA DO REMATCH #{num}",
            description=f"\"{self.gossip_text}\"",
            color=discord.Color.from_rgb(139, 92, 246)
        )
        embed.set_footer(text="Fofoca enviada de forma 100% anônima via Bot • Rematch Scene")
        embed.timestamp = discord.utils.utcnow()

        await gossip_channel.send(embed=embed)

        # Notificar o autor no privado (DM)
        try:
            author = await interaction.client.fetch_user(self.author_id)
            if author:
                dm = await author.create_dm()
                await dm.send("✅ **Sua fofoca foi APROVADA por um administrador e publicada no canal oficial de fofocas!**")
        except Exception as e:
            print(f"Erro ao avisar autor no DM: {e}")

        # Atualizar mensagem de aprovação no canal dos ADMs (Mantendo o autor anônimo)
        embed_updated = interaction.message.embeds[0]
        embed_updated.color = discord.Color.green()
        embed_updated.title = "✅ Fofoca Aprovada & Publicada"
        embed_updated.description = f"**Conteúdo:**\n\"{self.gossip_text}\""
        embed_updated.set_footer(text=f"Aprovada por {interaction.user.display_name}")

        await interaction.response.edit_message(embed=embed_updated, view=None)

    @discord.ui.button(label="❌ Negar", style=discord.ButtonStyle.danger, custom_id="gossip_reject_btn")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem rejeitar fofocas.", ephemeral=True)

        # Notificar o autor no privado (DM)
        try:
            author = await interaction.client.fetch_user(self.author_id)
            if author:
                dm = await author.create_dm()
                await dm.send("❌ **Sua fofoca foi REJEITADA por um administrador e não foi publicada.**")
        except Exception as e:
            print(f"Erro ao avisar autor no DM: {e}")

        # Atualizar mensagem no canal dos ADMs revelando o autor somente ao negar
        embed_updated = interaction.message.embeds[0]
        embed_updated.color = discord.Color.red()
        embed_updated.title = "❌ Fofoca Rejeitada"
        embed_updated.description = f"**Conteúdo:**\n\"{self.gossip_text}\"\n\n**Autor da Fofoca Rejeitada:** <@{self.author_id}>"
        embed_updated.set_footer(text=f"Rejeitada por {interaction.user.display_name}")

        await interaction.response.edit_message(embed=embed_updated, view=None)

class GossipConfirmView(discord.ui.View):
    def __init__(self, gossip_text: str):
        super().__init__(timeout=120)
        self.gossip_text = gossip_text

    @discord.ui.button(label="✅ Sim, Enviar Fofoca!", style=discord.ButtonStyle.success, custom_id="confirm_gossip")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        approval_channel_id = db.get_gossip_approval_channel()
        if approval_channel_id:
            approval_channel = interaction.client.get_channel(approval_channel_id)
            if approval_channel:
                embed_app = discord.Embed(
                    title="⏳ Nova Fofoca Aguardando Aprovação",
                    description=f"**Conteúdo:**\n\"{self.gossip_text}\"",
                    color=discord.Color.gold()
                )
                embed_app.set_footer(text="Fofoca Anônima • Clique em Aceitar para publicar no canal oficial, ou Negar para recusar.")
                await approval_channel.send(embed=embed_app, view=GossipApprovalView(interaction.user.id, self.gossip_text))
                await interaction.response.send_message("✅ **Sua fofoca foi enviada para a moderação!** Um administrador irá analisar e, se aprovada, ela será publicada no canal oficial de fofocas.", ephemeral=False)
                self.stop()
                return

        # Se não houver canal de aprovação configurado, publica diretamente
        channel_id = db.get_gossip_channel()
        if not channel_id:
            return await interaction.response.send_message("❌ O canal de fofocas não está configurado no servidor.", ephemeral=True)

        gossip_channel = interaction.client.get_channel(channel_id)
        if not gossip_channel:
            return await interaction.response.send_message("❌ Canal de fofocas não encontrado.", ephemeral=True)

        num = db.increment_gossip_count()
        db.record_gossip_sent(interaction.user.id)

        embed = discord.Embed(
            title=f"🤫 FOFOCA ANÔNIMA DO REMATCH #{num}",
            description=f"\"{self.gossip_text}\"",
            color=discord.Color.from_rgb(139, 92, 246)
        )
        embed.set_footer(text="Fofoca enviada de forma 100% anônima via Bot • Rematch Scene")
        embed.timestamp = discord.utils.utcnow()

        await gossip_channel.send(embed=embed)
        await interaction.response.send_message("✅ **Sua fofoca foi enviada e publicada anonimamente com sucesso no canal de fofocas!**", ephemeral=False)
        self.stop()

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger, custom_id="cancel_gossip")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Envio de fofoca cancelado.", ephemeral=False)
        self.stop()

class GossipPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🤫 Enviar Fofoca Anônima", style=discord.ButtonStyle.primary, custom_id="send_gossip_btn")
    async def send_gossip(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel_id = db.get_gossip_channel()
        if not channel_id:
            return await interaction.response.send_message("❌ O canal de fofocas ainda não foi configurado pelos administradores (`!fofocaaqui`).", ephemeral=True)

        user = interaction.user

        # Defer a resposta para evitar timeout de 3 segundos no Discord
        await interaction.response.defer(ephemeral=True)

        try:
            dm_channel = await user.create_dm()
            await dm_channel.send("🤫 **Central de Fofocas Anônimas do Rematch**\nPor favor, responda a esta mensagem escrevendo a fofoca que você deseja publicar. Ninguém saberá quem você é!")
            await interaction.followup.send("📩 Te enviei uma mensagem no seu privado (DM)! Responda por lá para mandar sua fofoca com total anonimato.", ephemeral=True)
        except Exception as e:
            return await interaction.followup.send("❌ Não consegui te enviar uma mensagem privada no DM. Verifique se suas DMs estão abertas para membros do servidor.", ephemeral=True)

        def check(m):
            return m.author.id == user.id and isinstance(m.channel, discord.DMChannel)

        try:
            msg = await interaction.client.wait_for("message", check=check, timeout=300.0)
        except asyncio.TimeoutError:
            return await dm_channel.send("⏱️ Tempo esgotado! O envio da fofoca foi cancelado.")

        gossip_text = msg.content
        embed_confirm = discord.Embed(
            title="🤫 Confirmar Fofoca Anônima",
            description=f"Sua fofoca é:\n\n> **{gossip_text}**\n\n*A fofoca está correta e pronta para ser enviada?*",
            color=discord.Color.purple()
        )
        await dm_channel.send(embed=embed_confirm, view=GossipConfirmView(gossip_text))

@bot.command(name="fofocaaqui")
@commands.has_permissions(administrator=True)
async def cmd_fofocaaqui(ctx):
    """Define o canal atual como o canal oficial para fofocas anônimas do Rematch"""
    db.set_gossip_channel(ctx.channel.id)
    await ctx.send(f"🤫 **Canal {ctx.channel.mention} configurado como o canal oficial de Fofocas Anônimas!**")

@bot.command(name="fofocaaprovar", aliases=["fofoca_aprovar"])
@commands.has_permissions(administrator=True)
async def cmd_fofocaaprovar(ctx):
    """Define o canal atual como o canal de aprovação de fofocas para os administradores"""
    db.set_gossip_approval_channel(ctx.channel.id)
    await ctx.send(f"📋 **Canal {ctx.channel.mention} configurado como o canal de aprovação de fofocas para os administradores!**")

@bot.command(name="fofoca")
async def cmd_fofoca(ctx):
    """Envia o painel interativo de fofocas anônimas"""
    embed = discord.Embed(
        title="🤫 Central de Fofocas Anônimas do Rematch",
        description="Ficou sabendo de algum babado, transferência ou polêmica do cenário de Rematch?\nClique no botão abaixo para enviar sua fofoca. O bot irá te chamar no privado para coletar o texto e publicar de forma **100% ANÔNIMA**!",
        color=discord.Color.from_rgb(168, 85, 247)
    )
    embed.set_footer(text="Rematch Gossip Hub • Total Sigilo")
    await ctx.send(embed=embed, view=GossipPanelView())

# --- SISTEMA DE INSCRIÇÕES & LISTA EM TEMPO REAL ---
async def update_live_teams_panel(bot_client, guild):
    channel_id, message_id = db.get_live_message()
    if not channel_id or not message_id:
        return

    channel = bot_client.get_channel(channel_id)
    if not channel:
        return

    try:
        msg = await channel.fetch_message(message_id)
    except Exception:
        return

    champ_config = db.get_championship_config()
    reg_ids = champ_config.get("registered_team_ids", [])
    custom_teams = db.get_custom_teams()

    embed = discord.Embed(
        title=f"🏆 {champ_config.get('name', 'Campeonato Rematch')} - Times Inscritos",
        description=f"Total de Times Inscritos: **{len(reg_ids)}**\nFormato: **{champ_config.get('format', 'Single Elimination').upper()}** | Premiação: **{champ_config.get('prize_type', 'Porcentagem').upper()}**",
        color=discord.Color.gold()
    )

    if not reg_ids:
        embed.add_field(name="Times", value="Nenhum time inscrito até o momento. Use `!inscrever @cargo_do_time` para se inscrever!", inline=False)
    else:
        teams_text = ""
        for idx, tid in enumerate(reg_ids, start=1):
            t = custom_teams.get(str(tid))
            if t:
                teams_text += f"**{idx}.** <@&{t['role_id']}> (Líder: <@{t['leader_id']}>)\n"
            else:
                teams_text += f"**{idx}.** Time ID {tid}\n"
        embed.add_field(name="Times Confirmados", value=teams_text, inline=False)

    embed.set_footer(text="Lista atualizada em tempo real • Rematch Championship")
    embed.timestamp = discord.utils.utcnow()
    await msg.edit(embed=embed)

@bot.command(name="inscrever")
async def cmd_inscrever(ctx, *, nome_ou_mencao: str = None):
    """Inscreve um time no campeonato ativo"""
    if not nome_ou_mencao:
        return await ctx.send("❌ Por favor, informe o cargo ou o nome do time para inscrever!\nExemplo: `!inscrever @Rissel Gaming` ou `!inscrever Rissel Gaming`")

    role_id = None
    if ctx.message.role_mentions:
        role_id = ctx.message.role_mentions[0].id
    else:
        target_name = nome_ou_mencao.lstrip("@").strip()
        custom_teams = db.get_custom_teams()
        for tid, t in custom_teams.items():
            if t.get("name", "").lower() == target_name.lower() or str(t.get("role_id")) == target_name:
                role_id = t.get("role_id")
                break

    if not role_id:
        return await ctx.send(f"❌ Time **{nome_ou_mencao}** não foi encontrado no sistema. Crie o time primeiro usando `!criartime <Nome do Time>`.")

    team = db.get_custom_team_by_role_or_name(role_id)
    if not team:
        return await ctx.send("❌ Erro ao localizar os dados do time.")

    success, msg = db.register_team_for_championship(team["id"])
    if success:
        await ctx.send(f"✅ **O time <@&{team['role_id']}> foi inscrito com sucesso no campeonato!**")
        await update_live_teams_panel(bot, ctx.guild)
    else:
        await ctx.send(f"⚠️ {msg}")

@bot.command(name="timesinscritos")
async def cmd_timesinscritos(ctx):
    """Exibe e fixa o painel de times inscritos no campeonato que atualiza em tempo real"""
    champ_config = db.get_championship_config()
    reg_ids = champ_config.get("registered_team_ids", [])
    custom_teams = db.get_custom_teams()

    embed = discord.Embed(
        title=f"🏆 {champ_config.get('name', 'Campeonato Rematch')} - Times Inscritos",
        description=f"Total de Times Inscritos: **{len(reg_ids)}**\nFormato: **{champ_config.get('format', 'Single Elimination').upper()}**",
        color=discord.Color.gold()
    )

    if not reg_ids:
        embed.add_field(name="Times", value="Nenhum time inscrito até o momento. Use `!inscrever @cargo_do_time` para se inscrever!", inline=False)
    else:
        teams_text = ""
        for idx, tid in enumerate(reg_ids, start=1):
            t = custom_teams.get(str(tid))
            if t:
                teams_text += f"**{idx}.** <@&{t['role_id']}> (Líder: <@{t['leader_id']}>)\n"
            else:
                teams_text += f"**{idx}.** Time ID {tid}\n"
        embed.add_field(name="Times Confirmados", value=teams_text, inline=False)

    embed.set_footer(text="Lista atualizada em tempo real • Rematch Championship")
    embed.timestamp = discord.utils.utcnow()

    msg = await ctx.send(embed=embed)
    db.set_live_message(ctx.channel.id, msg.id)

# --- SISTEMA DE CONFIGURAÇÃO DE CAMPEONATO E BRACKETS ---
class ConfirmBracketView(discord.ui.View):
    def __init__(self, matches, teams_dict, champ_config):
        super().__init__(timeout=180)
        self.matches = matches
        self.teams_dict = teams_dict
        self.champ_config = champ_config

    @discord.ui.button(label="✅ Confirmar & Publicar Bracket", style=discord.ButtonStyle.success, custom_id="confirm_bracket_btn")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        db.setup_bracket(self.matches)
        draw_bracket_image(self.matches, self.teams_dict, "bracket.png")
        
        embed = discord.Embed(
            title=f"🏆 Chaveamento Oficial - {self.champ_config.get('name', 'Campeonato Rematch')}",
            description=f"O campeonato começou! Confira abaixo a árvore de confrontos oficiais.\nFormato: **{self.champ_config.get('format', '').upper()}** | Premiação: **{self.champ_config.get('prize_type', '').upper()}**",
            color=discord.Color.green()
        )
        file = discord.File("bracket.png", filename="bracket.png")
        embed.set_image(url="attachment://bracket.png")

        await interaction.channel.send(embed=embed, file=file)
        await interaction.response.send_message("✅ **Chaveamento do campeonato confirmado e publicado com sucesso!**", ephemeral=True)
        self.stop()

    @discord.ui.button(label="🔄 Refazer / Embaralhar Bracket", style=discord.ButtonStyle.secondary, custom_id="re-shuffle_bracket_btn")
    async def reshuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        team_ids = list(self.teams_dict.keys())
        new_matches = generate_bracket_matches(team_ids)
        draw_bracket_image(new_matches, self.teams_dict, "bracket_preview.png")

        self.matches = new_matches
        file = discord.File("bracket_preview.png", filename="bracket_preview.png")
        
        embed = discord.Embed(
            title="🏆 Nova Prévia do Chaveamento (Embaralhado)",
            description="Os times foram re-embaralhados. A bracket está feita corretamente?",
            color=discord.Color.gold()
        )
        embed.set_image(url="attachment://bracket_preview.png")

        await interaction.response.edit_message(embed=embed, attachments=[file], view=self)

class FormatSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Single Elimination (Eliminação Simples)", value="single_elimination", emoji="🥇", description="Perdeu está fora"),
            discord.SelectOption(label="Double Elimination (Com Lower Bracket)", value="double_elimination", emoji="🔄", description="Upper e Lower Bracket"),
            discord.SelectOption(label="Formato Suíço (Swiss System)", value="swiss", emoji="🇨🇭", description="Confrontos por pontuação similar"),
            discord.SelectOption(label="Pontos Corridos (Round Robin)", value="points", emoji="📊", description="Todos contra todos")
        ]
        super().__init__(placeholder="Selecione o formato do campeonato...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_format = self.values[0]
        await interaction.response.send_message(f"✅ Formato selecionado: **{self.values[0]}**", ephemeral=True)

class PrizeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Porcentagem (80% Campeão / 20% Vice)", value="percentage", emoji="💰", description="Premiação dividida por colocação"),
            discord.SelectOption(label="Modo Rushadão", value="rushadao", emoji="🔥", description="Vencedor da partida ganha a taxa do perdedor")
        ]
        super().__init__(placeholder="Selecione o formato de premiação...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_prize = self.values[0]
        await interaction.response.send_message(f"✅ Premiação selecionada: **{self.values[0]}**", ephemeral=True)

class ChampionshipSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.selected_format = "double_elimination"
        self.selected_prize = "percentage"
        self.add_item(FormatSelect())
        self.add_item(PrizeSelect())

    @discord.ui.button(label="🚀 Gerar & Iniciar Campeonato", style=discord.ButtonStyle.success)
    async def start_champ(self, interaction: discord.Interaction, button: discord.ui.Button):
        db.set_championship_config(
            name="Campeonato Rematch",
            format_type=self.selected_format,
            prize_type=self.selected_prize,
            prize_percentages={"champion": 80, "runner_up": 20} if self.selected_prize == "percentage" else None
        )

        champ_config = db.get_championship_config()
        reg_ids = champ_config.get("registered_team_ids", [])
        custom_teams = db.get_custom_teams()

        teams_dict = {}
        if reg_ids:
            for tid in reg_ids:
                if tid in custom_teams:
                    teams_dict[tid] = custom_teams[tid]
                else:
                    teams_dict[tid] = {"name": f"Time {tid[:6]}", "team_name": f"Time {tid[:6]}"}
        else:
            # Usar times do draft ou cadastrados
            teams_dict = custom_teams or db.get_teams()

        if len(teams_dict) < 2:
            return await interaction.response.send_message("❌ É necessário ter pelo menos 2 times cadastrados ou inscritos para iniciar o campeonato!", ephemeral=True)

        team_ids = list(teams_dict.keys())
        matches = generate_bracket_matches(team_ids)

        draw_bracket_image(matches, teams_dict, "bracket_preview.png")

        embed = discord.Embed(
            title="🏆 Prévia do Chaveamento do Campeonato",
            description=f"A bracket foi gerada com base nos times inscritos.\nFormato: **{self.selected_format.upper()}** | Premiação: **{self.selected_prize.upper()}**\n\n**A bracket está feita corretamente?**",
            color=discord.Color.gold()
        )
        file = discord.File("bracket_preview.png", filename="bracket_preview.png")
        embed.set_image(url="attachment://bracket_preview.png")

        await interaction.response.send_message(embed=embed, file=file, view=ConfirmBracketView(matches, teams_dict, champ_config))

@bot.command(name="campeonato", aliases=["iniciarcampeonato"])
@commands.has_permissions(administrator=True)
async def cmd_campeonato(ctx):
    """Inicia o painel de criação e chaveamento de campeonatos"""
    embed = discord.Embed(
        title="🏆 Gerenciador de Campeonatos - Rematch",
        description="Selecione abaixo as opções de **formato** e **premiação** para configurar o novo campeonato e gerar o chaveamento visual.",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed, view=ChampionshipSetupView())

# Iniciar o bot
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("Erro: DISCORD_TOKEN não encontrado nas variáveis de ambiente.")
    else:
        bot.run(DISCORD_TOKEN)


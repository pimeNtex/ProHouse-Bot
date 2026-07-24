import json
import os
import threading
import copy
import random
import time
from config import DATABASE_FILE, POSITIONS, CAPTAIN_POSITION, REQUIRED_VOTES

class Database:
    _lock = threading.Lock()

    def __init__(self):
        self.filepath = DATABASE_FILE
        self.default_state = {
            "phase": "inscricao",  # inscricao, draft, protecao, roubo, bracket
            "registrations": {},    # user_id (str) -> {user_id, username, display_name, position}
            "custom_teams": {},     # team_id (str) -> {id, name, role_id, leader_id, leader_name, logo_path, members}
            "championship": {
                "active": False,
                "name": "Campeonato Rematch",
                "format": "single_elimination", # single_elimination, double_elimination, swiss, points
                "prize_type": "percentage", # percentage, rushadao
                "prize_percentages": {"champion": 80, "runner_up": 20},
                "entry_fee": 0.0,
                "registered_team_ids": [],
                "live_message_id": None,
                "live_channel_id": None
            },
            "gossip": {
                "channel_id": None,
                "count": 0
            },
            "tickets": {},
            "draft": {
                "captains": [],      # list of captain user_ids (str)
                "order": [],         # list of captain user_ids representing pick sequence
                "current_index": 0,  # current index in order list
                "teams": {},         # captain_id (str) -> {captain_id, captain_name, players: {pos -> player_data}, protected_player_id}
                "turn_deadline": None
            },
            "steal": {
                "order": [],         # list of captain user_ids (str) in steal order (reverse of draft captains order)
                "current_index": 0,
                "steals": []         # list of dicts detailing steals: {stealer_id, target_captain_id, stolen_player_id, given_player_id}
            },
            "bracket": {
                "teams": [],         # list of team dicts or captain_ids
                "matches": {},       # match_id (str) -> match details
                "current_round": 1
            }
        }
        self.init_db()

    def init_db(self):
        with self._lock:
            if not os.path.exists(self.filepath):
                self._save_state(self.default_state)

    def _load_state(self):
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                updated = False
                for k, v in self.default_state.items():
                    if k not in data:
                        data[k] = copy.deepcopy(v)
                        updated = True
                if updated:
                    self._save_state(data)
                return data
        except Exception:
            return copy.deepcopy(self.default_state)

    def _save_state(self, state):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4, ensure_ascii=False)

    def get_phase(self):
        with self._lock:
            state = self._load_state()
            return state.get("phase", "inscricao")

    def set_phase(self, phase):
        with self._lock:
            state = self._load_state()
            state["phase"] = phase
            self._save_state(state)

    def set_registration_message(self, channel_id, message_id):
        with self._lock:
            state = self._load_state()
            state["registration_channel_id"] = channel_id
            state["registration_message_id"] = message_id
            self._save_state(state)

    def get_registration_message(self):
        with self._lock:
            state = self._load_state()
            return state.get("registration_channel_id"), state.get("registration_message_id")

    def set_draft_message(self, channel_id, message_id):
        with self._lock:
            state = self._load_state()
            if "draft" in state:
                state["draft"]["channel_id"] = channel_id
                state["draft"]["message_id"] = message_id
            self._save_state(state)

    def get_draft_message(self):
        with self._lock:
            state = self._load_state()
            draft = state.get("draft", {})
            return draft.get("channel_id"), draft.get("message_id")

    def reset_db(self):
        with self._lock:
            self._save_state(self.default_state)

    def cancel_picks(self):
        with self._lock:
            state = self._load_state()
            state["phase"] = "inscricao"
            state["draft"] = {
                "captains": [],
                "order": [],
                "current_index": 0,
                "teams": {},
                "turn_deadline": None
            }
            state["steal"] = {
                "order": [],
                "current_index": 0,
                "steals": []
            }
            state["bracket"] = {
                "teams": [],
                "matches": {},
                "current_round": 1
            }
            self._save_state(state)

    # --- INSCRICAO (REGISTRATION) METHODS ---
    def register_player(self, user_id, username, display_name, position):
        with self._lock:
            state = self._load_state()
            if state["phase"] != "inscricao" and state["phase"] != "draft":
                return False, "As inscrições estão fechadas no momento."
            
            if state["phase"] == "draft" and position == "GK":
                return False, "Não é possível se inscrever como Goleiro (GK) após o início do draft."
            
            user_id_str = str(user_id)
            if state["phase"] == "draft":
                # Impedir capitães de se reinscreverem
                if user_id_str in state.get("draft", {}).get("captains", []):
                    return False, "Você já é capitão deste mix."
                # Impedir jogadores já recrutados de se reinscreverem
                teams = state.get("draft", {}).get("teams", {})
                for tid, team in teams.items():
                    for pl in team.get("players", []):
                        if str(pl.get("id")) == user_id_str:
                            return False, "Você já foi escolhido por uma equipe neste draft."
            state["registrations"][user_id_str] = {
                "user_id": user_id,
                "username": username,
                "display_name": display_name,
                "position": position
            }
            self._save_state(state)
            return True, f"Jogador {display_name} inscrito com sucesso como **{position}**."

    def unregister_player(self, user_id):
        with self._lock:
            state = self._load_state()
            if state["phase"] != "inscricao" and state["phase"] != "draft":
                return False, "As inscrições estão fechadas no momento."
            
            user_id_str = str(user_id)
            if state["phase"] == "draft":
                teams = state.get("draft", {}).get("teams", {})
                for tid, team in teams.items():
                    for pl in team.get("players", []):
                        if str(pl.get("id")) == user_id_str:
                            return False, "Você não pode cancelar sua inscrição pois já foi escolhido por um time no Draft."

            if user_id_str in state["registrations"]:
                name = state["registrations"][user_id_str]["display_name"]
                del state["registrations"][user_id_str]
                self._save_state(state)
                return True, f"Inscrição de {name} cancelada."
            return False, "Você não está inscrito."

    def get_registrations(self):
        with self._lock:
            state = self._load_state()
            return copy.deepcopy(state.get("registrations", {}))

    # --- DRAFT METHODS ---
    def setup_draft(self, captains_list, registrations, pick_rounds=4):
        """
        captains_list: list of dicts of captains (GKs)
        registrations: dict of all registered players
        """
        with self._lock:
            state = self._load_state()
            state["phase"] = "draft"
            state["draft"]["pick_rounds"] = pick_rounds
            
            # Setup captains (GKs)
            captain_ids = [str(c["user_id"]) for c in captains_list]
            state["draft"]["captains"] = captain_ids
            
            order = []
            T = len(captain_ids)
            if T > 0:
                forward = True
                for r in range(pick_rounds):
                    if forward:
                        for i in range(T):
                            order.append(captain_ids[i])
                    else:
                        for i in range(T - 1, -1, -1):
                            order.append(captain_ids[i])
                    forward = not forward

            state["draft"]["order"] = order
            state["draft"]["current_index"] = 0
            state["draft"]["teams"] = {}
            
            countries = ["Brasil", "França", "Espanha", "Inglaterra", "Argentina", "Alemanha", "Croácia", "Holanda"]
            random.shuffle(countries)
            
            for idx, c in enumerate(captains_list):
                cid_str = str(c["user_id"])
                country = countries[idx % len(countries)]
                captain_username = c.get("username", c["display_name"])
                clean_username = captain_username.lstrip("@")
                team_name = f"{country} (@{clean_username})"
                
                state["draft"]["teams"][cid_str] = {
                    "captain_id": c["user_id"],
                    "captain_name": c["display_name"],
                    "country": country,
                    "team_name": team_name,
                    "players": [
                        {"id": c["user_id"], "name": c["display_name"], "username": captain_username, "position": "GK"}
                    ],
                    "protected_player_id": None,
                    "protected_player_ids": None
                }
            
            import time
            state["draft"]["turn_deadline"] = time.time() + 90
            self._save_state(state)

    def set_protection_deadline(self, deadline):
        with self._lock:
            state = self._load_state()
            if "draft" not in state:
                state["draft"] = {}
            state["draft"]["protection_deadline"] = deadline
            self._save_state(state)

    def get_protection_deadline(self):
        with self._lock:
            state = self._load_state()
            return state.get("draft", {}).get("protection_deadline")

    def get_draft_state(self):
        with self._lock:
            state = self._load_state()
            return copy.deepcopy(state.get("draft", {}))

    def make_pick(self, captain_id, player_id):
        with self._lock:
            state = self._load_state()
            if state["phase"] != "draft":
                return False, "Não estamos na fase de Draft."

            draft = state["draft"]
            current_index = draft["current_index"]
            order = draft["order"]
            
            if current_index >= len(order):
                return False, "O Draft já foi concluído."

            active_captain = order[current_index]
            if str(captain_id) != active_captain:
                return False, "Não é o seu turno de escolha."

            # Find player in registrations
            player_id_str = str(player_id)
            if player_id_str not in state["registrations"]:
                return False, "Jogador não encontrado nas inscrições."

            player_data = state["registrations"][player_id_str]
            position = player_data["position"]
            
            # Check if player is already picked
            for tid, team in draft["teams"].items():
                for pl in team["players"]:
                    if pl and str(pl["id"]) == player_id_str:
                        return False, "Este jogador já foi escolhido por outro time."
            
            # Check if player is a captain themselves
            if player_id_str in draft["captains"]:
                return False, "Você não pode escolher outro capitão."

            # Check if captain already has completed team
            team = draft["teams"][active_captain]
            pick_rounds = draft.get("pick_rounds", 4)
            max_players = 1 + pick_rounds
            if len(team["players"]) >= max_players:
                return False, f"Seu time já está completo ({max_players} jogadores)."

            # Assign player to team
            team["players"].append({
                "id": player_data["user_id"],
                "name": player_data["display_name"],
                "username": player_data.get("username", player_data["display_name"]),
                "position": position
            })
            
            # Advance draft index
            draft["current_index"] += 1
            import time
            draft["turn_deadline"] = time.time() + 90
            
            # Save state
            self._save_state(state)
            
            # Check if draft is finished
            is_finished = draft["current_index"] >= len(order)
            return True, {
                "player_name": player_data["display_name"],
                "position": position,
                "captain_name": team["captain_name"],
                "is_finished": is_finished
            }

    def skip_turn(self):
        with self._lock:
            state = self._load_state()
            if state["phase"] != "draft":
                return False, "Não estamos na fase de Draft."
            
            draft = state["draft"]
            current_index = draft["current_index"]
            order = draft["order"]
            
            if current_index >= len(order):
                return False, "O Draft já foi concluído."
            
            # Advance current index
            draft["current_index"] += 1
            import time
            draft["turn_deadline"] = time.time() + 90
            
            # Check if draft is finished
            is_finished = draft["current_index"] >= len(order)
            self._save_state(state)
            
            return True, {
                "is_finished": is_finished
            }

    def distribute_leftover_players(self):
        """
        Caso sobre alguém e tenha algum time com vaga aberta (por exemplo, devido a pulo de turno),
        distribui aleatoriamente os jogadores restantes para as vagas em aberto.
        Retorna uma lista de tuplas (player_name, team_captain_name, position, player_id) dos jogadores distribuídos.
        """
        with self._lock:
            state = self._load_state()
            if state["phase"] != "draft":
                return []
                
            draft = state["draft"]
            pick_rounds = draft.get("pick_rounds", 4)
            target_size = 1 + pick_rounds
            
            # 1. Encontrar todos os jogadores já escolhidos (incluindo capitães)
            picked_ids = set()
            for tid, team in draft["teams"].items():
                for pl in team["players"]:
                    picked_ids.add(str(pl["id"]))
                    
            # 2. Identificar os jogadores disponíveis restantes no pool
            regs = state.get("registrations", {})
            available_pool = []
            for pid, p in regs.items():
                pid_str = str(pid)
                if pid_str not in picked_ids and pid_str not in draft["captains"]:
                    available_pool.append(p)
                    
            if not available_pool:
                return [] # Nenhum jogador sobrou
                
            # 3. Encontrar os times que têm vagas abertas
            teams_with_vacancies = []
            for tid, team in draft["teams"].items():
                current_size = len(team["players"])
                if current_size < target_size:
                    vacancies = target_size - current_size
                    for _ in range(vacancies):
                        teams_with_vacancies.append(team)
                        
            if not teams_with_vacancies:
                return [] # Nenhuma vaga aberta
                
            # 4. Embaralhar e distribuir
            random.shuffle(available_pool)
            random.shuffle(teams_with_vacancies)
            
            distributed = []
            # Distribuir até acabar os jogadores livres ou as vagas
            for i in range(min(len(available_pool), len(teams_with_vacancies))):
                player = available_pool[i]
                team = teams_with_vacancies[i]
                
                # Adiciona o jogador ao time
                team["players"].append({
                    "id": player["user_id"],
                    "name": player["display_name"],
                    "username": player.get("username", player["display_name"]),
                    "position": player["position"]
                })
                distributed.append((player["display_name"], team["captain_name"], player["position"], player["user_id"]))
                
            self._save_state(state)
            return distributed

    # --- PROTECTION METHODS ---
    def protect_player(self, captain_id, player_id):
        # Redireciona para o novo método protect_players com 1 jogador
        success, res = self.protect_players(captain_id, [player_id])
        if not success:
            return False, res
        return True, {
            "player_name": res["player_names"][0],
            "all_set": res["all_set"]
        }

    def protect_players(self, captain_id, player_ids):
        with self._lock:
            state = self._load_state()
            if state["phase"] != "protecao":
                return False, "Não estamos na fase de Proteção."

            cid_str = str(captain_id)
            if cid_str not in state["draft"]["teams"]:
                return False, "Você não é capitão."

            team = state["draft"]["teams"][cid_str]
            
            # Valida se os jogadores pertencem ao time do capitão e não são o GK
            validated_names = []
            for pid in player_ids:
                pid_str = str(pid)
                player_name = None
                for pl in team["players"]:
                    if pl["position"] != "GK" and str(pl["id"]) == pid_str:
                        player_name = pl["name"]
                        break
                if not player_name:
                    return False, f"O jogador com ID {pid} não faz parte do seu time ou é você mesmo (GK)."
                validated_names.append(player_name)

            # Grava no banco
            team["protected_player_ids"] = [int(pid) for pid in player_ids]
            # Mantém compatibilidade retroativa para código antigo que lê protected_player_id
            team["protected_player_id"] = int(player_ids[0]) if len(player_ids) > 0 else None
            
            self._save_state(state)
            
            # Verificar se todos os capitães definiram suas proteções
            all_set = True
            for tid, t in state["draft"]["teams"].items():
                if t.get("protected_player_ids") is None and t.get("protected_player_id") is None:
                    all_set = False
                    break
            
            return True, {
                "player_names": validated_names,
                "all_set": all_set
            }

    # --- STEAL METHODS ---
    def setup_steal(self):
        with self._lock:
            state = self._load_state()
            state["phase"] = "roubo"
            # Steal order is reverse of the captains list, excluding captains who chose 2 protections
            captains = state["draft"]["captains"]
            steal_order = []
            for cid in list(reversed(captains)):
                team = state["draft"]["teams"].get(cid, {})
                prot_ids = team.get("protected_player_ids") or []
                if len(prot_ids) != 2:
                    steal_order.append(cid)
            state["steal"]["order"] = steal_order
            state["steal"]["current_index"] = 0
            state["steal"]["steals"] = []
            import time
            state["steal"]["turn_deadline"] = time.time() + 90
            self._save_state(state)

    def get_steal_state(self):
        with self._lock:
            state = self._load_state()
            return copy.deepcopy(state.get("steal", {}))

    def make_steal(self, stealer_id, target_captain_id, target_player_id, give_player_id, pass_turn=False):
        with self._lock:
            state = self._load_state()
            if state["phase"] != "roubo":
                return False, "Não estamos na fase de Roubo."

            steal = state["steal"]
            curr_idx = steal["current_index"]
            order = steal["order"]
            
            if curr_idx >= len(order):
                return False, "A fase de Roubo já foi concluída."

            if str(stealer_id) != order[curr_idx]:
                return False, "Não é o seu turno de roubo."

            stealer_id_str = str(stealer_id)
            stealer_team = state["draft"]["teams"][stealer_id_str]

            if pass_turn:
                # Captain chooses not to steal
                steal["current_index"] += 1
                import time
                steal["turn_deadline"] = time.time() + 90
                self._save_state(state)
                is_finished = steal["current_index"] >= len(order)
                return True, {
                    "passed": True,
                    "stealer_name": stealer_team["captain_name"],
                    "is_finished": is_finished
                }

            target_captain_id_str = str(target_captain_id)
            if target_captain_id_str not in state["draft"]["teams"]:
                return False, "Capitão alvo não encontrado."
            
            if target_captain_id_str == stealer_id_str:
                return False, "Você não pode roubar do seu próprio time."

            target_team = state["draft"]["teams"][target_captain_id_str]
            
            # Check steal count limit (max 2 steals from a team)
            stolen_count = sum(1 for s in steal.get("steals", []) if str(s["target_captain_id"]) == target_captain_id_str)
            if stolen_count >= 2:
                return False, "Este time já foi roubado o limite de 2 vezes."

            target_player_id_str = str(target_player_id)
            give_player_id_str = str(give_player_id)

            # Find target player in target team
            target_pl_idx = -1
            target_player_data = None
            for idx, pl in enumerate(target_team["players"]):
                if str(pl["id"]) == target_player_id_str:
                    target_pl_idx = idx
                    target_player_data = pl
                    break

            if target_pl_idx == -1 or not target_player_data:
                return False, "O jogador alvo não foi encontrado no time selecionado."
            
            if target_player_data["position"] == "GK":
                return False, "Você não pode roubar um Capitão (GK)."

            # Check if player was already involved in a swap (either stolen or given)
            protected_player_ids = set()
            for s in steal.get("steals", []):
                protected_player_ids.add(str(s["stolen_player_id"]))
                protected_player_ids.add(str(s["given_player_id"]))
            if target_player_id_str in protected_player_ids:
                return False, "Este jogador já esteve envolvido em uma troca nesta fase e está protegido!"

            # Check protection
            target_prot_ids = [str(x) for x in target_team.get("protected_player_ids", [])]
            if not target_prot_ids and target_team.get("protected_player_id") is not None:
                target_prot_ids = [str(target_team["protected_player_id"])]
                
            if len(target_prot_ids) == 2:
                return False, "Esta equipe escolheu proteção dupla e não pode ser roubada!"
                
            if target_player_id_str in target_prot_ids:
                return False, "Este jogador foi protegido e não pode ser roubado!"

            # Find give player in stealer team
            give_pl_idx = -1
            give_player_data = None
            for idx, pl in enumerate(stealer_team["players"]):
                if str(pl["id"]) == give_player_id_str:
                    give_pl_idx = idx
                    give_player_data = pl
                    break

            if give_pl_idx == -1 or not give_player_data:
                return False, "O jogador a ser dado em troca não foi encontrado no seu time."

            if give_player_data["position"] == "GK":
                return False, "Você não pode se dar em troca (GK)."

            # Swap players
            stealer_team["players"].pop(give_pl_idx)
            target_team["players"].pop(target_pl_idx)

            stealer_team["players"].append(target_player_data)
            target_team["players"].append(give_player_data)

            # Record steal history
            steal["steals"].append({
                "stealer_id": stealer_id,
                "stealer_name": stealer_team["captain_name"],
                "target_captain_id": target_captain_id,
                "target_captain_name": target_team["captain_name"],
                "stolen_player_id": target_player_id,
                "stolen_player_name": target_player_data["name"],
                "given_player_id": give_player_id,
                "given_player_name": give_player_data["name"],
                "position": target_player_data["position"]
            })

            # Advance turn
            steal["current_index"] += 1
            import time
            steal["turn_deadline"] = time.time() + 90
            self._save_state(state)

            is_finished = steal["current_index"] >= len(order)
            return True, {
                "passed": False,
                "stealer_id": stealer_id,
                "stealer_name": stealer_team["captain_name"],
                "target_captain_id": target_captain_id,
                "target_captain_name": target_team["captain_name"],
                "stolen_player_id": target_player_id,
                "stolen_player_name": target_player_data["name"],
                "given_player_id": give_player_id,
                "given_player_name": give_player_data["name"],
                "position": target_player_data["position"],
                "is_finished": is_finished
            }

    # --- BRACKET STATE ---
    def setup_bracket(self, matches):
        with self._lock:
            state = self._load_state()
            state["phase"] = "bracket"
            state["bracket"]["matches"] = matches
            
            # List all teams
            teams_list = []
            for tid, t in state["draft"]["teams"].items():
                teams_list.append(t)
            state["bracket"]["teams"] = teams_list
            state["bracket"]["current_round"] = 1
            self._save_state(state)

    def get_bracket_state(self):
        with self._lock:
            state = self._load_state()
            return copy.deepcopy(state.get("bracket", {}))

    def get_teams(self):
        with self._lock:
            state = self._load_state()
            return copy.deepcopy(state["draft"]["teams"])

    def get_required_votes(self):
        with self._lock:
            state = self._load_state()
            pick_rounds = state.get("draft", {}).get("pick_rounds", 4)
            return 1 + pick_rounds

    def record_vote(self, match_id, user_id, team_id_voted):
        with self._lock:
            state = self._load_state()
            if state["phase"] != "bracket":
                return False, "Não estamos na fase de Bracket."

            matches = state["bracket"]["matches"]
            if match_id not in matches:
                return False, "Partida não encontrada."

            match = matches[match_id]
            if match["status"] != "ongoing":
                return False, "Esta partida não está ativa para votação."

            team_a_id = str(match["team_a_id"])
            team_b_id = str(match["team_b_id"])
            user_id_str = str(user_id)
            
            # Verify if user is in one of the teams playing
            teams = state["draft"]["teams"]
            player_in_match = False
            for tid in [team_a_id, team_b_id]:
                if tid in teams:
                    for pl in teams[tid]["players"]:
                        if pl and str(pl["id"]) == user_id_str:
                            player_in_match = True
                            break
                if player_in_match:
                    break

            if not player_in_match:
                return False, "Você não faz parte de nenhum dos times desta partida."

            # Save the vote
            if "votes" not in match:
                match["votes"] = {}
            
            # Record or update vote
            match["votes"][user_id_str] = str(team_id_voted)
            self._save_state(state)
            
            # Count votes
            votes_a = sum(1 for uid, vid in match["votes"].items() if vid == team_a_id)
            votes_b = sum(1 for uid, vid in match["votes"].items() if vid == team_b_id)
            
            pick_rounds = state.get("draft", {}).get("pick_rounds", 4)
            required_votes = 1 + pick_rounds
            
            winner_id = None
            if votes_a >= required_votes:
                winner_id = team_a_id
            elif votes_b >= required_votes:
                winner_id = team_b_id
                
            return True, {
                "votes_a": votes_a,
                "votes_b": votes_b,
                "winner_id": winner_id,
                "team_a_id": team_a_id,
                "team_b_id": team_b_id
            }

    def admin_override_winner(self, match_id, winner_team_id):
        with self._lock:
            state = self._load_state()
            if state["phase"] != "bracket":
                return False, "Não estamos na fase de Bracket."

            matches = state["bracket"]["matches"]
            if match_id not in matches:
                return False, "Partida não encontrada."

            match = matches[match_id]
            if match["status"] != "ongoing":
                return False, "Esta partida não está ativa."

            team_a_id = str(match["team_a_id"])
            team_b_id = str(match["team_b_id"])
            winner_team_id_str = str(winner_team_id)

            if winner_team_id_str not in [team_a_id, team_b_id]:
                return False, "O time vencedor especificado não está nesta partida."

            self._save_state(state)
            return True, {
                "winner_id": winner_team_id_str,
                "team_a_id": team_a_id,
                "team_b_id": team_b_id
            }

    def resolve_match(self, match_id, winner_id):
        with self._lock:
            state = self._load_state()
            matches = state["bracket"]["matches"]
            match = matches[match_id]
            
            team_a_id = str(match["team_a_id"])
            team_b_id = str(match["team_b_id"])
            winner_id_str = str(winner_id)
            loser_id_str = team_b_id if winner_id_str == team_a_id else team_a_id

            match["winner_id"] = winner_id_str
            match["status"] = "completed"

            # Propagate winner and loser
            # Winner goes to next_match_win
            next_win = match.get("next_match_win")
            if next_win:
                win_match_id = next_win["match_id"]
                win_pos = next_win["position"]  # "team_a_id" or "team_b_id"
                if win_match_id in matches:
                    matches[win_match_id][win_pos] = winner_id_str
                    # If both teams are now set in the next match, check if it's a bye or make it active
                    next_m = matches[win_match_id]
                    if next_m.get("team_a_id") and next_m.get("team_b_id"):
                        if next_m["team_a_id"] == "BYE":
                            # Automatic win for B
                            self._resolve_match_recursive(matches, win_match_id, next_m["team_b_id"])
                        elif next_m["team_b_id"] == "BYE":
                            # Automatic win for A
                            self._resolve_match_recursive(matches, win_match_id, next_m["team_a_id"])
                        else:
                            next_m["status"] = "ongoing"

            # Loser goes to next_match_lose
            next_lose = match.get("next_match_lose")
            if next_lose:
                lose_match_id = next_lose["match_id"]
                lose_pos = next_lose["position"]
                if lose_match_id in matches:
                    matches[lose_match_id][lose_pos] = loser_id_str
                    next_m = matches[lose_match_id]
                    if next_m.get("team_a_id") and next_m.get("team_b_id"):
                        if next_m["team_a_id"] == "BYE":
                            self._resolve_match_recursive(matches, lose_match_id, next_m["team_b_id"])
                        elif next_m["team_b_id"] == "BYE":
                            self._resolve_match_recursive(matches, lose_match_id, next_m["team_a_id"])
                        else:
                            next_m["status"] = "ongoing"

            self._save_state(state)
            return copy.deepcopy(matches)

    def _resolve_match_recursive(self, matches, match_id, winner_id):
        match = matches[match_id]
        team_a_id = str(match["team_a_id"])
        team_b_id = str(match["team_b_id"])
        winner_id_str = str(winner_id)
        loser_id_str = team_b_id if winner_id_str == team_a_id else team_a_id

        match["winner_id"] = winner_id_str
        match["status"] = "completed"

        next_win = match.get("next_match_win")
        if next_win:
            win_match_id = next_win["match_id"]
            win_pos = next_win["position"]
            if win_match_id in matches:
                matches[win_match_id][win_pos] = winner_id_str
                next_m = matches[win_match_id]
                if next_m.get("team_a_id") and next_m.get("team_b_id"):
                    if next_m["team_a_id"] == "BYE":
                        self._resolve_match_recursive(matches, win_match_id, next_m["team_b_id"])
                    elif next_m["team_b_id"] == "BYE":
                        self._resolve_match_recursive(matches, win_match_id, next_m["team_a_id"])
                    else:
                        next_m["status"] = "ongoing"

        next_lose = match.get("next_match_lose")
        if next_lose:
            lose_match_id = next_lose["match_id"]
            lose_pos = next_lose["position"]
            if lose_match_id in matches:
                matches[lose_match_id][lose_pos] = loser_id_str
                next_m = matches[lose_match_id]
                if next_m.get("team_a_id") and next_m.get("team_b_id"):
                    if next_m["team_a_id"] == "BYE":
                        self._resolve_match_recursive(matches, lose_match_id, next_m["team_b_id"])
                    elif next_m["team_b_id"] == "BYE":
                        self._resolve_match_recursive(matches, lose_match_id, next_m["team_a_id"])
                    else:
                        next_m["status"] = "ongoing"

    # --- CUSTOM TEAMS METHODS ---
    def save_custom_team(self, team_id, name, role_id, leader_id, leader_name, logo_path):
        with self._lock:
            state = self._load_state()
            if "custom_teams" not in state:
                state["custom_teams"] = {}
            team_id_str = str(team_id)
            state["custom_teams"][team_id_str] = {
                "id": team_id_str,
                "name": name,
                "team_name": name,
                "role_id": role_id,
                "leader_id": leader_id,
                "leader_name": leader_name,
                "captain_name": leader_name,
                "logo_path": logo_path,
                "members": [leader_id]
            }
            self._save_state(state)
            return state["custom_teams"][team_id_str]

    def get_custom_teams(self):
        with self._lock:
            state = self._load_state()
            return copy.deepcopy(state.get("custom_teams", {}))

    def get_custom_team_by_id(self, team_id):
        with self._lock:
            state = self._load_state()
            teams = state.get("custom_teams", {})
            return copy.deepcopy(teams.get(str(team_id)))

    def get_custom_team_by_role_or_name(self, query):
        with self._lock:
            state = self._load_state()
            teams = state.get("custom_teams", {})
            query_str = str(query).lower().strip()
            for tid, t in teams.items():
                if str(t.get("role_id")) == query_str:
                    return copy.deepcopy(t)
                if t.get("name", "").lower() == query_str:
                    return copy.deepcopy(t)
            return None

    # --- CHAMPIONSHIP METHODS ---
    def set_championship_config(self, name="Campeonato Rematch", format_type="single_elimination", prize_type="percentage", prize_percentages=None, entry_fee=0.0):
        with self._lock:
            state = self._load_state()
            if "championship" not in state:
                state["championship"] = {}
            if prize_percentages is None:
                prize_percentages = {"champion": 80, "runner_up": 20}
            state["championship"]["name"] = name
            state["championship"]["format"] = format_type
            state["championship"]["prize_type"] = prize_type
            state["championship"]["prize_percentages"] = prize_percentages
            state["championship"]["entry_fee"] = entry_fee
            state["championship"]["active"] = True
            if "registered_team_ids" not in state["championship"]:
                state["championship"]["registered_team_ids"] = []
            self._save_state(state)

    def get_championship_config(self):
        with self._lock:
            state = self._load_state()
            return copy.deepcopy(state.get("championship", {}))

    def register_team_for_championship(self, team_id):
        with self._lock:
            state = self._load_state()
            champ = state.get("championship", {})
            reg_ids = champ.get("registered_team_ids", [])
            team_id_str = str(team_id)
            if team_id_str in reg_ids:
                return False, "O time já está inscrito no campeonato!"
            reg_ids.append(team_id_str)
            champ["registered_team_ids"] = reg_ids
            state["championship"] = champ
            self._save_state(state)
            return True, "Time inscrito com sucesso no campeonato!"

    def unregister_team_from_championship(self, team_id):
        with self._lock:
            state = self._load_state()
            champ = state.get("championship", {})
            reg_ids = champ.get("registered_team_ids", [])
            team_id_str = str(team_id)
            if team_id_str not in reg_ids:
                return False, "O time não está inscrito no campeonato."
            reg_ids.remove(team_id_str)
            champ["registered_team_ids"] = reg_ids
            state["championship"] = champ
            self._save_state(state)
            return True, "Inscrição do time cancelada."

    def set_live_message(self, channel_id, message_id):
        with self._lock:
            state = self._load_state()
            if "championship" not in state:
                state["championship"] = {}
            state["championship"]["live_channel_id"] = channel_id
            state["championship"]["live_message_id"] = message_id
            self._save_state(state)

    def get_live_message(self):
        with self._lock:
            state = self._load_state()
            champ = state.get("championship", {})
            return champ.get("live_channel_id"), champ.get("live_message_id")

    # --- GOSSIP METHODS ---
    def set_gossip_channel(self, channel_id):
        with self._lock:
            state = self._load_state()
            if "gossip" not in state:
                state["gossip"] = {}
            state["gossip"]["channel_id"] = channel_id
            self._save_state(state)

    def get_gossip_channel(self):
        with self._lock:
            state = self._load_state()
            gossip = state.get("gossip", {})
            return gossip.get("channel_id")

    def increment_gossip_count(self):
        with self._lock:
            state = self._load_state()
            if "gossip" not in state:
                state["gossip"] = {"count": 0}
            count = state["gossip"].get("count", 0) + 1
            state["gossip"]["count"] = count
            self._save_state(state)
            return count

    def set_gossip_approval_channel(self, channel_id):
        with self._lock:
            state = self._load_state()
            if "gossip" not in state:
                state["gossip"] = {}
            state["gossip"]["approval_channel_id"] = channel_id
            self._save_state(state)

    def get_gossip_approval_channel(self):
        with self._lock:
            state = self._load_state()
            gossip = state.get("gossip", {})
            return gossip.get("approval_channel_id")

    def add_pending_gossip(self, msg_id, author_id, gossip_text):
        with self._lock:
            state = self._load_state()
            if "gossip" not in state:
                state["gossip"] = {}
            if "pending" not in state["gossip"]:
                state["gossip"]["pending"] = {}
            state["gossip"]["pending"][str(msg_id)] = {
                "author_id": author_id,
                "text": gossip_text,
                "created_at": time.time()
            }
            self._save_state(state)

    def get_pending_gossip(self, msg_id):
        with self._lock:
            state = self._load_state()
            pending = state.get("gossip", {}).get("pending", {})
            return pending.get(str(msg_id))

    def remove_pending_gossip(self, msg_id):
        with self._lock:
            state = self._load_state()
            pending = state.get("gossip", {}).get("pending", {})
            msg_id_str = str(msg_id)
            if msg_id_str in pending:
                del pending[msg_id_str]
                self._save_state(state)

    def check_gossip_cooldown(self, user_id, cooldown_hours=6):
        with self._lock:
            state = self._load_state()
            gossip = state.get("gossip", {})
            user_cooldowns = gossip.get("user_cooldowns", {})
            last_time = user_cooldowns.get(str(user_id))
            if not last_time:
                return True, 0
            
            elapsed = time.time() - last_time
            required_seconds = cooldown_hours * 3600
            if elapsed >= required_seconds:
                return True, 0
            else:
                remaining = required_seconds - elapsed
                return False, remaining


    def record_gossip_sent(self, user_id):
        with self._lock:
            state = self._load_state()
            if "gossip" not in state:
                state["gossip"] = {}
            if "user_cooldowns" not in state["gossip"]:
                state["gossip"]["user_cooldowns"] = {}
            state["gossip"]["user_cooldowns"][str(user_id)] = time.time()
            self._save_state(state)


    # --- TICKET METHODS ---
    def add_ticket(self, channel_id, user_id, category):
        with self._lock:
            state = self._load_state()
            if "tickets" not in state:
                state["tickets"] = {}
            state["tickets"][str(channel_id)] = {
                "channel_id": channel_id,
                "user_id": user_id,
                "category": category,
                "status": "open"
            }
            self._save_state(state)

    def close_ticket_db(self, channel_id):
        with self._lock:
            state = self._load_state()
            tickets = state.get("tickets", {})
            cid_str = str(channel_id)
            if cid_str in tickets:
                tickets[cid_str]["status"] = "closed"
                self._save_state(state)


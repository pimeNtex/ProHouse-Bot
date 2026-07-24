import random
import os
from PIL import Image, ImageDraw, ImageFont
from config import POSITIONS

def get_next_power_of_2(n):
    if n <= 2:
        return 2
    elif n <= 4:
        return 4
    elif n <= 8:
        return 8
    else:
        return 16

def generate_bracket_matches(team_ids):
    """
    Generates double elimination bracket matches for a list of team IDs.
    Returns a dict of matches: match_id -> match_details.
    """
    random.shuffle(team_ids)
    num_teams = len(team_ids)
    N = get_next_power_of_2(num_teams)
    num_byes = N - num_teams
    
    # Distribute BYEs so they are matched against real teams and never against other BYEs
    padded_teams = []
    real_idx = 0
    for i in range(N // 2):
        if i < num_byes:
            padded_teams.append(team_ids[real_idx])
            real_idx += 1
            padded_teams.append("BYE")
        else:
            padded_teams.append(team_ids[real_idx])
            real_idx += 1
            padded_teams.append(team_ids[real_idx])
            real_idx += 1

    matches = {}
    
    if N == 2:
        # N=2 (2 teams)
        # U1_1: Team A vs Team B
        # GF_1: Winner U1_1 vs Loser U1_1
        # GF_2: (Optional if Loser wins GF_1)
        matches["U1_1"] = {
            "id": "U1_1", "round": 1, "type": "upper", "label": "Final da Upper",
            "team_a_id": padded_teams[0], "team_b_id": padded_teams[1], "winner_id": None, "status": "ongoing",
            "next_match_win": {"match_id": "GF_1", "position": "team_a_id"},
            "next_match_lose": {"match_id": "GF_1", "position": "team_b_id"}
        }
        matches["GF_1"] = {
            "id": "GF_1", "round": 2, "type": "grand_final", "label": "Grande Final",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": None, "next_match_lose": None
        }
        
    elif N == 4:
        # Upper Round 1
        matches["U1_1"] = {
            "id": "U1_1", "round": 1, "type": "upper", "label": "Semifinal Upper 1",
            "team_a_id": padded_teams[0], "team_b_id": padded_teams[1], "winner_id": None, "status": "ongoing",
            "next_match_win": {"match_id": "U2_1", "position": "team_a_id"},
            "next_match_lose": {"match_id": "L1_1", "position": "team_a_id"}
        }
        matches["U1_2"] = {
            "id": "U1_2", "round": 1, "type": "upper", "label": "Semifinal Upper 2",
            "team_a_id": padded_teams[2], "team_b_id": padded_teams[3], "winner_id": None, "status": "ongoing",
            "next_match_win": {"match_id": "U2_1", "position": "team_b_id"},
            "next_match_lose": {"match_id": "L1_1", "position": "team_b_id"}
        }
        # Upper Round 2 (Upper Final)
        matches["U2_1"] = {
            "id": "U2_1", "round": 2, "type": "upper", "label": "Final Upper",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "GF_1", "position": "team_a_id"},
            "next_match_lose": {"match_id": "L2_1", "position": "team_b_id"}
        }
        # Lower Round 1
        matches["L1_1"] = {
            "id": "L1_1", "round": 1, "type": "lower", "label": "Semifinal Lower",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "L2_1", "position": "team_a_id"},
            "next_match_lose": None
        }
        # Lower Round 2 (Lower Final)
        matches["L2_1"] = {
            "id": "L2_1", "round": 2, "type": "lower", "label": "Final Lower",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "GF_1", "position": "team_b_id"},
            "next_match_lose": None
        }
        # Grand Final
        matches["GF_1"] = {
            "id": "GF_1", "round": 3, "type": "grand_final", "label": "Grande Final",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": None, "next_match_lose": None
        }
        
    elif N == 8:
        # Upper Round 1
        matches["U1_1"] = {
            "id": "U1_1", "round": 1, "type": "upper", "label": "Quartas Upper 1",
            "team_a_id": padded_teams[0], "team_b_id": padded_teams[1], "winner_id": None, "status": "ongoing",
            "next_match_win": {"match_id": "U2_1", "position": "team_a_id"},
            "next_match_lose": {"match_id": "L1_1", "position": "team_a_id"}
        }
        matches["U1_2"] = {
            "id": "U1_2", "round": 1, "type": "upper", "label": "Quartas Upper 2",
            "team_a_id": padded_teams[2], "team_b_id": padded_teams[3], "winner_id": None, "status": "ongoing",
            "next_match_win": {"match_id": "U2_1", "position": "team_b_id"},
            "next_match_lose": {"match_id": "L1_1", "position": "team_b_id"}
        }
        matches["U1_3"] = {
            "id": "U1_3", "round": 1, "type": "upper", "label": "Quartas Upper 3",
            "team_a_id": padded_teams[4], "team_b_id": padded_teams[5], "winner_id": None, "status": "ongoing",
            "next_match_win": {"match_id": "U2_2", "position": "team_a_id"},
            "next_match_lose": {"match_id": "L1_2", "position": "team_a_id"}
        }
        matches["U1_4"] = {
            "id": "U1_4", "round": 1, "type": "upper", "label": "Quartas Upper 4",
            "team_a_id": padded_teams[6], "team_b_id": padded_teams[7], "winner_id": None, "status": "ongoing",
            "next_match_win": {"match_id": "U2_2", "position": "team_b_id"},
            "next_match_lose": {"match_id": "L1_2", "position": "team_b_id"}
        }
        # Upper Round 2
        matches["U2_1"] = {
            "id": "U2_1", "round": 2, "type": "upper", "label": "Semifinal Upper 1",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "U3_1", "position": "team_a_id"},
            "next_match_lose": {"match_id": "L2_2", "position": "team_b_id"}
        }
        matches["U2_2"] = {
            "id": "U2_2", "round": 2, "type": "upper", "label": "Semifinal Upper 2",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "U3_1", "position": "team_b_id"},
            "next_match_lose": {"match_id": "L2_1", "position": "team_b_id"}
        }
        # Upper Round 3 (Upper Final)
        matches["U3_1"] = {
            "id": "U3_1", "round": 3, "type": "upper", "label": "Final Upper",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "GF_1", "position": "team_a_id"},
            "next_match_lose": {"match_id": "L4_1", "position": "team_b_id"}
        }
        # Lower Round 1
        matches["L1_1"] = {
            "id": "L1_1", "round": 1, "type": "lower", "label": "Rodada 1 Lower 1",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "L2_1", "position": "team_a_id"},
            "next_match_lose": None
        }
        matches["L1_2"] = {
            "id": "L1_2", "round": 1, "type": "lower", "label": "Rodada 1 Lower 2",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "L2_2", "position": "team_a_id"},
            "next_match_lose": None
        }
        # Lower Round 2
        matches["L2_1"] = {
            "id": "L2_1", "round": 2, "type": "lower", "label": "Rodada 2 Lower 1",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "L3_1", "position": "team_a_id"},
            "next_match_lose": None
        }
        matches["L2_2"] = {
            "id": "L2_2", "round": 2, "type": "lower", "label": "Rodada 2 Lower 2",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "L3_1", "position": "team_b_id"},
            "next_match_lose": None
        }
        # Lower Round 3
        matches["L3_1"] = {
            "id": "L3_1", "round": 3, "type": "lower", "label": "Semifinal Lower",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "L4_1", "position": "team_a_id"},
            "next_match_lose": None
        }
        # Lower Round 4 (Lower Final)
        matches["L4_1"] = {
            "id": "L4_1", "round": 4, "type": "lower", "label": "Final Lower",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "GF_1", "position": "team_b_id"},
            "next_match_lose": None
        }
        # Grand Final
        matches["GF_1"] = {
            "id": "GF_1", "round": 5, "type": "grand_final", "label": "Grande Final",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": None, "next_match_lose": None
        }

    else:
        # N=16 (Default to 16)
        # Upper Round 1
        for i in range(1, 9):
            idx_a = (i - 1) * 2
            idx_b = idx_a + 1
            win_match = f"U2_{(i+1)//2}"
            win_pos = "team_a_id" if i % 2 != 0 else "team_b_id"
            lose_match = f"L1_{(i+1)//2}"
            lose_pos = "team_a_id" if i % 2 != 0 else "team_b_id"
            
            matches[f"U1_{i}"] = {
                "id": f"U1_{i}", "round": 1, "type": "upper", "label": f"Oitavas Upper {i}",
                "team_a_id": padded_teams[idx_a], "team_b_id": padded_teams[idx_b], "winner_id": None, "status": "ongoing",
                "next_match_win": {"match_id": win_match, "position": win_pos},
                "next_match_lose": {"match_id": lose_match, "position": lose_pos}
            }
        
        # Upper Round 2
        for i in range(1, 5):
            win_match = f"U3_{(i+1)//2}"
            win_pos = "team_a_id" if i % 2 != 0 else "team_b_id"
            lose_match = f"L2_{i}"  # Losers from U2 drop to L2 (matches L2_1 to L2_4)
            # Standard drop for U2 losers:
            # Loser U2_1 -> L2_4 team b
            # Loser U2_2 -> L2_3 team b
            # Loser U2_3 -> L2_2 team b
            # Loser U2_4 -> L2_1 team b
            lose_match_id = f"L2_{5-i}"
            
            matches[f"U2_{i}"] = {
                "id": f"U2_{i}", "round": 2, "type": "upper", "label": f"Quartas Upper {i}",
                "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
                "next_match_win": {"match_id": win_match, "position": win_pos},
                "next_match_lose": {"match_id": lose_match_id, "position": "team_b_id"}
            }

        # Upper Round 3
        matches["U3_1"] = {
            "id": "U3_1", "round": 3, "type": "upper", "label": "Semifinal Upper 1",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "U4_1", "position": "team_a_id"},
            "next_match_lose": {"match_id": "L4_2", "position": "team_b_id"}
        }
        matches["U3_2"] = {
            "id": "U3_2", "round": 3, "type": "upper", "label": "Semifinal Upper 2",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "U4_1", "position": "team_b_id"},
            "next_match_lose": {"match_id": "L4_1", "position": "team_b_id"}
        }

        # Upper Round 4 (Upper Final)
        matches["U4_1"] = {
            "id": "U4_1", "round": 4, "type": "upper", "label": "Final Upper",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "GF_1", "position": "team_a_id"},
            "next_match_lose": {"match_id": "L6_1", "position": "team_b_id"}
        }

        # Lower Round 1 (L1) - 4 matches
        for i in range(1, 5):
            matches[f"L1_{i}"] = {
                "id": f"L1_{i}", "round": 1, "type": "lower", "label": f"Rodada 1 Lower {i}",
                "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
                "next_match_win": {"match_id": f"L2_{i}", "position": "team_a_id"},
                "next_match_lose": None
            }

        # Lower Round 2 (L2) - 4 matches (Winners of L1 vs Losers of U2)
        for i in range(1, 5):
            win_match = f"L3_{(i+1)//2}"
            win_pos = "team_a_id" if i % 2 != 0 else "team_b_id"
            matches[f"L2_{i}"] = {
                "id": f"L2_{i}", "round": 2, "type": "lower", "label": f"Rodada 2 Lower {i}",
                "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
                "next_match_win": {"match_id": win_match, "position": win_pos},
                "next_match_lose": None
            }

        # Lower Round 3 (L3) - 2 matches (Winners of L2)
        matches["L3_1"] = {
            "id": "L3_1", "round": 3, "type": "lower", "label": "Rodada 3 Lower 1",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "L4_1", "position": "team_a_id"},
            "next_match_lose": None
        }
        matches["L3_2"] = {
            "id": "L3_2", "round": 3, "type": "lower", "label": "Rodada 3 Lower 2",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "L4_2", "position": "team_a_id"},
            "next_match_lose": None
        }

        # Lower Round 4 (L4) - 2 matches (Winners of L3 vs Losers of U3)
        matches["L4_1"] = {
            "id": "L4_1", "round": 4, "type": "lower", "label": "Rodada 4 Lower 1",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "L5_1", "position": "team_a_id"},
            "next_match_lose": None
        }
        matches["L4_2"] = {
            "id": "L4_2", "round": 4, "type": "lower", "label": "Rodada 4 Lower 2",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "L5_1", "position": "team_b_id"},
            "next_match_lose": None
        }

        # Lower Round 5 (L5) - 1 match (Winners of L4)
        matches["L5_1"] = {
            "id": "L5_1", "round": 5, "type": "lower", "label": "Semifinal Lower",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "L6_1", "position": "team_a_id"},
            "next_match_lose": None
        }

        # Lower Round 6 (L6) - 1 match (Winner of L5 vs Loser of U4)
        matches["L6_1"] = {
            "id": "L6_1", "round": 6, "type": "lower", "label": "Final Lower",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": {"match_id": "GF_1", "position": "team_b_id"},
            "next_match_lose": None
        }

        # Grand Final
        matches["GF_1"] = {
            "id": "GF_1", "round": 7, "type": "grand_final", "label": "Grande Final",
            "team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending",
            "next_match_win": None, "next_match_lose": None
        }

    # Automatically resolve BYE matches
    resolve_byes(matches)

    return matches

def resolve_byes(matches):
    """
    Recursively resolves matches that contain a BYE team.
    """
    to_resolve = []
    # Find all matches that have both teams set and at least one is a BYE
    for mid, match in matches.items():
        if match["status"] != "completed":
            team_a = match.get("team_a_id")
            team_b = match.get("team_b_id")
            if team_a and team_b and (team_a == "BYE" or team_b == "BYE"):
                to_resolve.append(mid)

    for mid in to_resolve:
        match = matches[mid]
        team_a = match.get("team_a_id")
        team_b = match.get("team_b_id")
        
        if team_a == "BYE" and team_b == "BYE":
            winner = "BYE"
        elif team_a == "BYE":
            winner = team_b
        else:
            winner = team_a
            
        resolve_match_locally(matches, mid, winner)

def resolve_match_locally(matches, match_id, winner_id):
    match = matches[match_id]
    team_a_id = match.get("team_a_id")
    team_b_id = match.get("team_b_id")
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
                if next_m["team_a_id"] == "BYE" or next_m["team_b_id"] == "BYE":
                    # Recurse
                    resolve_byes(matches)
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
                if next_m["team_a_id"] == "BYE" or next_m["team_b_id"] == "BYE":
                    resolve_byes(matches)
                else:
                    next_m["status"] = "ongoing"

def format_bracket_text(matches, teams):
    """
    Returns a clean string representation of the bracket state.
    """
    def get_team_name(tid):
        if not tid:
            return "A definir"
        if tid == "BYE":
            return "BYE"
        t = teams.get(str(tid))
        return t.get("team_name", t.get("captain_name", f"Time {tid[:6]}")) if t else f"Time {tid[:6]}"

    # Group matches by type and round
    upper = {}
    lower = {}
    gf = []

    for mid, m in matches.items():
        m_type = m["type"]
        m_round = m["round"]
        if m_type == "upper":
            upper.setdefault(m_round, []).append(m)
        elif m_type == "lower":
            lower.setdefault(m_round, []).append(m)
        elif m_type == "grand_final":
            gf.append(m)

    lines = []
    lines.append("🏆 **CHAVE DOS VENCEDORES (UPPER BRACKET)**")
    for r in sorted(upper.keys()):
        lines.append(f"**Rodada {r}**")
        for m in upper[r]:
            team_a = get_team_name(m["team_a_id"])
            team_b = get_team_name(m["team_b_id"])
            status_symbol = "🟢 Ativa" if m["status"] == "ongoing" else ("🔒 Pendente" if m["status"] == "pending" else "✅ Encerrada")
            votes_info = ""
            if m["status"] == "ongoing" and "votes" in m:
                v_a = sum(1 for uid, vid in m["votes"].items() if vid == m["team_a_id"])
                v_b = sum(1 for uid, vid in m["votes"].items() if vid == m["team_b_id"])
                votes_info = f" (Votos: {v_a} x {v_b})"
                
            winner_info = f" -> **Vencedor: {get_team_name(m['winner_id'])}**" if m["winner_id"] else ""
            lines.append(f"• `{m['id']}` ({m['label']}): {team_a} vs {team_b} [{status_symbol}]{votes_info}{winner_info}")
        lines.append("")

    if lower:
        lines.append("📉 **CHAVE DOS PERDEDORES (LOWER BRACKET)**")
        for r in sorted(lower.keys()):
            lines.append(f"**Rodada {r}**")
            for m in lower[r]:
                team_a = get_team_name(m["team_a_id"])
                team_b = get_team_name(m["team_b_id"])
                status_symbol = "🟢 Ativa" if m["status"] == "ongoing" else ("🔒 Pendente" if m["status"] == "pending" else "✅ Encerrada")
                votes_info = ""
                if m["status"] == "ongoing" and "votes" in m:
                    v_a = sum(1 for uid, vid in m["votes"].items() if vid == m["team_a_id"])
                    v_b = sum(1 for uid, vid in m["votes"].items() if vid == m["team_b_id"])
                    votes_info = f" (Votos: {v_a} x {v_b})"
                winner_info = f" -> **Vencedor: {get_team_name(m['winner_id'])}**" if m["winner_id"] else ""
                lines.append(f"• `{m['id']}` ({m['label']}): {team_a} vs {team_b} [{status_symbol}]{votes_info}{winner_info}")
            lines.append("")

    if gf:
        lines.append("👑 **GRANDE FINAL**")
        for m in gf:
            team_a = get_team_name(m["team_a_id"])
            team_b = get_team_name(m["team_b_id"])
            status_symbol = "🟢 Ativa" if m["status"] == "ongoing" else ("🔒 Pendente" if m["status"] == "pending" else "✅ Encerrada")
            votes_info = ""
            if m["status"] == "ongoing" and "votes" in m:
                v_a = sum(1 for uid, vid in m["votes"].items() if vid == m["team_a_id"])
                v_b = sum(1 for uid, vid in m["votes"].items() if vid == m["team_b_id"])
                votes_info = f" (Votos: {v_a} x {v_b})"
            winner_info = f" -> **Vencedor: {get_team_name(m['winner_id'])}**" if m["winner_id"] else ""
            lines.append(f"• `{m['id']}` ({m['label']}): {team_a} vs {team_b} [{status_symbol}]{votes_info}{winner_info}")
            
    return "\n".join(lines)

def get_label(team_id, default_text, teams):
    if not team_id:
        return default_text
    if team_id == "BYE":
        return "BYE"
    t = teams.get(str(team_id))
    name = t.get("team_name", t.get("captain_name", f"Time {team_id[:6]}")) if t else f"Time {team_id[:6]}"
    if len(name) > 12:
        return name[:11] + "…"
    return name.ljust(12)

def get_winner_label(matches, match_id, default_text, teams):
    m = matches.get(match_id)
    if not m or m["status"] == "pending":
        return default_text
    if m["winner_id"]:
        return get_label(m["winner_id"], default_text, teams)
    return default_text

def get_loser_label(matches, match_id, default_text, teams):
    m = matches.get(match_id)
    if not m or m["status"] != "completed":
        return default_text
    winner_id = m["winner_id"]
    team_a = m["team_a_id"]
    team_b = m["team_b_id"]
    loser_id = team_b if str(winner_id) == str(team_a) else team_a
    return get_label(loser_id, default_text, teams)

def get_diagram_n2(matches, teams):
    u1_1_a = get_label(matches["U1_1"]["team_a_id"], "A definir", teams)
    u1_1_b = get_label(matches["U1_1"]["team_b_id"], "A definir", teams)
    u1_1_winner = get_winner_label(matches, "U1_1", "Venc. U1_1", teams)
    u1_1_loser = get_loser_label(matches, "U1_1", "Perd. U1_1", teams)
    gf_1_winner = get_winner_label(matches, "GF_1", "A definir", teams)
    
    diagram = f"""
  UPPER FINAL (U1_1)         GRAND FINAL (GF_1)
  [ {u1_1_a} ]---\\ 
  [ {u1_1_b} ]---+--->[ {u1_1_winner} ]---\\
                     [ {u1_1_loser} ]---+--->[ {gf_1_winner} ] (Campeão)
"""
    return diagram

def get_diagram_n4(matches, teams):
    u1_1_a = get_label(matches["U1_1"]["team_a_id"], "A definir", teams)
    u1_1_b = get_label(matches["U1_1"]["team_b_id"], "A definir", teams)
    u1_2_a = get_label(matches["U1_2"]["team_a_id"], "A definir", teams)
    u1_2_b = get_label(matches["U1_2"]["team_b_id"], "A definir", teams)
    
    u1_1_w = get_winner_label(matches, "U1_1", "Venc. U1_1", teams)
    u1_2_w = get_winner_label(matches, "U1_2", "Venc. U1_2", teams)
    
    u2_1_w = get_winner_label(matches, "U2_1", "Venc. U2_1", teams)
    u2_1_l = get_loser_label(matches, "U2_1", "Perd. U2_1", teams)
    
    u1_1_l = get_loser_label(matches, "U1_1", "Perd. U1_1", teams)
    u1_2_l = get_loser_label(matches, "U1_2", "Perd. U1_2", teams)
    
    l1_1_w = get_winner_label(matches, "L1_1", "Venc. L1_1", teams)
    l2_1_w = get_winner_label(matches, "L2_1", "Venc. L2_1", teams)
    
    gf_1_w = get_winner_label(matches, "GF_1", "A definir", teams)
    
    diagram = f"""
  UPPER BRACKET
  [ {u1_1_a} ]---\\ (U1_1)
  [ {u1_1_b} ]---+--->[ {u1_1_w} ]---\\ (U2_1 Upper Final)
                     [ {u1_2_w} ]---+--->[ {u2_1_w} ]-------\\
  [ {u1_2_a} ]---\\ (U1_2)                                            | (GF_1 Grand Final)
  [ {u1_2_b} ]---+--->[ {u1_2_w} ]---/                                |
                                                                    +--->[ {gf_1_w} ] (Campeão)
  LOWER BRACKET                                                     |
  [ {u1_1_l} ]---\\ (L1_1)                                            |
  [ {u1_2_l} ]---+--->[ {l1_1_w} ]---\\ (L2_1 Lower Final)            |
                     [ {u2_1_l} ]---+--->[ {l2_1_w} ]-------/
"""
    return diagram

def get_diagram_n8(matches, teams):
    u1_1_a = get_label(matches["U1_1"]["team_a_id"], "A definir", teams)
    u1_1_b = get_label(matches["U1_1"]["team_b_id"], "A definir", teams)
    u1_2_a = get_label(matches["U1_2"]["team_a_id"], "A definir", teams)
    u1_2_b = get_label(matches["U1_2"]["team_b_id"], "A definir", teams)
    u1_3_a = get_label(matches["U1_3"]["team_a_id"], "A definir", teams)
    u1_3_b = get_label(matches["U1_3"]["team_b_id"], "A definir", teams)
    u1_4_a = get_label(matches["U1_4"]["team_a_id"], "A definir", teams)
    u1_4_b = get_label(matches["U1_4"]["team_b_id"], "A definir", teams)
    
    u1_1_w = get_winner_label(matches, "U1_1", "Venc. U1_1", teams)
    u1_2_w = get_winner_label(matches, "U1_2", "Venc. U1_2", teams)
    u1_3_w = get_winner_label(matches, "U1_3", "Venc. U1_3", teams)
    u1_4_w = get_winner_label(matches, "U1_4", "Venc. U1_4", teams)
    
    u2_1_w = get_winner_label(matches, "U2_1", "Venc. U2_1", teams)
    u2_2_w = get_winner_label(matches, "U2_2", "Venc. U2_2", teams)
    
    u3_1_w = get_winner_label(matches, "U3_1", "Venc. U3_1", teams)
    u3_1_l = get_loser_label(matches, "U3_1", "Perd. U3_1", teams)
    
    u1_1_l = get_loser_label(matches, "U1_1", "Perd. U1_1", teams)
    u1_2_l = get_loser_label(matches, "U1_2", "Perd. U1_2", teams)
    u1_3_l = get_loser_label(matches, "U1_3", "Perd. U1_3", teams)
    u1_4_l = get_loser_label(matches, "U1_4", "Perd. U1_4", teams)
    
    u2_1_l = get_loser_label(matches, "U2_1", "Perd. U2_1", teams)
    u2_2_l = get_loser_label(matches, "U2_2", "Perd. U2_2", teams)
    
    l1_1_w = get_winner_label(matches, "L1_1", "Venc. L1_1", teams)
    l1_2_w = get_winner_label(matches, "L1_2", "Venc. L1_2", teams)
    
    l2_1_w = get_winner_label(matches, "L2_1", "Venc. L2_1", teams)
    l2_2_w = get_winner_label(matches, "L2_2", "Venc. L2_2", teams)
    
    l3_1_w = get_winner_label(matches, "L3_1", "Venc. L3_1", teams)
    l4_1_w = get_winner_label(matches, "L4_1", "Venc. L4_1", teams)
    
    gf_1_w = get_winner_label(matches, "GF_1", "A definir", teams)
    
    diagram = f"""
  UPPER BRACKET
  [ {u1_1_a} ]---\\ (U1_1)
  [ {u1_1_b} ]---+--->[ {u1_1_w} ]---\\ (U2_1)
                     [ {u1_2_w} ]---+--->[ {u2_1_w} ]---\\ (U3_1 Final Upper)
  [ {u1_2_a} ]---\\ (U1_2)                                        [ {u2_2_w} ]---+--->[ {u3_1_w} ]-------\\
  [ {u1_2_b} ]---+--->[ {u1_2_w} ]---/                                                            |
                                                                                                  | (GF_1)
  [ {u1_3_a} ]---\\ (U1_3)                                                                            +--->[ {gf_1_w} ] (Campeão)
  [ {u1_3_b} ]---+--->[ {u1_3_w} ]---\\ (U2_2)                                                        |
                     [ {u1_4_w} ]---+--->[ {u2_2_w} ]---/                                            |
  [ {u1_4_a} ]---\\ (U1_4)                                                                            |
  [ {u1_4_b} ]---+--->[ {u1_4_w} ]---/                                            [ {l4_1_w} ]------/
  
  LOWER BRACKET
  [ {u1_1_l} ]---\\ (L1_1)
  [ {u1_2_l} ]---+--->[ {l1_1_w} ]---\\ (L2_1)
                     [ {u2_2_l} ]---+--->[ {l2_1_w} ]---\\ (L3_1 Semifinal Lower)
                                                       [ {l2_2_w} ]---+--->[ {l3_1_w} ]---\\ (L4_1 Final Lower)
  [ {u1_3_l} ]---\\ (L1_2)                                                                [ {u3_1_l} ]---+--->[ {l4_1_w} ]---/
  [ {u1_4_l} ]---+--->[ {l1_2_w} ]---\\ (L2_2)                                            
                     [ {u2_1_l} ]---+--->[ {l2_2_w} ]---/
"""
    return diagram

def get_diagram_n16(matches, teams):
    u2_1 = get_winner_label(matches, "U2_1", "Venc. U2_1", teams)
    u2_2 = get_winner_label(matches, "U2_2", "Venc. U2_2", teams)
    u2_3 = get_winner_label(matches, "U2_3", "Venc. U2_3", teams)
    u2_4 = get_winner_label(matches, "U2_4", "Venc. U2_4", teams)
    
    u3_1 = get_winner_label(matches, "U3_1", "Venc. U3_1", teams)
    u3_2 = get_winner_label(matches, "U3_2", "Venc. U3_2", teams)
    
    u4_1 = get_winner_label(matches, "U4_1", "Venc. U4_1", teams)
    
    gf_1_w = get_winner_label(matches, "GF_1", "A definir", teams)
    l6_1_w = get_winner_label(matches, "L6_1", "Venc. L6_1", teams)
    
    diagram = f"""
  UPPER BRACKET (RESUMIDO)
  U1_1 & U1_2 ----> [ {u2_1} ]---\\ (U2)
  U1_3 & U1_4 ----> [ {u2_2} ]---+---> [ {u3_1} ]---\\ (U3)
                                                    +---> [ {u4_1} ] (Upper Final) ---\\
  U1_5 & U1_6 ----> [ {u2_3} ]---\\ (U2)             |                                  |
  U1_7 & U1_8 ----> [ {u2_4} ]---+---> [ {u3_2} ]---/                                  |
                                                                                       +---> [ {gf_1_w} ] (Campeão)
  LOWER BRACKET (RESUMIDO)                                                             |
  L2_1 & L2_2 ----> [ L3_1 ]---\\ (L3)                                                  |
  L2_3 & L2_4 ----> [ L3_2 ]---+---> [ L4_1/L4_2 ] ----> [ L5_1 ] ----> [ {l6_1_w} ] -/ (Lower Final)
"""
    return diagram

def get_bracket_diagram(matches, teams):
    if "U1_5" in matches:
        return get_diagram_n16(matches, teams)
    elif "U1_3" in matches:
        return get_diagram_n8(matches, teams)
    elif "U1_2" in matches:
        return get_diagram_n4(matches, teams)
    elif "U1_1" in matches:
        return get_diagram_n2(matches, teams)
    return ""

def draw_bracket_image(matches, teams, output_path="bracket.png"):
    if not os.path.exists("base_bracket.png"):
        print("base_bracket.png não encontrado!")
        return False
        
    img = Image.open("base_bracket.png").convert("RGBA")
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("arial.ttf", 10)
        font_bold = ImageFont.truetype("arialbd.ttf", 10)
        font_title = ImageFont.truetype("arialbd.ttf", 18)
    except IOError:
        font = ImageFont.load_default()
        font_bold = ImageFont.load_default()
        font_title = ImageFont.load_default()

    draw.text((40, 20), "Mix do ProHouse REMATCH", fill=(255, 255, 255, 255), font=font_title)
    
    # Determinar N
    num_teams = len(teams)
    N = get_next_power_of_2(num_teams)
    
    if any(mid.startswith("U1_5") or mid.startswith("U1_6") for mid in matches):
        N = 16
    elif any(mid.startswith("U1_3") or mid.startswith("U1_4") for mid in matches):
        N = 8
    elif any(mid.startswith("U1_2") for mid in matches):
        N = 4
    else:
        N = 2

    if N == 2:
        box_width, box_height = 180, 50
        coords = {
            "U1_1": {"x": 200, "y": 200, "label": "Final Upper"},
            "GF_1": {"x": 580, "y": 200, "label": "Grande Final"}
        }
        connections = [
            ("U1_1", "GF_1", "win")
        ]
    elif N == 4:
        box_width, box_height = 180, 50
        coords = {
            "U1_1": {"x": 80, "y": 80, "label": "Semifinal Upper 1"},
            "U1_2": {"x": 80, "y": 200, "label": "Semifinal Upper 2"},
            "U2_1": {"x": 340, "y": 140, "label": "Final Upper"},
            "L1_1": {"x": 80, "y": 380, "label": "Semifinal Lower"},
            "L2_1": {"x": 340, "y": 380, "label": "Final Lower"},
            "GF_1": {"x": 620, "y": 260, "label": "Grande Final"}
        }
        connections = [
            ("U1_1", "U2_1", "win_top"),
            ("U1_2", "U2_1", "win_bottom"),
            ("U1_1", "L1_1", "lose"),
            ("U1_2", "L1_1", "lose"),
            ("U2_1", "GF_1", "win_top"),
            ("L1_1", "L2_1", "win"),
            ("U2_1", "L2_1", "lose"),
            ("L2_1", "GF_1", "win_bottom")
        ]
    elif N == 8:
        box_width, box_height = 170, 50
        coords = {
            "U1_1": {"x": 40, "y": 40, "label": "Quartas Upper 1"},
            "U1_2": {"x": 40, "y": 100, "label": "Quartas Upper 2"},
            "U1_3": {"x": 40, "y": 160, "label": "Quartas Upper 3"},
            "U1_4": {"x": 40, "y": 220, "label": "Quartas Upper 4"},
            "U2_1": {"x": 240, "y": 70, "label": "Semifinal Upper 1"},
            "U2_2": {"x": 240, "y": 190, "label": "Semifinal Upper 2"},
            "U3_1": {"x": 440, "y": 130, "label": "Final Upper"},
            
            "L1_1": {"x": 40, "y": 340, "label": "Lower R1.1"},
            "L1_2": {"x": 40, "y": 450, "label": "Lower R1.2"},
            "L2_1": {"x": 240, "y": 340, "label": "Lower R2.1"},
            "L2_2": {"x": 240, "y": 450, "label": "Lower R2.2"},
            "L3_1": {"x": 440, "y": 395, "label": "Semifinal Lower"},
            "L4_1": {"x": 640, "y": 395, "label": "Final Lower"},
            
            "GF_1": {"x": 810, "y": 245, "label": "Grande Final"}
        }
        connections = [
            ("U1_1", "U2_1", "win_top"),
            ("U1_2", "U2_1", "win_bottom"),
            ("U1_3", "U2_2", "win_top"),
            ("U1_4", "U2_2", "win_bottom"),
            ("U2_1", "U3_1", "win_top"),
            ("U2_2", "U3_1", "win_bottom"),
            
            ("L1_1", "L2_1", "win"),
            ("L1_2", "L2_2", "win"),
            ("L2_1", "L3_1", "win_top"),
            ("L2_2", "L3_1", "win_bottom"),
            ("L3_1", "L4_1", "win"),
            
            ("U3_1", "GF_1", "win_top"),
            ("L4_1", "GF_1", "win_bottom")
        ]
    else: # N = 16
        box_width, box_height = 130, 38
        coords = {}
        for i in range(1, 9):
            coords[f"U1_{i}"] = {"x": 30, "y": 25 + (i - 1) * 32, "label": f"U1_{i}"}
        for i in range(1, 5):
            coords[f"U2_{i}"] = {"x": 170, "y": 40 + (i - 1) * 64, "label": f"U2_{i}"}
        coords["U3_1"] = {"x": 310, "y": 70, "label": "U3_1"}
        coords["U3_2"] = {"x": 310, "y": 200, "label": "U3_2"}
        coords["U4_1"] = {"x": 450, "y": 130, "label": "Final Upper"}
        
        for i in range(1, 5):
            coords[f"L1_{i}"] = {"x": 30, "y": 300 + (i - 1) * 64, "label": f"L1_{i}"}
        for i in range(1, 5):
            coords[f"L2_{i}"] = {"x": 170, "y": 300 + (i - 1) * 64, "label": f"L2_{i}"}
        coords["L3_1"] = {"x": 310, "y": 332, "label": "L3_1"}
        coords["L3_2"] = {"x": 310, "y": 460, "label": "L3_2"}
        coords["L4_1"] = {"x": 450, "y": 332, "label": "L4_1"}
        coords["L4_2"] = {"x": 450, "y": 460, "label": "L4_2"}
        coords["L5_1"] = {"x": 590, "y": 396, "label": "Semifinal Lower"}
        coords["L6_1"] = {"x": 730, "y": 396, "label": "Final Lower"}
        coords["GF_1"] = {"x": 870, "y": 260, "label": "Grande Final"}
        
        connections = [
            ("U1_1", "U2_1", "win_top"), ("U1_2", "U2_1", "win_bottom"),
            ("U1_3", "U2_2", "win_top"), ("U1_4", "U2_2", "win_bottom"),
            ("U1_5", "U2_3", "win_top"), ("U1_6", "U2_3", "win_bottom"),
            ("U1_7", "U2_4", "win_top"), ("U1_8", "U2_4", "win_bottom"),
            ("U2_1", "U3_1", "win_top"), ("U2_2", "U3_1", "win_bottom"),
            ("U2_3", "U3_2", "win_top"), ("U2_4", "U3_2", "win_bottom"),
            ("U3_1", "U4_1", "win_top"), ("U3_2", "U4_1", "win_bottom"),
            ("L1_1", "L2_1", "win"), ("L1_2", "L2_2", "win"),
            ("L1_3", "L2_3", "win"), ("L1_4", "L2_4", "win"),
            ("L2_1", "L3_1", "win_top"), ("L2_2", "L3_1", "win_bottom"),
            ("L2_3", "L3_2", "win_top"), ("L2_4", "L3_2", "win_bottom"),
            ("L3_1", "L4_1", "win"), ("L3_2", "L4_2", "win"),
            ("L4_1", "L5_1", "win_top"), ("L4_2", "L5_1", "win_bottom"),
            ("L5_1", "L6_1", "win"),
            ("U4_1", "GF_1", "win_top"), ("L6_1", "GF_1", "win_bottom")
        ]

    for src, dst, link in connections:
        if src in coords and dst in coords:
            s = coords[src]
            d = coords[dst]
            
            x_src = s["x"] + box_width
            y_src = s["y"] + box_height // 2
            
            x_dst = d["x"]
            if "top" in link:
                y_dst = d["y"] + box_height // 4
            elif "bottom" in link:
                y_dst = d["y"] + (box_height * 3) // 4
            else:
                y_dst = d["y"] + box_height // 2
                
            mid_x = (x_src + x_dst) // 2
            line_color = (99, 102, 241, 180)
            draw.line([(x_src, y_src), (mid_x, y_src)], fill=line_color, width=2)
            draw.line([(mid_x, y_src), (mid_x, y_dst)], fill=line_color, width=2)
            draw.line([(mid_x, y_dst), (x_dst, y_dst)], fill=line_color, width=2)

    for mid, pos in coords.items():
        match = matches.get(mid)
        if not match:
            match = {"team_a_id": None, "team_b_id": None, "winner_id": None, "status": "pending", "label": pos["label"]}
            
        x, y = pos["x"], pos["y"]
        status = match.get("status", "pending")
        
        if status == "ongoing":
            border_color = (59, 130, 246, 255)
            bg_color = (23, 37, 84, 230)
        elif status == "completed":
            border_color = (34, 197, 94, 255)
            bg_color = (20, 83, 45, 230)
        else:
            border_color = (71, 85, 105, 180)
            bg_color = (15, 23, 42, 230)
            
        draw.rounded_rectangle([x, y, x + box_width, y + box_height], radius=6, fill=bg_color, outline=border_color, width=2)
        draw.line([x + 2, y + box_height // 2, x + box_width - 2, y + box_height // 2], fill=border_color, width=1)
        
        for idx, slot in enumerate(["team_a_id", "team_b_id"]):
            tid = match.get(slot)
            slot_y = y + idx * (box_height // 2)
            
            text_color = (255, 255, 255, 255)
            font_to_use = font
            
            if status == "completed":
                if match.get("winner_id") == tid and tid:
                    text_color = (74, 222, 128, 255)
                    font_to_use = font_bold
                elif tid:
                    text_color = (148, 163, 184, 180)
            
            if not tid:
                draw.text((x + 8, slot_y + (box_height // 4) - 6), "A definir", fill=(100, 116, 139, 255), font=font)
            elif tid == "BYE":
                draw.text((x + 8, slot_y + (box_height // 4) - 6), "BYE", fill=(148, 163, 184, 255), font=font)
            else:
                team = teams.get(str(tid))
                if team:
                    team_disp = team.get("name", team.get("team_name", team.get("captain_name", f"Time {str(tid)[:6]}")))
                    country = team.get("country", "")
                    logo_path = team.get("logo_path", "")
                else:
                    team_disp = f"Time {str(tid)[:6]}"
                    country = ""
                    logo_path = ""
                
                max_chars = 18 if box_width >= 170 else 13
                if len(team_disp) > max_chars:
                    team_disp = team_disp[:max_chars - 1] + "…"
                    
                flag_offset = 0
                if logo_path and os.path.exists(logo_path):
                    try:
                        logo_img = Image.open(logo_path).convert("RGBA")
                        f_h = max(12, (box_height // 2) - 6)
                        f_w = f_h
                        logo_img = logo_img.resize((f_w, f_h))
                        img.paste(logo_img, (x + 6, slot_y + 3), logo_img)
                        flag_offset = f_w + 6
                    except Exception as e:
                        print(f"Erro ao carregar logo do time {team_disp}: {e}")
                elif country:
                    flag_file = f"flags/{country}.png"
                    if os.path.exists(flag_file):
                        try:
                            flag_img = Image.open(flag_file).convert("RGBA")
                            f_h = (box_height // 2) - 8
                            f_w = int(f_h * 1.5)
                            flag_img = flag_img.resize((f_w, f_h))
                            img.paste(flag_img, (x + 8, slot_y + 4), flag_img)
                            flag_offset = f_w + 6
                        except Exception as e:
                            print(f"Erro ao desenhar bandeira {country}: {e}")
                            
                draw.text((x + 8 + flag_offset, slot_y + (box_height // 4) - 6), team_disp, fill=text_color, font=font_to_use)

    img.save(output_path)
    return True

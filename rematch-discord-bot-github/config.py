import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Posições válidas do jogo Rematch
POSITIONS = ["GK", "Fixo", "Ala Def", "Ala Of", "Pivô"]

# Posição do capitão
CAPTAIN_POSITION = "GK"

# Número mínimo de votos para aprovar um vencedor de partida
REQUIRED_VOTES = 6

# Nome do arquivo de banco de dados
DATABASE_FILE = "db.json"

# Pastas de armazenamento
LOGOS_DIR = "logos"
TICKETS_CATEGORY_NAME = "🎫 TICKETS REMATCH"


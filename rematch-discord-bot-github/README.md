# ⚽ Rematch Discord Bot - ProHouse REMATCH

Bot profissional de Discord para gerenciamento completo de **Mixes** e **Campeonatos** do jogo **Rematch**, equipado com sistema de **Tickets de Suporte**, **Fofocas Anônimas com Moderação**, **Geração Dinâmica de Chaveamentos (Brackets)** e **Narração TTS por Voz**.

---

## 🌟 Funcionalidades Principais

1. **⚽ Sistema Completo de Mix**:
   - **Fase de Inscrições**: Inscrição por posições (`GK`, `Fixo`, `Ala Def`, `Ala Of`, `Pivô`).
   - **Fase de Draft (Picks)**: Escolha de jogadores em rodadas intercaladas por capitães (GK) com timer de **1m30s** por turno e seleção aleatória automática no timeout.
   - **Fase de Proteção**: Capitães escolhem proteção simples (1 jogador) ou dupla (2 jogadores, time imune e não pode roubar) com timer de **1m30s**.
   - **Fase de Roubo (Trocas Forçadas)**: Realização de trocas de jogadores entre times com timer de **1m30s** por turno.
   - **Comando `$resetarpainel`**: Reenvia os painéis interativos mantendo 100% das informações salvas.

2. **🏆 Sistema de Campeonatos**:
   - Formatos suportados: **Eliminação Simples (Single Elimination)**, **Eliminação Dupla (Double Elimination)**, **Formato Suíço** e **Pontos Corridos**.
   - Geração gráfica automática de tabelas/chaveamentos com logos dos times inseridas via Pillow.
   - Sistema de votação de resultado de partidas diretamente nos canais com canais de narração por voz automatizada.

3. **🎫 Painel de Tickets de Suporte (`!ticket`)**:
   - Painel interativo com 7 categorias (*Pagar inscrição*, *Dúvidas*, *Criar time*, *Denúncia*, *Parcerias*, *Doações*, *Reportar bug*).
   - Criação automática de canais privados de suporte com botão para fechar ticket.

4. **📢 Anúncios Oficiais (`!anunciar`)**:
   - Formatação rápida em Embed para publicações oficiais com suporte a imagem anexada.

5. **🛡️ Criação Automática de Times (`!criartime <Nome>`)**:
   - Cria o cargo do time no Discord, atribui ao líder e armazena a logo oficial.

6. **💬 Fofocas Anônimas com Moderação (`!fofoca`, `!fofocaaqui`, `!fofocaaprovar`)**:
   - Envio 100% anônimo para o canal de moderação dos administradores.
   - Botões de `✅ Aceitar` (publica anonimamente) e `❌ Negar` (notifica o autor por DM e revela o autor apenas no canal dos ADMs).

---

## 🚀 Como Instalar e Rodar Localmente

### Pré-requisitos
- Python 3.10 ou superior
- Pip instalado

### 1. Clonar o Repositório
```bash
git clone https://github.com/SEU_USUARIO/rematch-discord-bot.git
cd rematch-discord-bot
```

### 2. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 3. Configurar as Variáveis de Ambiente
Crie um arquivo `.env` na raiz do projeto baseado no `.env.example`:
```env
DISCORD_TOKEN=seu_token_do_bot_aqui
```

### 4. Iniciar o Bot
```bash
python bot.py
```

---

## ☁️ Hospedagem na Nuvem (Railway / Render / VPS)

1. Crie um novo projeto na sua plataforma de hospedagem de preferência (ex: Railway, Render, Fly.io, Heroku ou VPS Linux/Windows).
2. Conecte o seu repositório do GitHub.
3. Configure a variável de ambiente `DISCORD_TOKEN` nas configurações da hospedagem.
4. O comando de inicialização será: `python bot.py`.

---

## 📜 Licença
Este projeto é de uso exclusivo da comunidade **ProHouse REMATCH**.

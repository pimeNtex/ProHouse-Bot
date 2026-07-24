# Imagem base Python slim
FROM python:3.11-slim

# Instalar ffmpeg e pacotes do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar arquivos do projeto
COPY . .

# Comando para iniciar o bot
CMD ["python", "bot.py"]

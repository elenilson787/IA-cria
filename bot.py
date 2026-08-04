import base64
from flask import Flask
import json
import os
import threading
import time
from PIL import Image, ImageOps
from openai import OpenAI
import telebot
import fal_client

# --- SERVIDOR HTTP PARA MANTER O RENDER ATIVO ---
app = Flask(__name__)

@app.route("/")
def home():
    return "🤖 Bot do Telegram TikTok Shop rodando via Fal.ai!"

# --- VARIÁVEIS DE AMBIENTE ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
FAL_KEY = os.getenv("FAL_KEY")  # A nova chave do Fal.ai

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client_openai = OpenAI(api_key=OPENAI_KEY)


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def otimizar_imagem(caminho_imagem):
    """Ajusta rotação da foto e otimiza a resolução"""
    with Image.open(caminho_imagem) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img.thumbnail((1024, 1024))
        img.save(caminho_imagem, "JPEG", quality=90)


def analisar_produto_e_criar_prompts(caminho_imagem):
    """Gera 2 prompts em inglês via GPT-4o-mini caso a legenda esteja vazia"""
    base64_image = encode_image(caminho_imagem)

    prompt_instrucao = """
    Examine esta imagem de produto e gere DOIS PROMPTS EM INGLÊS para geração de vídeo Image-to-Video.
    - PROMPT 1: Ação inicial/preparação. Movimento de câmera: [Push in].
    - PROMPT 2: Resultado final/conclusão. Movimento de câmera: [Close-up].
    Responda APENAS em JSON válido com as chaves "prompt_1" e "prompt_2".
    """

    response = client_openai.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_instrucao},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        },
                    },
                ],
            }
        ],
        max_tokens=500,
    )

    dados = json.loads(response.choices[0].message.content.strip())
    return dados.get("prompt_1", ""), dados.get("prompt_2", "")


def gerar_video_fal(caminho_imagem, prompt):
    """Chama a API do Fal.ai usando o modelo MiniMax"""
    # 1. Faz o upload da imagem para os servidores do Fal.ai
    image_url = fal_client.upload_file(caminho_imagem)

    # 2. Inscreve a requisição para gerar o vídeo
    result = fal_client.subscribe(
        "fal-ai/minimax-video",
        arguments={
            "prompt": prompt,
            "image_url": image_url
        },
    )

    return result["video"]["url"]


@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    bot.reply_to(message, "📸 Imagem recebida! Processando pelo Fal.ai...")

    foto_local = f"temp_{message.message_id}.jpg"

    try:
        if not FAL_KEY:
            bot.send_message(
                message.chat.id,
                "⚠️ **Erro:** A variável `FAL_KEY` não foi encontrada no Render.",
            )
            return

        # 1. Download e otimização da foto
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        with open(foto_local, "wb") as new_file:
            new_file.write(downloaded_file)

        otimizar_imagem(foto_local)

        # 2. Definição dos Prompts (Legenda Customizada ou IA)
        user_caption = message.caption if message.caption else ""

        if user_caption.strip():
            if "|" in user_caption:
                partes = user_caption.split("|")
                prompt_1, prompt_2 = partes[0].strip(), partes[1].strip()
            else:
                prompt_1 = user_caption.strip()
                prompt_2 = f"{user_caption.strip()}, continuous action"
            bot.send_message(message.chat.id, "✏️ **Prompts recebidos da legenda!**")
        else:
            bot.send_message(message.chat.id, "🤖 **Gerando roteiro com IA...**")
            prompt_1, prompt_2 = analisar_produto_e_criar_prompts(foto_local)

        bot.send_message(
            message.chat.id,
            f"📝 **Roteiro:**\n\n🔹 **Vídeo 1:** `{prompt_1}`\n\n🔸 **Vídeo 2:** `{prompt_2}`",
            parse_mode="Markdown",
        )

        # 3. Gerar e enviar Vídeo 1
        bot.send_message(message.chat.id, "🎬 **Gerando Vídeo 1/2 no Fal.ai...** *(Aguarde, é rápido!)*")
        video_url_1 = gerar_video_fal(foto_local, prompt_1)
        bot.send_video(message.chat.id, video_url_1, caption="▶️ **Parte 1:** Ação Inicial")

        # 4. Gerar e enviar Vídeo 2
        bot.send_message(message.chat.id, "🎬 **Gerando Vídeo 2/2 no Fal.ai...** *(Quase lá)*")
        video_url_2 = gerar_video_fal(foto_local, prompt_2)
        bot.send_video(message.chat.id, video_url_2, caption="✅ **Parte 2:** Resultado Final")

    except Exception as e:
        bot.reply_to(message, f"❌ Erro ao gerar: {str(e)}")

    finally:
        if os.path.exists(foto_local):
            os.remove(foto_local)


def iniciar_telegram():
    print("🤖 Bot iniciado...")
    bot.polling(non_stop=True)


if __name__ == "__main__":
    t = threading.Thread(target=iniciar_telegram)
    t.daemon = True
    t.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
    

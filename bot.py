import base64
from flask import Flask
import json
import os
import threading
import time
from PIL import Image, ImageOps
from openai import OpenAI
import requests
import telebot

# --- SERVIDOR HTTP PARA O RENDER ---
app = Flask(__name__)


@app.route("/")
def home():
    return "🤖 Bot do Telegram TikTok Shop rodando via Modal.com Serverless GPU!"


# --- VARIÁVEIS DE AMBIENTE ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
MODAL_URL = os.getenv("MODAL_URL")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client_openai = OpenAI(api_key=OPENAI_KEY)


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def otimizar_imagem(caminho_imagem):
    """Ajusta a rotação da foto do celular e otimiza a resolução"""
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


def gerar_video_modal(caminho_imagem, prompt):
    """Envia a imagem e prompt para a GPU serverless no Modal.com"""
    if not MODAL_URL:
        raise Exception(
            "Variável MODAL_URL não configurada no painel do Render!"
        )

    # Converte imagem local para Base64
    img_b64 = encode_image(caminho_imagem)

    payload = {"prompt": prompt, "image_base64": img_b64}

    # Envia requisição para a GPU no Modal (timeout de 5 minutos)
    response = requests.post(MODAL_URL, json=payload, timeout=300)

    if response.status_code == 200:
        caminho_video = f"temp_video_{int(time.time())}.mp4"
        with open(caminho_video, "wb") as f:
            f.write(response.content)
        return caminho_video
    else:
        raise Exception(
            f"Erro na GPU do Modal ({response.status_code}): {response.text}"
        )


@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    bot.reply_to(
        message, "📸 Imagem recebida! Processando na GPU Serverless..."
    )

    foto_local = f"temp_{message.message_id}.jpg"
    videos_gerados = []

    try:
        if not MODAL_URL:
            bot.send_message(
                message.chat.id,
                "⚠️ **Erro:** A variável `MODAL_URL` não foi encontrada no Render.",
            )
            return

        # 1. Download e otimização da foto
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        with open(foto_local, "wb") as new_file:
            new_file.write(downloaded_file)

        otimizar_imagem(foto_local)

        # 2. Obtenção dos prompts
        user_caption = message.caption if message.caption else ""

        if user_caption.strip():
            if "|" in user_caption:
                partes = user_caption.split("|")
                prompt_1, prompt_2 = partes[0].strip(), partes[1].strip()
            else:
                prompt_1 = user_caption.strip()
                prompt_2 = f"{user_caption.strip()}, continuous action"
            bot.send_message(
                message.chat.id, "✏️ **Prompts recebidos da legenda!**"
            )
        else:
            bot.send_message(
                message.chat.id, "🤖 **Gerando roteiro com IA...**"
            )
            prompt_1, prompt_2 = analisar_produto_e_criar_prompts(foto_local)

        bot.send_message(
            message.chat.id,
            f"📝 **Roteiro:**\n\n🔹 **Vídeo 1:** `{prompt_1}`\n\n🔸 **Vídeo 2:** `{prompt_2}`",
            parse_mode="Markdown",
        )

        # 3. Gerar Vídeo 1
        bot.send_message(
            message.chat.id,
            "🎬 **Gerando Vídeo 1/2 na GPU...** *(Pode levar cerca de 1 minuto)*",
        )
        v1_path = gerar_video_modal(foto_local, prompt_1)
        videos_gerados.append(v1_path)

        with open(v1_path, "rb") as vid:
            bot.send_video(
                message.chat.id, vid, caption="▶️ **Parte 1:** Ação Inicial"
            )

        # 4. Gerar Vídeo 2
        bot.send_message(
            message.chat.id,
            "🎬 **Gerando Vídeo 2/2 na GPU...** *(Quase lá)*",
        )
        v2_path = gerar_video_modal(foto_local, prompt_2)
        videos_gerados.append(v2_path)

        with open(v2_path, "rb") as vid:
            bot.send_video(
                message.chat.id, vid, caption="✅ **Parte 2:** Resultado Final"
            )

    except Exception as e:
        bot.reply_to(message, f"❌ Erro ao gerar vídeo: {str(e)}")

    finally:
        # Limpeza de arquivos temporários
        if os.path.exists(foto_local):
            os.remove(foto_local)
        for path in videos_gerados:
            if os.path.exists(path):
                os.remove(path)


def iniciar_telegram():
    print("🤖 Bot iniciado...")
    bot.polling(non_stop=True)


if __name__ == "__main__":
    t = threading.Thread(target=iniciar_telegram)
    t.daemon = True
    t.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

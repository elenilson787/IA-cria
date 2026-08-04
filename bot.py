import base64
from flask import Flask
from gradio_client import Client, handle_file
import json
import os
import threading
import time
from PIL import Image, ImageOps
from openai import OpenAI
import telebot

# --- SERVIDOR HTTP PARA MANTER O RENDER ATIVO ---
app = Flask(__name__)


@app.route("/")
def home():
    return "🤖 Bot do Telegram TikTok Shop rodando via Hugging Face!"


# --- VARIÁVEIS DE AMBIENTE ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

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
    - PROMPT 1: Ação inicial/preparação.
    - PROMPT 2: Resultado final/conclusão.
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


def gerar_video_huggingface(caminho_imagem, prompt):
    """Chama a API do CogVideoX no Hugging Face com o parâmetro de vídeo corrigido"""
    client = Client("THUDM/CogVideoX-5B-Space")

    result = client.predict(
        prompt=prompt,
        image_input=handle_file(caminho_imagem),
        video_input=None,  # Parâmetro obrigatório do modelo ajustado para None
        api_name="/generate",
    )

    if isinstance(result, (list, tuple)):
        return result[0]
    return result


@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    bot.reply_to(
        message, "📸 Imagem recebida! Processando via Hugging Face..."
    )

    foto_local = f"temp_{message.message_id}.jpg"

    try:
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

        # 3. Gerar e enviar Vídeo 1
        bot.send_message(
            message.chat.id,
            "🎬 **Gerando Vídeo 1/2 no Hugging Face...** *(Aguarde)*",
        )
        video_path_1 = gerar_video_huggingface(foto_local, prompt_1)
        with open(video_path_1, "rb") as v1:
            bot.send_video(
                message.chat.id, v1, caption="▶️ **Parte 1:** Ação Inicial"
            )

        # 4. Gerar e enviar Vídeo 2
        bot.send_message(
            message.chat.id,
            "🎬 **Gerando Vídeo 2/2 no Hugging Face...** *(Aguarde)*",
        )
        video_path_2 = gerar_video_huggingface(foto_local, prompt_2)
        with open(video_path_2, "rb") as v2:
            bot.send_video(
                message.chat.id, v2, caption="✅ **Parte 2:** Resultado Final"
            )

    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {str(e)}")

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
        

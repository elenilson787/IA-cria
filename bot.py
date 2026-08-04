import os
import base64
import threading
from flask import Flask
import telebot
from openai import OpenAI
import replicate
from PIL import Image, ImageOps

# --- SERVIDOR HTTP PARA MANTER O RENDER ATIVO ---
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot do Telegram TikTok Shop está rodando com MiniMax Video-01!"

# --- VARIÁVEIS DE AMBIENTE ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
REPLICATE_KEY = os.getenv("REPLICATE_API_TOKEN")

# Inicialização dos Clientes
bot = telebot.TeleBot(TELEGRAM_TOKEN)
client_openai = OpenAI(api_key=OPENAI_KEY)


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def otimizar_imagem(caminho_imagem):
    """Corrige rotação da foto do celular e ajusta resolução"""
    with Image.open(caminho_imagem) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert('RGB')
        img.thumbnail((1024, 1024))
        img.save(caminho_imagem, 'JPEG', quality=90)


def analisar_produto_e_criar_prompt(caminho_imagem):
    base64_image = encode_image(caminho_imagem)
    
    prompt_instrucao = """
    Examine esta imagem de produto. Identifique o tipo de objeto.
    Escreva um PROMPT ULTRA DETALHADO EM INGLÊS para um modelo de geração de vídeo do tipo Image-to-Video.
    
    Regras do Prompt de Vídeo:
    1. Descreva uma pessoa usando este objeto de forma natural no ambiente apropriado.
    2. Especifique movimento de câmera (ex: [Push in], [Slow zoom in], eye-level cinematic shot).
    3. Responda APENAS com o prompt em inglês em até 3 frases. Sem introduções.
    """

    response = client_openai.chat.completions.create(
        model="gpt-4o-mini",
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
        max_tokens=250,
    )
    
    return response.choices[0].message.content.strip()


@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    bot.reply_to(message, "📸 Imagem recebida! Analisando o produto com a IA...")
    
    foto_local = f"temp_{message.message_id}.jpg"
    
    try:
        if not REPLICATE_KEY:
            bot.send_message(message.chat.id, "⚠️ **Erro:** A variável `REPLICATE_API_TOKEN` não foi encontrada no Render.")
            return

        # 1. Baixar a foto enviada pelo usuário
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        with open(foto_local, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        # 2. Otimizar a imagem
        otimizar_imagem(foto_local)
            
        # 3. Gerar o prompt ultra realista com o GPT-4o-mini
        prompt_video = analisar_produto_e_criar_prompt(foto_local)
        bot.send_message(message.chat.id, f"📝 **Prompt Gerado:**\n`{prompt_video}`", parse_mode="Markdown")
        bot.send_message(message.chat.id, "🎬 Gerando animação HD com MiniMax (Hailuo)... (pode levar de 1 a 2 minutos)")

        # 4. Enviar para o MiniMax Video-01 usando o parâmetro correto 'first_frame_image'
        rep_client = replicate.Client(api_token=REPLICATE_KEY.strip())

        with open(foto_local, "rb") as image_file:
            output = rep_client.run(
                "minimax/video-01", 
                input={
                    "prompt": prompt_video,
                    "first_frame_image": image_file,
                    "prompt_optimizer": True
                }
            )
        
        # Obter URL do vídeo gerado
        if hasattr(output, 'url'):
            video_url = output.url
        elif isinstance(output, list) and len(output) > 0:
            video_url = str(output[0])
        else:
            video_url = str(output)
        
        bot.send_video(message.chat.id, video_url, caption="✅ Seu vídeo HD com MiniMax está pronto!")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ocorreu um erro: {str(e)}")
        
    finally:
        if os.path.exists(foto_local):
            os.remove(foto_local)


def iniciar_telegram():
    print("🤖 Bot do Telegram iniciado...")
    bot.polling(non_stop=True)


if __name__ == "__main__":
    t = threading.Thread(target=iniciar_telegram)
    t.daemon = True
    t.start()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
    

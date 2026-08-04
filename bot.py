import os
import threading
from flask import Flask
import telebot
from openai import OpenAI
import replicate

# --- SERVIDOR HTTP PARA MANTER O RENDER ATIVO ---
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot do Telegram TikTok Shop está rodando com Wan 2.1!"

# --- VARIÁVEIS DE AMBIENTE ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
REPLICATE_KEY = os.getenv("REPLICATE_API_TOKEN")

# Inicialização dos Clientes
bot = telebot.TeleBot(TELEGRAM_TOKEN)
client_openai = OpenAI(api_key=OPENAI_KEY)


def analisar_produto_e_criar_prompt(url_imagem):
    prompt_instrucao = """
    Examine esta imagem de produto. Identifique o tipo de objeto.
    Escreva um PROMPT DETALHADO E OBJETIVO EM INGLÊS para um modelo de geração de vídeo do tipo Image-to-Video.
    
    Regras do Prompt de Vídeo:
    1. Descreva uma pessoa usando este objeto de forma natural no ambiente apropriado.
    2. Especifique o movimento de câmera (ex: slow zoom in, eye-level cinematic shot).
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
                            "url": url_imagem
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
    bot.reply_to(message, "📸 Imagem recebida! Obtendo link e analisando com a IA...")
    
    try:
        if not REPLICATE_KEY:
            bot.send_message(message.chat.id, "⚠️ **Erro:** A variável `REPLICATE_API_TOKEN` não foi encontrada no Render.")
            return

        # 1. Obter URL pública direta da imagem hospedada no Telegram
        file_info = bot.get_file(message.photo[-1].file_id)
        url_imagem = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"
            
        # 2. Analisar com GPT-4o-mini passando a URL direta
        prompt_video = analisar_produto_e_criar_prompt(url_imagem)
        bot.send_message(message.chat.id, f"📝 **Prompt Gerado:**\n`{prompt_video}`", parse_mode="Markdown")
        bot.send_message(message.chat.id, "🎬 Gerando animação com Wan 2.1... (pode levar de 1 a 2 minutos)")

        # 3. Enviar a URL pública direta para o Replicate
        rep_client = replicate.Client(api_token=REPLICATE_KEY.strip())

        output = rep_client.run(
            "wavespeedai/wan-2.1-i2v-480p", 
            input={
                "prompt": prompt_video,
                "image": url_imagem,
                "aspect_ratio": "9:16"
            }
        )
        
        # Tratamento da URL do vídeo gerado
        if isinstance(output, list) and len(output) > 0:
            video_url = str(output[0])
        elif hasattr(output, 'url'):
            video_url = output.url
        else:
            video_url = str(output)
        
        bot.send_video(message.chat.id, video_url, caption="✅ Seu vídeo 9:16 para o TikTok Shop está pronto!")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ocorreu um erro: {str(e)}")


def iniciar_telegram():
    print("🤖 Bot do Telegram iniciado...")
    bot.polling(non_stop=True)


if __name__ == "__main__":
    t = threading.Thread(target=iniciar_telegram)
    t.daemon = True
    t.start()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
    

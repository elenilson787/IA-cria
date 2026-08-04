import os
import json
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
    return "🤖 Bot do Telegram TikTok Shop está rodando com 2 Vídeos (MiniMax)!"

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
    """Corrige a rotação da foto do celular e ajusta a resolução"""
    with Image.open(caminho_imagem) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert('RGB')
        img.thumbnail((1024, 1024))
        img.save(caminho_imagem, 'JPEG', quality=90)


def analisar_produto_e_criar_prompts(caminho_imagem):
    """Gera 2 prompts em inglês: 1º para ação inicial, 2º para o resultado final"""
    base64_image = encode_image(caminho_imagem)
    
    prompt_instrucao = """
    Examine esta imagem de produto. Identifique o tipo de objeto.
    Você deve gerar DOIS PROMPTS ULTRA DETALHADOS EM INGLÊS para um modelo de geração de vídeo do tipo Image-to-Video.
    
    Regras para os Prompts:
    - PROMPT 1 (Ação Inicial/Preparação): Descreva uma pessoa iniciando o uso do produto no ambiente apropriado. Mostre a preparação, a instalação, o ato de ligar o botão, colocar os ingredientes ou aplicar o produto. Movimento de câmera: [Push in] ou [Slow zoom in].
    - PROMPT 2 (Resultado/Ação Final): Descreva a conclusão do processo com o mesmo produto. Mostre o resultado perfeito, a pessoa retirando o alimento pronto, exibindo a superfície limpa ou o resultado final com entusiasmo. Movimento de câmera: [Close-up] ou [Wide shot reveal].
    
    Responda APENAS em formato JSON válido contendo exatamente as chaves "prompt_1" e "prompt_2".
    Exemplo de formato esperado:
    {
      "prompt_1": "...",
      "prompt_2": "..."
    }
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
    
    conteudo = response.choices[0].message.content.strip()
    dados = json.loads(conteudo)
    return dados.get("prompt_1", ""), dados.get("prompt_2", "")


def gerar_video_replicate(caminho_imagem, prompt):
    """Função auxiliar para chamar o MiniMax no Replicate"""
    rep_client = replicate.Client(api_token=REPLICATE_KEY.strip())
    
    with open(caminho_imagem, "rb") as image_file:
        output = rep_client.run(
            "minimax/video-01", 
            input={
                "prompt": prompt,
                "first_frame_image": image_file,
                "prompt_optimizer": True
            }
        )
    
    if hasattr(output, 'url'):
        return output.url
    elif isinstance(output, list) and len(output) > 0:
        return str(output[0])
    return str(output)


@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    bot.reply_to(message, "📸 Imagem recebida! Analisando o produto para criar o roteiro em 2 partes...")
    
    foto_local = f"temp_{message.message_id}.jpg"
    
    try:
        if not REPLICATE_KEY:
            bot.send_message(message.chat.id, "⚠️ **Erro:** A variável `REPLICATE_API_TOKEN` não foi encontrada no Render.")
            return

        # 1. Baixar foto do Telegram e otimizar
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        with open(foto_local, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        otimizar_imagem(foto_local)
            
        # 2. Gerar os 2 Prompts com GPT-4o-mini
        prompt_1, prompt_2 = analisar_produto_e_criar_prompts(foto_local)
        
        msg_prompts = (
            f"📝 **Roteiro dos 2 Vídeos Gerado!**\n\n"
            f"🔹 **Vídeo 1 (Ação Inicial):**\n`{prompt_1}`\n\n"
            f"🔸 **Vídeo 2 (Resultado Final):**\n`{prompt_2}`"
        )
        bot.send_message(message.chat.id, msg_prompts, parse_mode="Markdown")

        # 3. Gerar e Enviar Vídeo 1
        bot.send_message(message.chat.id, "🎬 **Gerando Vídeo 1/2 (Ação Inicial)...**\n*(Pode levar de 1 a 2 minutos)*")
        video_url_1 = gerar_video_replicate(foto_local, prompt_1)
        bot.send_video(message.chat.id, video_url_1, caption="▶️ **Parte 1:** Ação Inicial / Preparação")

        # 4. Gerar e Enviar Vídeo 2
        bot.send_message(message.chat.id, "🎬 **Gerando Vídeo 2/2 (Resultado Final)...**\n*(Pode levar de 1 a 2 minutos)*")
        video_url_2 = gerar_video_replicate(foto_local, prompt_2)
        bot.send_video(message.chat.id, video_url_2, caption="✅ **Parte 2:** Resultado Final do Produto")
        
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
    

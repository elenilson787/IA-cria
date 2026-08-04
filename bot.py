import os
import base64
import requests
import telebot
from openai import OpenAI
import replicate

# --- CONFIGURAÇÃO DE CHAVES ---
TELEGRAM_TOKEN = "SEU_TELEGRAM_BOT_TOKEN_AQUI"
OPENAI_KEY = "SUA_OPENAI_API_KEY_AQUI"
REPLICATE_KEY = "SEU_REPLICATE_API_TOKEN_AQUI"

# Inicialização dos Clientes
bot = telebot.TeleBot(TELEGRAM_TOKEN)
client_openai = OpenAI(api_key=OPENAI_KEY)
os.environ["REPLICATE_API_TOKEN"] = REPLICATE_KEY


# Função auxiliar para converter imagem local em Base64
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


# 1. Função que usa o GPT-4o / GPT-4o-mini para analisar o produto e criar o Prompt de Vídeo
def analisar_produto_e_criar_prompt(caminho_imagem):
    base64_image = encode_image(caminho_imagem)
    
    prompt_instrucao = """
    Examine esta imagem de produto. Identifique o tipo de objeto (ex: utensílio de cozinha, produto de limpeza, roupa, acessório, etc.).
    Escreva um PROMPT ULTRA DETALHADO EM INGLÊS para um modelo de geração de vídeo do tipo Image-to-Video.
    
    Regras do Prompt de Vídeo:
    1. Descreva uma mulher usando este objeto exato de forma natural, realista e persuasiva no ambiente apropriado (ex: cozinha moderna se for utensílio, sala se for limpeza, vestindo se for roupa).
    2. Especifique o movimento de câmera (ex: slow zoom in, eye-level cinematic shot).
    3. Mencione a proporção vertical 9:16 perfeita para TikTok/Reels.
    4. Responda APENAS com o prompt em inglês, sem introduções ou explicações.
    """

    response = client_openai.chat.completions.create(
        model="gpt-4o-mini",  # Você pode usar "gpt-4o" para máxima precisão ou "gpt-4o-mini" para menor custo
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
        max_tokens=400,
    )
    
    return response.choices[0].message.content.strip()


# 2. Handler do Telegram quando você envia uma Foto
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    bot.reply_to(message, "📸 Imagem recebida! Analisando o produto com o GPT-4o e gerando o prompt de animação...")
    
    try:
        # Baixar a foto enviada pelo usuário
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        foto_local = "temp_product.jpg"
        with open(foto_local, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        # Passo A: Analisar imagem com OpenAI Vision
        prompt_video = analisar_produto_e_criar_prompt(foto_local)
        bot.send_message(message.chat.id, f"📝 **Prompt Criado pela IA (OpenAI):**\n`{prompt_video}`", parse_mode="Markdown")
        bot.send_message(message.chat.id, "🎬 Gerando vídeo no Replicate... (Isso pode levar de 1 a 3 minutos)")

        # Passo B: Gerar vídeo no Replicate
        with open(foto_local, "rb") as image_file:
            output = replicate.run(
                "luma/ray", 
                input={
                    "prompt": prompt_video,
                    "input_image": image_file,
                    "aspect_ratio": "9:16"
                }
            )
        
        video_url = output  # URL do vídeo gerado
        
        # Passo C: Enviar vídeo de volta para o usuário
        bot.send_video(message.chat.id, video_url, caption="✅ Seu vídeo para o TikTok Shop está pronto!")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ocorreu um erro: {str(e)}")

print("🤖 Bot iniciado com OpenAI e aguardando fotos...")
bot.polling()

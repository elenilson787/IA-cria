import os
import time
import requests
import telebot
import google.generativeai as genai
import replicate

# --- CONFIGURAÇÃO DE CHAVES ---
TELEGRAM_TOKEN = "SEU_TELEGRAM_BOT_TOKEN_AQUI"
GEMINI_KEY = "SUA_GEMINI_API_KEY_AQUI"
REPLICATE_KEY = "SEU_REPLICATE_API_TOKEN_AQUI"

# Inicialização
bot = telebot.TeleBot(TELEGRAM_TOKEN)
genai.configure(api_key=GEMINI_KEY)
os.environ["REPLICATE_API_TOKEN"] = REPLICATE_KEY

# 1. Função que usa o Gemini Vision para analisar o produto e criar o Prompt de Vídeo
def analisar_produto_e_criar_prompt(caminho_imagem):
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Upload da imagem para o Gemini
    sample_file = genai.upload_file(path=caminho_imagem)
    
    prompt_instrucao = """
    Examine esta imagem de produto. Identifique o tipo de objeto (ex: utensílio de cozinha, produto de limpeza, roupa, acessório, etc.).
    Escreva um PROMPT ULTRA DETALHADO EM INGLÊS para um modelo de geração de vídeo do tipo Image-to-Video.
    
    Regras do Prompt de Vídeo:
    1. Descreva uma mulher usando este objeto exato de forma natural, realista e persuasiva no ambiente apropriado (ex: cozinha moderna se for utensílio, sala se for limpeza, vestindo se for roupa).
    2. Especifique o movimento de câmera (ex: slow zoom in, eye-level cinematic shot).
    3. Mencione a proporção vertical 9:16 perfeita para TikTok/Reels.
    4. Responda APENAS com o prompt em inglês, sem introduções ou explicações.
    """
    
    response = model.generate_content([sample_file, prompt_instrucao])
    return response.text.strip()

# 2. Handler do Telegram quando você envia uma Foto
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    bot.reply_to(message, "📸 Imagem recebida! Analisando o produto e gerando o prompt de animação...")
    
    try:
        # Baixar a foto enviada pelo usuário
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        foto_local = "temp_product.jpg"
        with open(foto_local, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        # Passo A: Analisar imagem com Gemini
        prompt_video = analisar_produto_e_criar_prompt(foto_local)
        bot.send_message(message.chat.id, f"📝 **Prompt Criado pela IA:**\n`{prompt_video}`", parse_mode="Markdown")
        bot.send_message(message.chat.id, "🎬 Gerando vídeo por IA... (Isso pode levar de 1 a 3 minutos)")

        # Passo B: Fazer upload público temporário da foto para a API de Vídeo
        # (Neste exemplo usamos o modelo Luma Ray 2 ou MiniMax via Replicate)
        with open(foto_local, "rb") as image_file:
            output = replicate.run(
                "luma/ray", # Você também pode usar "minimax/video-01" ou outros modelos I2V
                input={
                    "prompt": prompt_video,
                    "input_image": image_file,
                    "aspect_ratio": "9:16"
                }
            )
        
        video_url = output  # URL do vídeo gerado em mp4
        
        # Passo C: Enviar vídeo de volta para o usuário no Telegram
        bot.send_video(message.chat.id, video_url, caption="✅ Seu vídeo para o TikTok Shop está pronto!")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ocorreu um erro ao gerar o vídeo: {str(e)}")

print("🤖 Bot iniciado e aguardando fotos...")
bot.polling()

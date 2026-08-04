import os
import base64
import telebot
from openai import OpenAI
import replicate

# Lê as variáveis de ambiente
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
REPLICATE_KEY = os.getenv("REPLICATE_API_TOKEN")

# Garante a chave do Replicate no sistema
if REPLICATE_KEY:
    os.environ["REPLICATE_API_TOKEN"] = REPLICATE_KEY

# Inicialização dos Clientes
bot = telebot.TeleBot(TELEGRAM_TOKEN)
client_openai = OpenAI(api_key=OPENAI_KEY)


# Converte imagem local em Base64
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


# 1. Analisa a imagem e cria o prompt com o GPT-4o-mini
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
        max_tokens=400,
    )
    
    return response.choices[0].message.content.strip()


# 2. Handler do Telegram para fotos
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    bot.reply_to(message, "📸 Imagem recebida! Analisando o produto com a IA...")
    
    # Nome único para a imagem baseado no ID da mensagem
    foto_local = f"temp_{message.message_id}.jpg"
    
    try:
        # Baixar foto do Telegram
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        with open(foto_local, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        # Passo A: Analisar com GPT
        prompt_video = analisar_produto_e_criar_prompt(foto_local)
        bot.send_message(message.chat.id, f"📝 **Prompt Gerado:**\n`{prompt_video}`", parse_mode="Markdown")
        bot.send_message(message.chat.id, "🎬 Gerando animação no Replicate... (pode levar de 1 a 3 minutos)")

        # Passo B: Gerar Vídeo no Replicate
        with open(foto_local, "rb") as image_file:
            output = replicate.run(
                "luma/ray", 
                input={
                    "prompt": prompt_video,
                    "input_image": image_file,
                    "aspect_ratio": "9:16"
                }
            )
        
        video_url = str(output)
        
        # Passo C: Enviar Vídeo
        bot.send_video(message.chat.id, video_url, caption="✅ Seu vídeo para o TikTok Shop está pronto!")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ocorreu um erro: {str(e)}")
        
    finally:
        # Limpeza do arquivo temporário
        if os.path.exists(foto_local):
            os.remove(foto_local)

print("🤖 Bot iniciado e pronto para receber fotos...")
# non_stop=True mantém o bot ativo mesmo em oscilações de rede
bot.polling(non_stop=True)

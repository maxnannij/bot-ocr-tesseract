# api/bot.py
import os
import json
import asyncio
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google.cloud import vision

# --- Configuración desde Variables de Entorno de Vercel ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
# Decodificar las credenciales de Google desde Base64
GOOGLE_CREDENTIALS_BASE64 = os.getenv('GOOGLE_CREDENTIALS_BASE64')

# Escribir las credenciales decodificadas a un archivo temporal que la librería de Google puede leer
# Vercel provee un sistema de archivos temporal en /tmp
credentials_path = "/tmp/google_credentials.json"
if GOOGLE_CREDENTIALS_BASE64:
    decoded_creds = base64.b64decode(GOOGLE_CREDENTIALS_BASE64)
    with open(credentials_path, "w") as f:
        f.write(decoded_creds.decode('utf-8'))
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path

# --- Lógica del Bot (similar a la anterior) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('¡Hola! Envíame una foto de una factura y extraeré el texto (desplegado en Vercel).')

def extraer_texto_de_imagen(image_bytes):
    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_bytes)
    response = client.document_text_detection(image=image)
    if response.error.message:
        raise Exception(f"Error en Google Vision: {response.error.message}")
    return response.full_text_annotation.text

async def procesar_imagen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_id = update.message.photo[-1].file_id
    new_file = await context.bot.get_file(file_id)
    image_bytes = await new_file.download_as_bytearray()
    
    await update.message.reply_text('Procesando desde Vercel...')
    
    try:
        texto_extraido = extraer_texto_de_imagen(bytes(image_bytes))
        # Dividir el mensaje si es muy largo para Telegram
        for i in range(0, len(texto_extraido), 4096):
            await update.message.reply_text(texto_extraido[i:i + 4096])
    except Exception as e:
        await update.message.reply_text(f"Hubo un error: {e}")

# --- El "Handler" principal para Vercel ---
# Vercel llamará a esta función con la data del webhook de Telegram
async def handler(request):
    # Inicializar la aplicación del bot en cada llamada
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Añadir manejadores
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.PHOTO, procesar_imagen))

    # Procesar la actualización del webhook
    body = json.loads(request.body)
    update = Update.de_json(body, application.bot)
    await application.process_update(update)
    
    # Responder a Vercel que todo está OK
    return {'statusCode': 200, 'body': 'OK'}

# Esto es necesario para que Vercel pueda importar la función `handler`
# Si usas un framework como Flask/FastAPI, el setup es un poco distinto,
# pero para `python-telegram-bot` esto se puede hacer con su lógica interna.
# Para simplificar y asegurar compatibilidad, envolvemos el llamado asíncrono.
# A Vercel le basta con encontrar una función llamada `handler` que acepte un `request`.

# La forma más limpia de hacer esto es tener una función síncrona que llame a la asíncrona
from http.server import BaseHTTPRequestHandler
class vercel_handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length)
        
        # Ejecutamos nuestra lógica asíncrona
        asyncio.run(handler(type('Request', (), {'body': body})))
        
        # Respondemos a Vercel
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')

# Renombramos la clase para que Vercel la detecte
handler = vercel_handler

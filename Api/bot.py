import os
import asyncio
import json
import logging
import base64
import requests # Importamos la librería requests
from http.server import BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIGURACIÓN ---
# Vercel leerá estos valores de las Variables de Entorno.
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
# Ahora usaremos la API Key de Google Vision
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY') # LLENAR CON API

# Configuración del logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- LÓGICA DE GOOGLE VISION (con API Key y requests) ---
def extraer_texto_de_imagen(image_bytes: bytes) -> str:
    """
    Envía la imagen a la API de Google Vision usando una API Key y devuelve el texto.
    """
    if not GOOGLE_API_KEY:
        logger.error("La GOOGLE_API_KEY no está configurada en las variables de entorno.")
        return "Error: La clave de API del servicio de visión no está configurada."

    vision_url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_API_KEY}"
    
    # Codificar la imagen en Base64, que es como la API la espera
    encoded_image = base64.b64encode(image_bytes).decode('utf-8')
    
    # Construir el cuerpo de la petición JSON
    request_body = {
        "requests": [
            {
                "image": {
                    "content": encoded_image
                },
                "features": [
                    {
                        "type": "DOCUMENT_TEXT_DETECTION"
                    }
                ]
            }
        ]
    }
    
    try:
        # Hacer la petición POST a la API
        response = requests.post(vision_url, json=request_body)
        response.raise_for_status()  # Esto lanzará un error si la respuesta es 4xx o 5xx
        
        # Parsear la respuesta JSON
        response_json = response.json()
        
        # Extraer el texto completo de la anotación
        # La estructura de la respuesta puede ser compleja, hay que navegarla
        if 'responses' in response_json and len(response_json['responses']) > 0:
            first_response = response_json['responses'][0]
            if 'fullTextAnnotation' in first_response:
                return first_response['fullTextAnnotation']['text']
            else:
                logger.warning("No se encontró 'fullTextAnnotation' en la respuesta de la API.")
                return "No se detectó texto en la imagen."
        else:
            logger.error(f"Respuesta inesperada de la API de Vision: {response_json}")
            return "Error al analizar la respuesta del servicio de visión."
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error en la petición a Google Vision: {e}")
        return "Error de comunicación con el servicio de extracción de texto."
    except Exception as e:
        logger.error(f"Excepción inesperada en extraer_texto_de_imagen: {e}")
        return "Ocurrió un error inesperado al procesar la imagen."


# --- MANEJADORES DE TELEGRAM (sin cambios aquí) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('¡Hola! Soy tu bot de facturas. Envíame una foto y extraeré el texto.')

async def procesar_imagen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        return

    await update.message.reply_text('Imagen recibida. Procesando...')
    
    try:
        file_id = update.message.photo[-1].file_id
        new_file = await context.bot.get_file(file_id)
        image_bytes = await new_file.download_as_bytearray()
        
        texto_extraido = extraer_texto_de_imagen(bytes(image_bytes))
        
        if texto_extraido:
            for i in range(0, len(texto_extraido), 4096):
                await update.message.reply_text(texto_extraido[i:i + 4096])
        else:
            await update.message.reply_text('No se pudo extraer texto de la imagen.')
            
    except Exception as e:
        logger.error(f"Error en procesar_imagen: {e}")
        await update.message.reply_text('Lo siento, ocurrió un error inesperado.')


# --- PUNTO DE ENTRADA PARA VERCEL (sin cambios aquí, ya no maneja credenciales JSON) ---
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.PHOTO, procesar_imagen))

        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            
            async def process_update_async():
                update = Update.de_json(json.loads(body.decode('utf-8')), application.bot)
                await application.process_update(update)

            asyncio.run(process_update_async())
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
            
        except Exception as e:
            logger.error(f"Error al procesar el webhook: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'Error')
        return

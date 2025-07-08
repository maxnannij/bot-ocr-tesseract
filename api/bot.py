import os
import asyncio
import json
import logging
import base64
import requests
from http.server import BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIGURACIÓN DE VARIABLES DE ENTORNO Y LOGGING ---
# Vercel leerá estos valores de las Variables de Entorno configuradas en el panel.
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')

# Configuración del logging para poder ver los mensajes en los logs de Vercel
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
    
    # La API de Vision espera que la imagen esté codificada en Base64.
    encoded_image = base64.b64encode(image_bytes).decode('utf-8')
    
    # Construimos el cuerpo de la petición JSON según la documentación de la API.
    request_body = {
        "requests": [
            {
                "image": {
                    "content": encoded_image
                },
                "features": [
                    {
                        "type": "DOCUMENT_TEXT_DETECTION" # Ideal para facturas
                    }
                ]
            }
        ]
    }
    
    try:
        # Hacemos la petición POST a la API de Google.
        response = requests.post(vision_url, json=request_body, timeout=20) # Timeout de 20 seg
        response.raise_for_status()  # Lanza un error si la respuesta es 4xx o 5xx.
        
        response_json = response.json()
        
        # Navegamos la estructura de la respuesta para encontrar el texto.
        if 'responses' in response_json and len(response_json['responses']) > 0:
            first_response = response_json['responses'][0]
            if 'fullTextAnnotation' in first_response:
                return first_response['fullTextAnnotation']['text']
            elif 'error' in first_response:
                error_message = first_response['error'].get('message', 'Error desconocido')
                logger.error(f"La API de Vision devolvió un error: {error_message}")
                return f"Error de la API de Vision: {error_message}"
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


# --- MANEJADORES DE COMANDOS DE TELEGRAM ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde al comando /start."""
    await update.message.reply_text('¡Hola! Soy tu bot de facturas. Envíame una foto de un ticket y extraeré el texto para ti.')

async def procesar_imagen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa una imagen recibida y extrae el texto."""
    if not update.message.photo:
        return

    await update.message.reply_text('Imagen recibida. Procesando...')
    
    try:
        # Obtener el archivo de la foto con la mayor resolución.
        file_id = update.message.photo[-1].file_id
        new_file = await context.bot.get_file(file_id)
        
        # Descargar la imagen en memoria.
        image_bytes = await new_file.download_as_bytearray()
        
        # Llamar a nuestra función que contacta a Google Vision.
        texto_extraido = extraer_texto_de_imagen(bytes(image_bytes))
        
        if texto_extraido:
            # Telegram tiene un límite de 4096 caracteres por mensaje.
            # Este bucle divide el texto en trozos si es demasiado largo.
            for i in range(0, len(texto_extraido), 4096):
                await update.message.reply_text(texto_extraido[i:i + 4096])
        else:
            # Esto nunca debería pasar si la función devuelve mensajes de error, pero es una salvaguarda.
            await update.message.reply_text('No se pudo extraer texto de la imagen.')
            
    except Exception as e:
        logger.error(f"Error en procesar_imagen: {e}")
        await update.message.reply_text('Lo siento, ocurrió un error inesperado al procesar tu imagen.')


# --- PUNTO DE ENTRADA PARA VERCEL (SERVERLESS HANDLER) - CORREGIDO ---
class handler(BaseHTTPRequestHandler):
    
    def do_POST(self):
        """Maneja las peticiones POST entrantes de Telegram (webhook)."""
        # Inicializamos la aplicación del bot en cada invocación.
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Registramos los manejadores de comandos y mensajes.
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.PHOTO, procesar_imagen))

        try:
            # Obtenemos el cuerpo de la petición que envía Telegram.
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            
            # Creamos una función asíncrona para encapsular la lógica del bot.
            async def process_update_async():
                # INICIO DE LA CORRECCIÓN IMPORTANTE
                await application.initialize()  # Prepara la aplicación para funcionar.
                
                update = Update.de_json(json.loads(body.decode('utf-8')), application.bot)
                await application.process_update(update) # Procesa el mensaje.
                
                await application.shutdown()    # Libera los recursos de la aplicación.
                # FIN DE LA CORRECCIÓN IMPORTANTE

            # Ejecutamos nuestra lógica asíncrona.
            asyncio.run(process_update_async())
            
            # Respondemos a Vercel/Telegram que todo ha ido bien.
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
            
        except Exception as e:
            logger.error(f"Error crítico al procesar el webhook: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'Internal Server Error')
            
        return

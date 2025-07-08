import os
import asyncio
import json
import logging
import base64
from http.server import BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google.cloud import vision

# --- CONFIGURACIÓN ---
# Vercel leerá estos valores de las Variables de Entorno que configures en su panel.
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

# Las credenciales de Google se leen de una variable de entorno en formato Base64
# y se escriben en un archivo temporal que la librería de Google puede usar.
# Esto es necesario en un entorno serverless como Vercel.
GOOGLE_CREDENTIALS_BASE64 = os.getenv('GOOGLE_CREDENTIALS_BASE64')

# Configuración del logging para ver errores en Vercel
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- LÓGICA DE GOOGLE VISION ---
def extraer_texto_de_imagen(image_bytes: bytes) -> str:
    """
    Envía la imagen a la API de Google Vision y devuelve el texto extraído.
    """
    try:
        # La librería de Google Vision buscará las credenciales automáticamente
        # en la ruta definida por la variable de entorno 'GOOGLE_APPLICATION_CREDENTIALS'.
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_bytes)
        
        # 'document_text_detection' es ideal para facturas y documentos densos.
        response = client.document_text_detection(image=image)
        
        if response.error.message:
            logger.error(f"Error en Google Vision API: {response.error.message}")
            raise Exception(f"Google Vision API Error: {response.error.message}")
            
        return response.full_text_annotation.text
    except Exception as e:
        logger.error(f"Excepción al llamar a Google Vision: {e}")
        return "Error al procesar la imagen con el servicio de extracción."

# --- MANEJADORES DE COMANDOS DE TELEGRAM ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde al comando /start."""
    await update.message.reply_text('¡Hola! Soy tu bot de facturas. Envíame una foto de un ticket o factura y extraeré el texto para ti.')

async def procesar_imagen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa una imagen recibida y extrae el texto."""
    if not update.message.photo:
        return

    await update.message.reply_text('Imagen recibida. Procesando...')
    
    try:
        # Obtener el archivo de la foto con la mayor resolución
        file_id = update.message.photo[-1].file_id
        new_file = await context.bot.get_file(file_id)
        
        # Descargar la imagen en memoria como un array de bytes
        image_bytes = await new_file.download_as_bytearray()
        
        # Llamar a la función de Google Vision
        texto_extraido = extraer_texto_de_imagen(bytes(image_bytes))
        
        if texto_extraido:
            # Telegram tiene un límite de 4096 caracteres por mensaje.
            # Dividimos el texto en trozos si es necesario.
            for i in range(0, len(texto_extraido), 4096):
                await update.message.reply_text(texto_extraido[i:i + 4096])
        else:
            await update.message.reply_text('No se pudo extraer texto de la imagen.')
            
    except Exception as e:
        logger.error(f"Error en procesar_imagen: {e}")
        await update.message.reply_text('Lo siento, ocurrió un error inesperado al procesar tu imagen.')

# --- PUNTO DE ENTRADA PARA VERCEL (SERVERLESS HANDLER) ---
class handler(BaseHTTPRequestHandler):
    
    def do_POST(self):
        """Maneja las peticiones POST entrantes de Telegram (webhook)."""
        # Configurar las credenciales de Google al inicio de cada invocación
        if GOOGLE_CREDENTIALS_BASE64:
            try:
                credentials_path = "/tmp/google_credentials.json"
                decoded_creds = base64.b64decode(GOOGLE_CREDENTIALS_BASE64)
                with open(credentials_path, "w") as f:
                    f.write(decoded_creds.decode('utf-8'))
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
            except Exception as e:
                logger.error(f"Error al decodificar o escribir las credenciales de Google: {e}")
                # Responder a Vercel para que no reintente
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b'Credentials setup error')
                return

        # Inicializar la aplicación del bot
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Registrar los manejadores
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.PHOTO, procesar_imagen))

        # Procesar la petición
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            
            async def process_update_async():
                update = Update.de_json(json.loads(body.decode('utf-8')), application.bot)
                await application.process_update(update)

            # Ejecutar la función asíncrona
            asyncio.run(process_update_async())
            
            # Responder a Telegram/Vercel que todo está bien
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
            
        except Exception as e:
            logger.error(f"Error al procesar el webhook: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'Error')

        return

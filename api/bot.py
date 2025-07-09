import os
import asyncio
import json
import logging
from http.server import BaseHTTPRequestHandler
from PIL import Image # Importamos la librería Pillow
import pytesseract   # Importamos pytesseract
import io            # Para manejar los bytes de la imagen en memoria

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIGURACIÓN ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
# Ya no necesitamos GOOGLE_API_KEY

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- LÓGICA DE TESSERACT OCR ---
def extraer_texto_de_imagen(image_bytes: bytes) -> str:
    """
    Usa Tesseract para extraer texto de una imagen en memoria.
    """
    try:
        # Tesseract necesita un objeto de imagen, no solo bytes.
        # Usamos Pillow (PIL) para abrir la imagen desde los bytes en memoria.
        image = Image.open(io.BytesIO(image_bytes))
        
        # Llamamos a tesseract. especificamos el idioma (español + inglés).
        # Tesseract intentará usar ambos.
        texto_extraido = pytesseract.image_to_string(image, lang='spa+eng')
        
        if not texto_extraido.strip():
            logger.warning("Tesseract no devolvió texto.")
            return "No se pudo detectar texto en la imagen."
            
        return texto_extraido
        
    except Exception as e:
        logger.error(f"Error al procesar con Tesseract: {e}")
        # Este error puede ocurrir si Tesseract no está instalado correctamente en el entorno.
        return "Ocurrió un error en el motor de extracción de texto (OCR)."

#
# ... EL RESTO DEL CÓDIGO (MANEJADORES DE TELEGRAM Y LA CLASE HANDLER) SE MANTIENE EXACTAMENTE IGUAL ...
#
# Solo asegúrate de que la función procesar_imagen() llame a la nueva versión de extraer_texto_de_imagen().
# El código que te he proporcionado en respuestas anteriores ya está bien estructurado para esto.
# Solo reemplaza la función extraer_texto_de_imagen y los imports.

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('¡Hola! Soy tu bot de facturas (versión Tesseract). Envíame una foto y extraeré el texto.')

async def procesar_imagen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        return
    await update.message.reply_text('Imagen recibida. Procesando con Tesseract...')
    try:
        file_id = update.message.photo[-1].file_id
        new_file = await context.bot.get_file(file_id)
        image_bytes = await new_file.download_as_bytearray()
        texto_extraido = extraer_texto_de_imagen(bytes(image_bytes))
        if texto_extraido:
            for i in range(0, len(texto_extraido), 4096):
                await update.message.reply_text(texto_extraido[i:i + 4096])
    except Exception as e:
        logger.error(f"Error en procesar_imagen: {e}")
        await update.message.reply_text('Lo siento, ocurrió un error inesperado.')


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.PHOTO, procesar_imagen))
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            async def process_update_async():
                await application.initialize()
                update = Update.de_json(json.loads(body.decode('utf-8')), application.bot)
                await application.process_update(update)
                await application.shutdown()
            asyncio.run(process_update_async())
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
        except Exception as e:
            logger.error(f"Error crítico al procesar el webhook: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'Internal Server Error')
        return

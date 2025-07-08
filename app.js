// --- Mismo código inicial ---
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const statusDiv = document.getElementById('status');

pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.11.338/pdf.worker.min.js`;

['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, preventDefaults, false);
});
function preventDefaults(e) { e.preventDefault(); e.stopPropagation(); }

['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'), false);
});
['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'), false);
});

dropZone.addEventListener('drop', (e) => handleFiles(e.dataTransfer.files), false);
fileInput.addEventListener('change', (e) => handleFiles(e.target.files), false);

// --- La lógica principal sigue siendo la misma, pero llamará a las nuevas funciones de extracción ---
async function handleFiles(files) {
    if (files.length === 0) {
        statusDiv.textContent = 'No se seleccionó ningún archivo.';
        return;
    }
    const file = files[0];

    try {
        statusDiv.textContent = 'Leyendo archivo...';
        let image;
        if (file.type === "application/pdf") {
            statusDiv.textContent = 'Convirtiendo PDF a imagen... (esto puede tardar)';
            image = await getImageFromPDF(file);
        } else {
            image = file;
        }

        statusDiv.textContent = 'Reconociendo texto con OCR... (esto es lo que más tarda)';
        const { data: { text } } = await Tesseract.recognize(image, 'spa', {
            logger: m => {
                if (m.status === 'recognizing text') {
                    statusDiv.textContent = `Reconociendo texto... ${Math.round(m.progress * 100)}%`;
                }
            }
        });

        statusDiv.textContent = 'Extrayendo datos estructurados...';
        // ¡NUEVO! Llamamos a la función de extracción avanzada.
        const datos = extraerDatosDetallados(text);

        statusDiv.textContent = 'Creando archivo Excel...';
        // ¡NUEVO! Llamamos a la función de creación de Excel con múltiples hojas.
        crearYDescargarExcelDetallado(datos);

        statusDiv.textContent = '¡Listo! El archivo Excel se ha descargado.';
    } catch (error) {
        console.error(error);
        statusDiv.textContent = `Error: ${error.message}`;
    }
}

async function getImageFromPDF(pdfFile) {
    // Esta función no cambia
    const pdf = await pdfjsLib.getDocument(URL.createObjectURL(pdfFile)).promise;
    const page = await pdf.getPage(1);
    const viewport = page.getViewport({ scale: 2.0 });
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    canvas.height = viewport.height;
    canvas.width = viewport.width;
    await page.render({ canvasContext: context, viewport: viewport }).promise;
    return canvas.toDataURL();
}

// =================================================================================
// ¡AQUÍ ESTÁ LA NUEVA LÓGICA DE EXTRACCIÓN!
// =================================================================================

function extraerDatosDetallados(texto) {
    const lineas = texto.split('\n'); // Dividimos el texto completo en líneas individuales
    const resumen = {};
    const articulos = [];

    // --- Definimos nuestras Expresiones Regulares (RegEx) ---

    // RegEx para encontrar el total. Busca "TOTAL" (insensible a mayúsculas) seguido de un número.
    const regexTotal = /(?:TOTAL|IMPORTE)\s*€?\s*([\d,]+\.?\d*)/i;
    // RegEx para la fecha.
    const regexFecha = /\d{2}[/-]\d{2}[/-]\d{2,4}/;
    
    // RegEx para identificar una línea de artículo.
    // Esta es la más importante y compleja. Busca:
    // (Cualquier texto al principio) (un espacio) (un número con 2 decimales al final de la línea)
    // Ejemplo: "PAN DE MOLDE 1,50" -> Captura "PAN DE MOLDE" y "1,50"
    const regexArticulo = /^(.*?)\s+([\d,]+\.\d{2})$/;

    // --- Extraemos la información del Resumen ---
    resumen['Comercio'] = lineas[0] || 'No encontrado'; // Asumimos que el nombre del comercio es la primera línea.
    
    const matchFecha = texto.match(regexFecha);
    if (matchFecha) resumen['Fecha'] = matchFecha[0];

    const matchTotal = texto.match(regexTotal);
    if (matchTotal) resumen['Total'] = parseFloat(matchTotal[1].replace(',', '.'));

    // --- Iteramos sobre cada línea para encontrar los artículos ---
    for (const linea of lineas) {
        const lineaLimpia = linea.trim();
        const matchArticulo = lineaLimpia.match(regexArticulo);

        // Si la línea coincide con nuestro patrón de artículo...
        if (matchArticulo) {
            // ...y no es una línea de subtotal o total (para evitar duplicados)
            if (!/TOTAL|SUBTOTAL|IVA|PAGO|CAMBIO/i.test(lineaLimpia)) {
                
                // El primer grupo capturado es la descripción, el segundo es el precio
                let descripcion = matchArticulo[1].trim();
                const precio = parseFloat(matchArticulo[2].replace(',', '.'));
                
                // Intento (muy simple) de extraer la cantidad si está al principio
                let cantidad = 1; // Por defecto es 1
                const matchCantidad = descripcion.match(/^(\d+)\s+(.*)/);
                if (matchCantidad) {
                    cantidad = parseInt(matchCantidad[1]);
                    descripcion = matchCantidad[2]; // Actualizamos la descripción sin la cantidad
                }

                articulos.push({
                    'Artículo': descripcion,
                    'Cantidad': cantidad,
                    'Precio': precio
                });
            }
        }
    }

    return { resumen, articulos };
}


// =================================================================================
// ¡NUEVA FUNCIÓN PARA CREAR UN EXCEL CON MÚLTIPLES HOJAS!
// =================================================================================

function crearYDescargarExcelDetallado(datos) {
    // Crear un nuevo libro de trabajo
    const wb = XLSX.utils.book_new();

    // --- Hoja 1: Resumen del Ticket ---
    // `json_to_sheet` espera un array de objetos, por eso ponemos [datos.resumen]
    const ws_resumen = XLSX.utils.json_to_sheet([datos.resumen]);
    XLSX.utils.book_append_sheet(wb, ws_resumen, 'Resumen');

    // --- Hoja 2: Lista de Artículos ---
    if (datos.articulos.length > 0) {
        const ws_articulos = XLSX.utils.json_to_sheet(datos.articulos);
        XLSX.utils.book_append_sheet(wb, ws_articulos, 'Artículos');
    }

    // Generar el archivo y forzar la descarga
    XLSX.writeFile(wb, "ticket_detallado.xlsx");
}

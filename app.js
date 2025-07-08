const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const statusDiv = document.getElementById('status');

// Configurar el worker de pdf.js
pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.11.338/pdf.worker.min.js`;

// --- Eventos de Arrastre ---
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'), false);
});

['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'), false);
});

dropZone.addEventListener('drop', (e) => handleFiles(e.dataTransfer.files), false);
fileInput.addEventListener('change', (e) => handleFiles(e.target.files), false);

async function handleFiles(files) {
    if (files.length === 0) {
        statusDiv.textContent = 'No se seleccionó ningún archivo.';
        return;
    }
    const file = files[0];

    // --- Lógica principal ---
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

        statusDiv.textContent = 'Extrayendo datos...';
        const datos = extraerDatos(text);

        statusDiv.textContent = 'Creando archivo Excel...';
        crearYDescargarExcel(datos, text);

        statusDiv.textContent = '¡Listo! El archivo Excel se ha descargado.';
    } catch (error) {
        console.error(error);
        statusDiv.textContent = `Error: ${error.message}`;
    }
}

async function getImageFromPDF(pdfFile) {
    const pdf = await pdfjsLib.getDocument(URL.createObjectURL(pdfFile)).promise;
    const page = await pdf.getPage(1); // Tomamos solo la primera página
    const viewport = page.getViewport({ scale: 2.0 }); // Aumentamos la escala para mejor calidad de OCR
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    canvas.height = viewport.height;
    canvas.width = viewport.width;

    await page.render({ canvasContext: context, viewport: viewport }).promise;
    return canvas.toDataURL(); // Devuelve la imagen en formato base64
}

function extraerDatos(texto) {
    const datos = {};
    // Expresiones regulares en JavaScript (similares a Python)
    const fechaMatch = texto.match(/\d{2}[/-]\d{2}[/-]\d{2,4}/);
    if (fechaMatch) datos['Fecha'] = fechaMatch[0];

    // Busca TOTAL, IMPORTE, etc. seguido de un número con decimales
    const totalMatch = texto.match(/(?:TOTAL|IMPORTE)\s*€?\s*([\d,]+\.?\d*)/i);
    if (totalMatch) datos['Total'] = parseFloat(totalMatch[1].replace(',', '.'));
    
    // Aquí puedes añadir más RegEx para el nombre de la tienda, CIF, etc.

    return datos;
}

function crearYDescargarExcel(datos, textoCompleto) {
    // Prepara los datos para la hoja de cálculo
    const datosArray = Object.keys(datos).length > 0 ? [datos] : [{ "Info": "No se extrajeron datos estructurados." }];

    // Crear un nuevo libro de trabajo
    const wb = XLSX.utils.book_new();
    
    // Crear hoja con datos estructurados
    const ws1 = XLSX.utils.json_to_sheet(datosArray);
    XLSX.utils.book_append_sheet(wb, ws1, 'Datos Extraídos');

    // Crear hoja con el texto completo del OCR
    const ws2 = XLSX.utils.json_to_sheet([{ "Texto Completo OCR": textoCompleto }]);
    XLSX.utils.book_append_sheet(wb, ws2, 'Texto Completo');

    // Generar el archivo y forzar la descarga
    XLSX.writeFile(wb, "ticket_extraido.xlsx");
}

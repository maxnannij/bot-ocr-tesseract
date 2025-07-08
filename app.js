// --- Elementos del DOM ---
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const statusDiv = document.getElementById('status');
const resultContainer = document.getElementById('result-container');
const copyButton = document.getElementById('copy-button');

// Elementos para mostrar los datos
const resumenComercio = document.getElementById('resumen-comercio');
const resumenFecha = document.getElementById('resumen-fecha');
const resumenTotal = document.getElementById('resumen-total');
const articulosTbody = document.getElementById('articulos-tbody');

// --- Configuración y Eventos (sin cambios) ---
pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.11.338/pdf.worker.min.js`;
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(e => dropZone.addEventListener(e, preventDefaults, false));
function preventDefaults(e) { e.preventDefault(); e.stopPropagation(); }
['dragenter', 'dragover'].forEach(e => dropZone.addEventListener(e, () => dropZone.classList.add('dragover'), false));
['dragleave', 'drop'].forEach(e => dropZone.addEventListener(e, () => dropZone.classList.remove('dragover'), false));
dropZone.addEventListener('drop', (e) => handleFiles(e.dataTransfer.files), false);
fileInput.addEventListener('change', (e) => handleFiles(e.target.files), false);

// --- Lógica de Procesamiento ---
async function handleFiles(files) {
    if (files.length === 0) return;
    const file = files[0];
    resultContainer.classList.add('hidden');

    try {
        statusDiv.textContent = 'Leyendo archivo...';
        let image = file.type === "application/pdf" ? await getImageFromPDF(file) : file;

        statusDiv.textContent = 'Reconociendo texto con OCR...';
        const { data: { text } } = await Tesseract.recognize(image, 'spa', {
            logger: m => {
                if (m.status === 'recognizing text') statusDiv.textContent = `Reconociendo... ${Math.round(m.progress * 100)}%`;
            }
        });

        statusDiv.textContent = 'Extrayendo datos estructurados...';
        const datos = extraerDatosDetallados(text);

        statusDiv.textContent = '¡Proceso completado!';
        mostrarResultados(datos);

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
    canvas.height = viewport.height;
    canvas.width = viewport.width;
    const context = canvas.getContext('2d');
    await page.render({ canvasContext: context, viewport: viewport }).promise;
    return canvas.toDataURL();
}

// --- ¡NUEVAS FUNCIONES DE EXTRACCIÓN Y VISUALIZACIÓN! ---

function extraerDatosDetallados(texto) {
    const lineas = texto.split('\n');
    const resumen = {};
    const articulos = [];
    
    // RegEx para el total, fecha y artículos
    const regexTotal = /(?:TOTAL|IMPORTE)\s*€?\s*([\d,]+\.?\d*)/i;
    const regexFecha = /\d{2}[/-]\d{2}[/-]\d{2,4}/;
    // Esta RegEx busca líneas que terminen en un precio. Es la clave.
    const regexArticulo = /^(.*?)\s+([\d,]+\.\d{2})\s*$/;

    // Extraer resumen
    resumen['Comercio'] = lineas[0] || 'No encontrado'; // Asumimos que la primera línea es el comercio
    const matchFecha = texto.match(regexFecha);
    if (matchFecha) resumen['Fecha'] = matchFecha[0];
    const matchTotal = texto.match(regexTotal);
    if (matchTotal) resumen['Total'] = parseFloat(matchTotal[1].replace(',', '.'));

    // Extraer artículos
    for (const linea of lineas) {
        const lineaLimpia = linea.trim();
        const matchArticulo = lineaLimpia.match(regexArticulo);

        if (matchArticulo && !/TOTAL|SUBTOTAL|IVA|PAGO|CAMBIO/i.test(lineaLimpia)) {
            articulos.push({
                'Artículo': matchArticulo[1].trim(),
                'Monto': parseFloat(matchArticulo[2].replace(',', '.'))
            });
        }
    }
    return { resumen, articulos };
}

function mostrarResultados(datos) {
    // Rellenar el resumen
    resumenComercio.textContent = datos.resumen.Comercio || 'N/A';
    resumenFecha.textContent = datos.resumen.Fecha || 'N/A';
    resumenTotal.textContent = datos.resumen.Total ? datos.resumen.Total.toFixed(2) + ' €' : 'N/A';

    // Limpiar la tabla anterior
    articulosTbody.innerHTML = '';

    // Rellenar la tabla de artículos
    if (datos.articulos.length > 0) {
        datos.articulos.forEach(item => {
            const row = document.createElement('tr');
            
            const cellArticulo = document.createElement('td');
            cellArticulo.textContent = item.Artículo;
            
            const cellMonto = document.createElement('td');
            cellMonto.textContent = item.Monto.toFixed(2); // Formatear a 2 decimales
            
            row.appendChild(cellArticulo);
            row.appendChild(cellMonto);
            
            articulosTbody.appendChild(row);
        });
    } else {
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.colSpan = 2;
        cell.textContent = 'No se pudieron extraer artículos.';
        row.appendChild(cell);
        articulosTbody.appendChild(row);
    }

    // Mostrar el contenedor de resultados
    resultContainer.classList.remove('hidden');
}


// --- Lógica del botón de Copiar (adaptada) ---
copyButton.addEventListener('click', () => {
    let textoParaCopiar = `Resumen del Ticket\n`;
    textoParaCopiar += `-----------------\n`;
    textoParaCopiar += `Comercio: ${resumenComercio.textContent}\n`;
    textoParaCopiar += `Fecha: ${resumenFecha.textContent}\n`;
    textoParaCopiar += `Total General: ${resumenTotal.textContent}\n\n`;
    textoParaCopiar += `Artículos\n`;
    textoParaCopiar += `-----------------\n`;

    // Recorrer las filas de la tabla para construir el texto
    articulosTbody.querySelectorAll('tr').forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length === 2) {
            // Usamos \t (tabulador) para que se pueda pegar bien en un Excel
            textoParaCopiar += `${cells[0].textContent}\t${cells[1].textContent}\n`;
        }
    });

    navigator.clipboard.writeText(textoParaCopiar).then(() => {
        const originalText = copyButton.textContent;
        copyButton.textContent = '¡Copiado!';
        setTimeout(() => { copyButton.textContent = originalText; }, 1500);
    });
});

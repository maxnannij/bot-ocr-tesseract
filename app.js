// --- Elementos del DOM ---
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const statusDiv = document.getElementById('status');
const resultContainer = document.getElementById('result-container');
const resultText = document.getElementById('result-text');
const copyButton = document.getElementById('copy-button');

// Configurar el worker de pdf.js
pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.11.338/pdf.worker.min.js`;

// --- Eventos de Arrastre (sin cambios) ---
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

// --- Lógica de Procesamiento de Archivos (actualizada) ---
async function handleFiles(files) {
    if (files.length === 0) {
        statusDiv.textContent = 'No se seleccionó ningún archivo.';
        return;
    }
    const file = files[0];
    
    // Ocultar resultados anteriores mientras se procesa uno nuevo
    resultContainer.classList.add('hidden');

    try {
        statusDiv.textContent = 'Leyendo archivo...';
        let image;
        if (file.type === "application/pdf") {
            statusDiv.textContent = 'Convirtiendo PDF a imagen...';
            image = await getImageFromPDF(file);
        } else {
            image = file;
        }

        statusDiv.textContent = 'Reconociendo texto con OCR... (esto puede tardar)';
        const { data: { text } } = await Tesseract.recognize(image, 'spa', {
            logger: m => {
                if (m.status === 'recognizing text') {
                    statusDiv.textContent = `Reconociendo texto... ${Math.round(m.progress * 100)}%`;
                }
            }
        });

        // --- ¡AQUÍ ESTÁ EL CAMBIO! ---
        // En lugar de procesar y crear un Excel, mostramos el texto.
        
        statusDiv.textContent = '¡Proceso completado!';
        
        // 1. Poner el texto extraído en el textarea
        resultText.value = text;
        
        // 2. Mostrar el contenedor de resultados
        resultContainer.classList.remove('hidden');

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

// --- ¡NUEVA! Lógica del botón de Copiar ---
copyButton.addEventListener('click', () => {
    // Seleccionar el texto dentro del textarea
    resultText.select();
    resultText.setSelectionRange(0, 99999); // Para compatibilidad con móviles

    // Usar la API del Portapapeles del navegador (moderna y segura)
    navigator.clipboard.writeText(resultText.value).then(() => {
        // Feedback para el usuario
        const originalText = copyButton.textContent;
        copyButton.textContent = '¡Copiado!';
        setTimeout(() => {
            copyButton.textContent = originalText;
        }, 1500); // Volver al texto original después de 1.5 segundos
    }).catch(err => {
        console.error('Error al copiar el texto: ', err);
        alert('No se pudo copiar el texto. Por favor, hazlo manualmente.');
    });
});

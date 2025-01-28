
# Immersive Relaxation Hub (没入型リラクゼーションハブ)

Immersive Relaxation Hub es una aplicación diseñada para analizar y visualizar datos EEG en tiempo real, mientras evalúa índices de relajación a través de un carrusel de videos. Esta herramienta utiliza gráficas modernas y topomapas para ofrecer una experiencia visual y práctica para el análisis de datos cerebrales.

---

## **Características**
- **Carrusel de Videos**: Evalúa el índice de relajación durante la reproducción de videos.
- **Gráfica de Líneas Reactiva**: Visualiza el progreso de los índices de relajación en tiempo real.
- **Topomap EEG**: Muestra la actividad cerebral promedio en un mapa topográfico.
- **Tabla de Resultados**: Muestra los valores promedio de relajación para cada video en el carrusel.
- **Integración con LSL (Lab Streaming Layer)**: Procesa datos EEG en tiempo real desde el stream `AURA_Filtered`.

---

## **Requisitos**
- Python 3.8 o superior
- Librerías necesarias (instalar con `requirements.txt`)

---

## **Instalación**
1. Clona este repositorio:
   ```bash
   git clone https://github.com/tu-repositorio/immersive-relaxation-hub.git
   cd immersive-relaxation-hub
   ```

2. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```

---

## **Uso**
1. Asegúrate de tener configurado el stream `AURA_Filtered` para recibir datos EEG.
2. Ejecuta el programa:
   ```bash
   python gui.py
   ```
3. **Funciones principales**:
   - **Launch Programs**: Inicia los programas externos necesarios para la adquisición de datos (`Aura.exe` y `ZenSync.exe`).
   - **Start Carrusel**: Inicia el carrusel de videos, limpia los datos anteriores y actualiza las gráficas y el topomap en tiempo real.
   - **Close**: Cierra la aplicación y detiene los programas externos.

---

## **Estructura del Proyecto**
```
immersive-relaxation-hub/
├── gui.py               # Código principal de la interfaz gráfica
├── requirements.txt     # Dependencias del proyecto
├── README.md            # Este archivo
└── assets/
    └── logo_expo2025.png # Logo utilizado en la interfaz
```

---

## **Tecnologías**
- **PyQt5**: Para la interfaz gráfica.
- **Matplotlib**: Para la visualización de gráficas.
- **MNE**: Para el procesamiento de datos EEG y creación de topomapas.
- **pylsl**: Para la integración con Lab Streaming Layer (LSL).
- **Scipy**: Para el procesamiento de señales.

---

## **Capturas de Pantalla**
### **Pantalla Principal**
![Interfaz Principal](assets/interfaz_principal.png)

---

## **Licencia**
Este proyecto se encuentra bajo la licencia MIT. Consulta el archivo `LICENSE` para más detalles.

---

## **Autores**
- **Edgar** - Desarrollo e integración de las funcionalidades.

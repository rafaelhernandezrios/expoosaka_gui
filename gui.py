import sys
import numpy as np
import subprocess
import sqlite3
import datetime
import uuid
import webbrowser
import os

import matplotlib
matplotlib.use("Qt5Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QWidget, QProgressBar, QTableWidget, QTableWidgetItem,
    QFrame, QLineEdit, QSpinBox
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap, QColor

import mne
from pylsl import StreamInfo, StreamOutlet, StreamInlet, resolve_stream
from scipy.signal import welch, butter, filtfilt

###############################################################################
# IMPORTA TU FUNCIÓN DE QR (asegúrate de adaptar la ruta / import):
###############################################################################
# from qr_generator import generate_session_qr
# Para el ejemplo, simulamos la función:
def generate_session_qr(session_id):
    """Genera un QR simple con la URL del survey."""
    try:
        import qrcode
        
        # Asegurar que existe el directorio qr_codes
        if not os.path.exists('qr_codes'):
            os.makedirs('qr_codes')
            
        # URL del servidor local con el ID de sesión
        url = f"http://localhost:5000/survey/{session_id}"
        
        # Genera el QR
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(url)
        qr.make(fit=True)
        
        # Crea la imagen
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Guarda en la carpeta qr_codes
        qr_path = f"qr_codes/qr_{session_id}.png"
        qr_img.save(qr_path)
        return qr_path
    except Exception as e:
        print(f"Error generating QR: {e}")
        return None

###############################################################################
# CONFIGURACIONES GLOBALES
###############################################################################
FS = 250
BUFFER_SIZE = 100

LOWCUT = 1.0
HIGHCUT = 50.0
ORDER = 5

###############################################################################
# FUNCIONES DE FILTRO Y PSD
###############################################################################
def butter_bandpass(lowcut, highcut, fs, order=5):
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    b, a = butter(order, [low, high], btype='band')
    return b, a

def butter_bandpass_filter(data, lowcut, highcut, fs, order=5):
    b, a = butter_bandpass(lowcut, highcut, fs, order=order)
    # Evita filtrar si no hay datos suficientes
    if len(data) < max(len(b), len(a)) * 3:
        raise ValueError("Not enough data to apply filter. Accumulate more samples.")
    y = filtfilt(b, a, data, axis=0)
    return y

def calcular_psd(data, fs=250, nperseg=250):
    from scipy.signal import welch
    psd_values = []
    for ch in range(data.shape[1]):
        freqs, psd = welch(data[:, ch], fs, nperseg=nperseg)
        delta = np.mean(psd[(freqs>=1) & (freqs<4)])
        theta = np.mean(psd[(freqs>=4) & (freqs<8)])
        alpha = np.mean(psd[(freqs>=8) & (freqs<13)])
        beta  = np.mean(psd[(freqs>=13) & (freqs<30)])
        gamma = np.mean(psd[(freqs>=30) & (freqs<=100)])
        psd_values += [delta, theta, alpha, beta, gamma]
    return psd_values

def calcular_indice_relajacion(psd_values):
    if len(psd_values) < 5:
        return 0
    theta = psd_values[1]
    alpha = psd_values[2]
    if alpha == 0:
        return 0
    return theta / alpha

###############################################################################
# STREAM DE TRIGGERS
###############################################################################
info_trig = StreamInfo('neuro_vr_triggers', 'triggers', 1, 0, 'string', 'myuid43536')
trigger_outlet = StreamOutlet(info_trig)

###############################################################################
# VISUALIZATION THREAD
###############################################################################
class VisualizationThread(QThread):
    topomap_update = pyqtSignal(np.ndarray)
    
    def __init__(self):
        super().__init__()
        self.running = True
        self.data = None
        
    def update_data(self, new_data):
        self.data = new_data
        
    def run(self):
        while self.running:
            if self.data is not None:
                self.topomap_update.emit(self.data)
            self.msleep(500)  # 500ms

    def stop(self):
        self.running = False

###############################################################################
# TOPOMAP WIDGET
###############################################################################
class TopomapWidget(FigureCanvas):
    def __init__(self, parent=None, num_channels=8):
        self.num_channels = num_channels
        self.eeg_channels = ["F3", "Fz", "F4", "C3", "C4", "P3", "Pz", "P4"][:self.num_channels]
        ch_types = ["eeg"] * self.num_channels
        self.info = mne.create_info(ch_names=self.eeg_channels, sfreq=FS, ch_types=ch_types)
        montage = mne.channels.make_standard_montage('standard_1020')
        self.info.set_montage(montage)

        self.data = np.zeros((self.num_channels, 1))
        self.fig, self.ax = plt.subplots(figsize=(5, 5))
        super().__init__(self.fig)
        self.setParent(parent)
        self.draw_topomap(self.data)

    def draw_topomap(self, data_array):
        self.ax.clear()
        evoked = mne.EvokedArray(data_array, self.info, tmin=0)
        evoked.plot_topomap(times=[0], axes=self.ax, time_format="",
                            cmap="Spectral_r", colorbar=False, show=False)
        self.ax.set_title("EEG Topomap")
        self.draw()

    def update_data(self, ch_values):
        arr = np.array(ch_values).reshape(self.num_channels, 1)
        self.draw_topomap(arr)

###############################################################################
# HILO CARRUSEL (ZenSyncThread)
###############################################################################
class ZenSyncThread(QThread):
    status_message = pyqtSignal(str)
    progress_update = pyqtSignal(int)
    partial_result = pyqtSignal(int, float)
    final_results = pyqtSignal(list, int)
    topomap_data = pyqtSignal(list)
    
    # Configuración de duraciones de videos
    DURACION_VIDEOS_EXTREMOS = 5  # Duración de videos 1 y 7
    DURACION_VIDEOS_CENTRALES = 8  # Duración de videos 2-6
    DURACION_VIDEO_GANADOR = 5     # Duración para reproducir el video ganador
    PAUSA_ENTRE_VIDEOS = 0.25       # Pausa entre videos (segundos)
    
    def __init__(self, num_channels=8):
        super().__init__()
        self.running = True
        self.buffer = []
        self.videos_avg = [0] * 7
        self.winner_index = -1
        self.num_channels = num_channels
        # Añadir un contador de seguridad para evitar bucles infinitos
        self.safety_counter = 0
        self.max_safety_count = 10000  # Límite de seguridad

    def stop(self):
        """Pide que el hilo se detenga sin bloquear."""
        self.running = False
        # No llamamos a wait() aquí para evitar bloquear el hilo principal

    def run(self):
        try:
            self.status_message.emit("[ZenSync] Buscando stream 'AURA_Filtered'...")
            
            # Configuración de simulación
            use_simulation = False  # Cambiar a True si se quiere usar simulación
            
            # Asegurar que el trigger_outlet esté disponible
            try:
                # Verificar si trigger_outlet ya está definido globalmente
                global trigger_outlet
                if 'trigger_outlet' not in globals() or trigger_outlet is None:
                    self.status_message.emit("[ZenSync] Creando nuevo trigger outlet...")
                    # Crear un nuevo StreamOutlet para enviar triggers
                    info = StreamInfo('ZenSync_Triggers', 'Markers', 1, 0, 'string', 'trigger_id')
                    trigger_outlet = StreamOutlet(info)
                
                # Probar el trigger outlet
                trigger_outlet.push_sample(["ZenSync_Start"])
                self.status_message.emit("[ZenSync] Trigger outlet configurado correctamente")
            except Exception as e:
                self.status_message.emit(f"[ZenSync] Error configurando trigger outlet: {str(e)}")
                # Crear un outlet simulado si hay error
                class DummyOutlet:
                    def push_sample(self, sample):
                        print(f"[TRIGGER SIMULADO]: {sample[0]}")
                
                trigger_outlet = DummyOutlet()
            
            # Variable para controlar si se encontró un stream real
            stream_found = False
            
            if use_simulation:
                self.status_message.emit("[ZenSync] MODO SIMULACIÓN ACTIVADO")
                # Crear un stream simulado
                class SimulatedInlet:
                    def pull_sample(self, timeout=0.0):
                        import time
                        import random
                        time.sleep(0.001)  # Pequeña pausa para simular latencia
                        return [random.random() for _ in range(8)], 0
                
                streams = True
                inlet = SimulatedInlet()
                self.status_message.emit("[ZenSync] Stream simulado creado correctamente")
                stream_found = True
            else:
                # Implementar un timeout manual en lugar de usar el parámetro timeout
                start_time = datetime.datetime.now()
                streams = None
                timeout_seconds = 5.0  # 5 segundos de timeout
                
                # Intentar encontrar el stream con un timeout manual
                while (datetime.datetime.now() - start_time).total_seconds() < timeout_seconds and self.running:
                    try:
                        streams = resolve_stream('name', 'AURA_Filtered')
                        if streams:
                            self.status_message.emit("[ZenSync] Stream 'AURA_Filtered' encontrado.")
                            stream_found = True
                            break
                    except Exception as e:
                        self.status_message.emit(f"[ZenSync] Error buscando stream: {str(e)}")
                    self.msleep(100)  # Pequeña pausa para no saturar la CPU
            
                if not streams:
                    self.status_message.emit("[ZenSync] ERROR: 'AURA_Filtered' not found after timeout.")
                    self.status_message.emit("[ZenSync] Para usar simulación, establezca use_simulation = True")
                    self.running = False
                    # Emitir señal de finalización con datos vacíos para desbloquear la interfaz
                    self.final_results.emit([0] * 7, -1)
                    return
                    
                self.status_message.emit("[ZenSync] Conectando a 'AURA_Filtered'...")
                try:
                    inlet = StreamInlet(streams[0])
                    self.status_message.emit("[ZenSync] Conectado a 'AURA_Filtered'.")
                except Exception as e:
                    self.status_message.emit(f"[ZenSync] Error conectando al stream: {str(e)}")
                    self.running = False
                    self.final_results.emit([0] * 7, -1)
                    return
            
            # Verificación explícita: si no estamos en simulación y no se encontró stream, salir
            if not use_simulation and not stream_found:
                self.status_message.emit("[ZenSync] No se encontró stream real y la simulación está desactivada. Saliendo.")
                self.running = False
                self.final_results.emit([0] * 7, -1)
                return
            
            # A partir de aquí, continúa el código normal...
            max_avg = -1
            max_idx = -1

            # 7 videos: 0..6
            for i in range(7):
                if not self.running:
                    break  # Cortar si se pidió stop

                # Duración distinta para el primer y último video
                dur = self.DURACION_VIDEOS_EXTREMOS if i in [0, 6] else self.DURACION_VIDEOS_CENTRALES
                self.status_message.emit(f"[ZenSync] Configurando video {i+1} con duración {dur}s")

                # Lanzar triggers - SIEMPRE, incluso en simulación
                try:
                    # Enviar trigger de inicio de video
                    trigger_outlet.push_sample([f"Start_video_{i+1}"])
                    self.status_message.emit(f"[ZenSync] Starting video {i+1} - Trigger enviado")

                    # fadein
                    trigger_outlet.push_sample(["fadein"])
                    self.status_message.emit("[ZenSync] Trigger fadein enviado")
                except Exception as e:
                    self.status_message.emit(f"[ZenSync] Error en trigger: {str(e)}")
                    # Continuar a pesar del error en trigger

                start_time = datetime.datetime.now()
                eng_values = []
                self.safety_counter = 0  # Reiniciar contador de seguridad

                # Eliminar el límite de muestras máximas para asegurar que se respete la duración
                # max_samples = 100  # Eliminado
                sample_count = 0

                # Bucle principal de procesamiento de datos
                while self.running:
                    # Verificar contador de seguridad
                    self.safety_counter += 1
                    if self.safety_counter > self.max_safety_count:
                        self.status_message.emit(f"[ZenSync] ¡ALERTA! Contador de seguridad excedido en video {i+1}. Forzando salida.")
                        break

                    # Verificar tiempo transcurrido - SOLO usar el tiempo como criterio de salida
                    elapsed = (datetime.datetime.now() - start_time).total_seconds()
                    if elapsed >= dur:
                        self.status_message.emit(f"[ZenSync] Video {i+1} completado: {elapsed:.1f}s / {sample_count} muestras")
                        break

                    try:
                        # Usar timeout corto para pull_sample para evitar bloqueos
                        sample, _ = inlet.pull_sample(timeout=0.01)
                        sample_count += 1
                        
                        if sample:
                            # Limitar el tamaño del buffer para evitar problemas de memoria
                            if len(self.buffer) >= BUFFER_SIZE * 2:
                                self.buffer = self.buffer[-BUFFER_SIZE:]
                                
                            self.buffer.append(sample[:self.num_channels])
                            # Emitir datos para el topomap solo ocasionalmente
                            if sample_count % 5 == 0:  # Cada 5 muestras
                                self.topomap_data.emit(sample[:self.num_channels])

                        # Procesar solo cada 10 muestras para reducir carga
                        if len(self.buffer) >= BUFFER_SIZE and sample_count % 10 == 0:
                            # En modo simulación, simplemente generamos valores aleatorios
                            if use_simulation:
                                # Simulamos un índice de relajación aleatorio
                                relax_idx = np.random.random() * 2
                                eng_values.append(relax_idx)
                                if sample_count % 20 == 0:  # Reducir mensajes
                                    self.status_message.emit(
                                        f"[ZenSync] Video {i+1}, Muestra {sample_count}, Relax idx: {relax_idx:.3f}"
                                    )
                            else:
                                # Procesamiento real
                                try:
                                    rawdata = np.array(self.buffer)
                                    # desliza el buffer
                                    self.buffer = self.buffer[1:]
                                    filtered = butter_bandpass_filter(rawdata, LOWCUT, HIGHCUT, FS, ORDER)
                                    psd_vals = calcular_psd(filtered, FS, 250)
                                    relax_idx = calcular_indice_relajacion(psd_vals)
                                    eng_values.append(relax_idx)
                                    if sample_count % 20 == 0:  # Reducir mensajes
                                        self.status_message.emit(
                                            f"[ZenSync] Video {i+1}, Muestra {sample_count}, Relax idx: {relax_idx:.3f}"
                                        )
                                except ValueError as ve:
                                    if sample_count % 20 == 0:
                                        self.status_message.emit(f"[ZenSync] Error en procesamiento: {str(ve)}")
                                except Exception as e:
                                    if sample_count % 20 == 0:
                                        self.status_message.emit(f"[ZenSync] Error inesperado: {str(e)}")
                    except Exception as e:
                        self.status_message.emit(f"[ZenSync] Error leyendo muestra: {str(e)}")
                        self.msleep(10)  # Pequeña pausa en caso de error

                    # Pequeña pausa para evitar saturar la CPU
                    self.msleep(10)

                # Calcular promedio del video
                video_avg = np.mean(eng_values) if eng_values else 0
                self.videos_avg[i] = video_avg
                self.status_message.emit(f"[ZenSync] Video {i+1} -> avg: {video_avg:.3f}")

                if i not in [0, 6]:
                    # Solo los videos intermedios participan en la competencia
                    if video_avg > max_avg:
                        max_avg = video_avg
                        max_idx = i
                    # Emitir el resultado parcial para actualizar la interfaz
                    self.partial_result.emit(i, video_avg)
                    # Imprimir información de depuración
                    self.status_message.emit(f"[ZenSync] Comparando: Video {i+1} = {video_avg:.3f}, Max = {max_avg:.3f}, MaxIdx = {max_idx+1 if max_idx >= 0 else -1}")

                # fadeout - SIEMPRE, incluso en simulación
                try:
                    trigger_outlet.push_sample(["fadeout"])
                    self.status_message.emit("[ZenSync] Trigger fadeout enviado")
                except Exception as e:
                    self.status_message.emit(f"[ZenSync] Error en trigger fadeout: {str(e)}")

                # Actualizar barra de progreso
                prog = int(((i+1) / 7) * 100)
                self.progress_update.emit(prog)

                # Pausa entre videos más precisa
                self.status_message.emit(f"[ZenSync] Pausa entre videos ({i+1} -> {i+2 if i<6 else 'fin'})")
                pausa_ms = int(self.PAUSA_ENTRE_VIDEOS * 1000)
                pausa_steps = max(1, pausa_ms // 50)  # Dividir en pasos de 50ms
                for _ in range(pausa_steps):
                    if not self.running:
                        break
                    self.msleep(pausa_ms // pausa_steps)

            if not self.running:
                self.status_message.emit("[ZenSync] Carrusel interrumpido.")
                # Asegurar que la interfaz se desbloquee
                self.final_results.emit([0] * 7, -1)
                return

            # Determina ganador
            self.winner_index = max_idx
            
            # Imprimir información de depuración sobre el ganador
            self.status_message.emit(f"[ZenSync] Determinando ganador: MaxIdx = {max_idx+1 if max_idx >= 0 else -1}, MaxAvg = {max_avg:.3f}")
            
            # Verificar si hay un ganador válido (videos 1-5, índices 0-4)
            if 0 <= max_idx <= 4:
                self.status_message.emit(f"[ZenSync] Ganador determinado: Video {max_idx+1}")
                
                # Lanzar triggers del ganador - SIEMPRE, incluso en simulación
                try:
                    trigger_outlet.push_sample(["fadein"])
                    self.status_message.emit("[ZenSync] Trigger fadein para ganador enviado")
                    
                    trigger_outlet.push_sample([f"Start_video_{max_idx+1}"])
                    self.status_message.emit(f"[ZenSync] Playing winner video: {max_idx+1} - Trigger enviado")
                except Exception as e:
                    self.status_message.emit(f"[ZenSync] Error en trigger ganador: {str(e)}")

                # Espera no bloqueante para el video ganador - usar DURACION_VIDEO_GANADOR
                self.status_message.emit(f"[ZenSync] Reproduciendo video ganador durante {self.DURACION_VIDEO_GANADOR}s")
                start_winner = datetime.datetime.now()
                while self.running and (datetime.datetime.now() - start_winner).total_seconds() < self.DURACION_VIDEO_GANADOR:
                    self.msleep(100)

                try:
                    trigger_outlet.push_sample(["fadeout"])
                    self.status_message.emit("[ZenSync] Trigger fadeout final enviado")
                    
                    for _ in range(5):  # Reducido para pruebas
                        if not self.running:
                            break
                        self.msleep(50)

                    trigger_outlet.push_sample(["end_session:zensync"])
                    self.status_message.emit("[ZenSync] Trigger end_session enviado")
                except Exception as e:
                    self.status_message.emit(f"[ZenSync] Error en trigger final: {str(e)}")
            else:
                self.status_message.emit("[ZenSync] No se determinó un ganador claro.")

            self.status_message.emit("[ZenSync] Carrusel completed.")
            self.final_results.emit(self.videos_avg, self.winner_index)

            # Al final del run, asegurarse de limpiar
            self.running = False
        except Exception as e:
            print(f"Error in ZenSync thread: {e}")
            self.status_message.emit(f"[ZenSync] Error crítico: {str(e)}")
            self.running = False
            # Asegurar que la interfaz se desbloquee incluso en caso de error
            self.final_results.emit([0] * 7, -1)

###############################################################################
# QTHREAD PARA GENERAR QR (ASÍNCRONO)
###############################################################################
class QRGeneratorThread(QThread):
    qr_generated = pyqtSignal(str)

    def __init__(self, session_id, parent=None):
        super().__init__(parent)
        self.session_id = session_id
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        if not self._running:
            return
        try:
            qr_path = generate_session_qr(self.session_id)
            if self._running:
                self.qr_generated.emit(qr_path)
        except Exception as e:
            print(f"[QRGeneratorThread] Error generating QR: {e}")
            # Si hubo error, emite una cadena vacía o None
            if self._running:
                self.qr_generated.emit("")

###############################################################################
# VENTANA QR
###############################################################################
class QRWindow(QMainWindow):
    def __init__(self, session_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Survey QR Code")
        self.setFixedSize(400, 500)
        
        # Establecer la ventana como modal
        self.setWindowModality(Qt.ApplicationModal)
        
        # Widget central
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        try:
            # Título
            title = QLabel("Scan QR Code for Survey")
            title.setAlignment(Qt.AlignCenter)
            title.setFont(QFont("Arial", 14, QFont.Bold))
            
            # QR Code
            self.qr_label = QLabel()
            self.qr_label.setAlignment(Qt.AlignCenter)
            
            # URL
            url = f"http://localhost:5000/survey/{session_id}"
            url_label = QLabel(f"URL: {url}")
            url_label.setAlignment(Qt.AlignCenter)
            url_label.setWordWrap(True)
            
            # Botón para abrir en navegador
            open_button = QPushButton("Open in Browser")
            open_button.clicked.connect(lambda: webbrowser.open(url))
            
            # Agregar widgets al layout
            layout.addWidget(title)
            layout.addWidget(self.qr_label)
            layout.addWidget(url_label)
            layout.addWidget(open_button)
            
            self.setCentralWidget(central)
            
            # Generar y mostrar QR de manera segura
            try:
                qr_path = generate_session_qr(session_id)
                if qr_path and os.path.exists(qr_path):
                    pixmap = QPixmap(qr_path)
                    scaled_pixmap = pixmap.scaled(300, 300, Qt.KeepAspectRatio)
                    self.qr_label.setPixmap(scaled_pixmap)
                    # Eliminar archivo temporal
                    try:
                        os.remove(qr_path)
                    except:
                        print(f"Could not remove temporary QR file: {qr_path}")
                else:
                    self.qr_label.setText("Error generating QR code")
            except Exception as e:
                print(f"Error showing QR: {e}")
                self.qr_label.setText("Error displaying QR code")
                
        except Exception as e:
            print(f"Error in QR window initialization: {e}")
            error_label = QLabel("Error creating QR window")
            layout.addWidget(error_label)

###############################################################################
# VENTANA PRINCIPAL
###############################################################################
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Immersive Relaxation Hub")
        
        self.fig, self.ax = plt.subplots(figsize=(8, 6), facecolor='none')
        self.canvas = FigureCanvas(self.fig)
        self.ax.set_title("ZenSync Progress (Videos 1..5)")
        self.ax.set_xlabel("Video")
        self.ax.set_ylabel("Relax Index")
        self.ax.grid(True)
        self.fig.set_dpi(80)
        
        # Widget Topomap
        self.topomap_widget = TopomapWidget(self)
        
        # Tabla de resultados
        self.table_frame = QFrame()
        table_layout = QVBoxLayout(self.table_frame)
        
        self.table_resultados = QTableWidget()
        self.table_resultados.setRowCount(5)
        self.table_resultados.setColumnCount(2)
        self.table_resultados.setHorizontalHeaderLabels(["Video", "Score"])
        for i in range(5):
            self.table_resultados.setItem(i, 0, QTableWidgetItem(f"Video {i+2}"))
        self.table_resultados.setMinimumWidth(200)
        self.table_resultados.horizontalHeader().setStretchLastSection(True)
        self.table_resultados.setEditTriggers(QTableWidget.NoEditTriggers)
        table_layout.addWidget(self.table_resultados)
        
        # Layout principal
        self.main_layout = QHBoxLayout()
        self.side_panel = self.create_side_panel()
        self.content_area = self.create_main_content()

        self.main_layout.addWidget(self.side_panel)
        self.main_layout.addWidget(self.content_area, stretch=1)

        container = QWidget()
        container.setLayout(self.main_layout)
        self.setCentralWidget(container)

        # Hilo de visualización del Topomap
        self.viz_thread = VisualizationThread()
        self.viz_thread.topomap_update.connect(self.topomap_widget.update_data)
        self.viz_thread.start()
        
        self.partial_data = [0] * 5

        # Hilo del carrusel y del QR
        self.zensync_thread = None
        self.qr_generator_thread = None

        self.session_id = None
        self.qr_window = None

        self.init_db()

    def create_side_panel(self):
        side = QFrame()
        side.setObjectName("SidePanel")
        side.setFixedWidth(300)

        layout = QVBoxLayout(side)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        logo_label = QLabel()
        # Ajusta la ruta al logo que uses
        pixmap = QPixmap("C:/Users/edgar/OneDrive/Escritorio/EXPOOSAKA/expoosaka_gui/src/assets/logo_expo2025.png")
        pixmap = pixmap.scaled(220, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        logo_label.setPixmap(pixmap)
        logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo_label)

        participant_layout = QHBoxLayout()
        participant_label = QLabel("Participant ID:")
        participant_label.setStyleSheet("color: #083d5c;")
        self.participant_lineedit = QLineEdit()
        self.participant_lineedit.setPlaceholderText("Ej. 001")
        participant_layout.addWidget(participant_label)
        participant_layout.addWidget(self.participant_lineedit)
        layout.addLayout(participant_layout)

        channels_layout = QHBoxLayout()
        channels_label = QLabel("N° de Canales:")
        channels_label.setStyleSheet("color: #083d5c;")
        self.channels_spinbox = QSpinBox()
        self.channels_spinbox.setRange(1, 8)
        self.channels_spinbox.setValue(8)
        channels_layout.addWidget(channels_label)
        channels_layout.addWidget(self.channels_spinbox)
        layout.addLayout(channels_layout)

        self.btn_launch_programs = QPushButton("Launch Programs")
        self.btn_launch_programs.clicked.connect(self.on_launch_programs)
        layout.addWidget(self.btn_launch_programs)

        self.btn_start_carrusel = QPushButton("Start Carrusel")
        self.btn_start_carrusel.clicked.connect(self.on_start_carrusel)
        layout.addWidget(self.btn_start_carrusel)

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.on_close)
        layout.addWidget(self.btn_close)

        layout.addStretch(1)
        return side

    def create_main_content(self):
        content = QWidget()
        main_vlayout = QVBoxLayout(content)
        main_vlayout.setContentsMargins(30, 30, 30, 30)
        main_vlayout.setSpacing(25)

        # Título
        title_container = QFrame()
        title_container.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 15px;
                padding: 20px;
            }
        """)
        title_layout = QVBoxLayout(title_container)
        
        self.label_title = QLabel("Immersive Relaxation Hub")
        self.label_title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        self.label_title.setStyleSheet("color: #2c3e50;")
        
        self.label_message = QLabel("Ready to launch programs and start carrusel.")
        self.label_message.setFont(QFont("Segoe UI", 12))
        self.label_message.setStyleSheet("color: #7f8c8d;")
        
        title_layout.addWidget(self.label_title)
        title_layout.addWidget(self.label_message)
        
        main_vlayout.addWidget(title_container)

        # Barra de progreso
        progress_container = QFrame()
        progress_container.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 15px;
                padding: 15px;
            }
        """)
        progress_layout = QVBoxLayout(progress_container)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        main_vlayout.addWidget(progress_container)

        # Contenedor resultados (gráfica y tabla)
        results_container = QFrame()
        results_container.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 15px;
                padding: 20px;
                border: 1px solid #e0e0e0;
            }
        """)
        results_layout = QHBoxLayout(results_container)

        viz_container = QFrame()
        viz_layout = QVBoxLayout(viz_container)

        topomap_container = QFrame()
        topomap_container.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-radius: 10px;
                padding: 10px;
            }
        """)
        topomap_layout = QVBoxLayout(topomap_container)
        self.topomap_widget.setMinimumHeight(200)
        topomap_layout.addWidget(self.topomap_widget)
        
        bottom_container = QFrame()
        bottom_container.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-radius: 10px;
                padding: 10px;
            }
        """)
        bottom_layout = QVBoxLayout(bottom_container)
        self.canvas.setMinimumHeight(250)
        bottom_layout.addWidget(self.canvas)
        
        viz_layout.addWidget(topomap_container, stretch=40)
        viz_layout.addWidget(bottom_container, stretch=60)

        table_container = QFrame()
        table_container.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-radius: 10px;
                padding: 10px;
            }
        """)
        table_layout = QVBoxLayout(table_container)
        table_layout.addWidget(self.table_frame)

        results_layout.addWidget(viz_container, stretch=80)
        results_layout.addWidget(table_container, stretch=20)

        main_vlayout.addWidget(results_container)

        content.setLayout(main_vlayout)
        return content

    def on_launch_programs(self):
        """Lanza los programas Aura y ZenSync sin bloquear la GUI."""
        self.label_message.setText("Launching Programs...")
        try:
            aura_path = "C:/Users/edgar/AppData/Local/Programs/Aura/Aura.exe"
            zensync_path = "C:/Users/edgar/OneDrive/Escritorio/EXPOOSAKA/ZenSync2/ZenSync.exe"
            subprocess.Popen([aura_path])
            subprocess.Popen([zensync_path])
            self.label_message.setText("Programs launched (asynchronously).")
        except Exception as e:
            self.label_message.setText(f"Error launching programs: {e}")

    def on_start_carrusel(self):
        """Inicia el carrusel EEG/ZenSync."""
        # Deshabilita el botón mientras corre el carrusel
        self.btn_start_carrusel.setEnabled(False)
        
        # Si hay un hilo previo, asegurarse de que termine
        if hasattr(self, 'zensync_thread') and self.zensync_thread:
            self.zensync_thread.stop()
            # No esperamos a que termine para evitar bloqueos
            # Simplemente creamos uno nuevo
        
        # Limpia datos anteriores
        for r in range(5):
            for c in range(2):
                item = self.table_resultados.item(r, c)
                if item:
                    item.setBackground(QColor(Qt.white))
                    if c == 1:
                        item.setText("")
        
        # Reinicia el gráfico
        self.ax.clear()
        self.ax.set_title("ZenSync Progress (Videos 1..5)")
        self.ax.set_xlabel("Video")
        self.ax.set_ylabel("Relax Index")
        self.ax.grid(True)
        self.canvas.draw()
        
        # Reinicia los datos parciales
        self.partial_data = [0] * 5
        
        # Genera nuevo session_id
        self.session_id = str(uuid.uuid4())
        
        # Crea y arranca el nuevo hilo
        self.zensync_thread = ZenSyncThread(num_channels=self.channels_spinbox.value())
        self.zensync_thread.status_message.connect(self.actualizar_mensaje)
        self.zensync_thread.progress_update.connect(self.progress_bar.setValue)
        self.zensync_thread.partial_result.connect(self.on_partial_result)
        self.zensync_thread.final_results.connect(self.on_final_results)
        self.zensync_thread.topomap_data.connect(self.topomap_widget.update_data)
        self.zensync_thread.start()
        
        # Mensaje de inicio
        self.label_message.setText("Carrusel iniciado. Procesando datos...")

    def on_close(self):
        """Al cerrar, detenemos hilos y cerramos la app."""
        self.label_message.setText("Closing...")
        
        # Detener hilo de carrusel de manera segura
        if hasattr(self, 'zensync_thread') and self.zensync_thread:
            self.zensync_thread.stop()
        
        # Detener hilo de visualización topomap
        if hasattr(self, 'viz_thread') and self.viz_thread:
            self.viz_thread.stop()
            self.viz_thread.wait()
        
        # Cerrar ventana de QR si está abierta
        if hasattr(self, 'qr_window') and self.qr_window:
            self.qr_window.close()
        
        # Opcional: matar procesos externos
        try:
            subprocess.call(["taskkill", "/IM", "Aura.exe", "/F"])
            subprocess.call(["taskkill", "/IM", "ZenSync.exe", "/F"])
        except Exception as e:
            print(f"Error closing exes: {e}")
        
        self.close()

    def closeEvent(self, event):
        """Intercepta el cierre de la ventana principal."""
        self.on_close()
        event.accept()

    def actualizar_mensaje(self, msg):
        self.label_message.setText(msg)
        print(msg)

    def on_partial_result(self, video_idx, avg_val):
        """Resultado parcial (para videos 2..6 -> i=1..5)."""
        row = video_idx - 1
        if 0 <= row < 5:
            self.table_resultados.setItem(row, 1, QTableWidgetItem(f"{avg_val:.3f}"))
            self.partial_data[row] = avg_val
        self.update_line_chart()

        # Ejemplo: Generamos datos aleatorios para actualizar topomap
        ch_values = np.random.randn(self.topomap_widget.num_channels)
        self.topomap_widget.update_data(ch_values)

    def on_final_results(self, videos_avg, winner_idx):
        """Resultado final del carrusel."""
        try:
            # No intentamos detener el hilo aquí, ya que podría bloquear
            # El hilo debería terminar por sí solo
            
            self.label_message.setText("Carrusel completed. Showing results...")
            
            # Imprimir información de depuración
            print(f"Final results: winner_idx={winner_idx}, videos_avg={videos_avg}")

            # Actualiza la tabla con promedios y marca el ganador
            for i in range(1, 6):
                row = i - 1
                val = videos_avg[i] if i < len(videos_avg) else 0.0
                self.table_resultados.setItem(row, 1, QTableWidgetItem(f"{val:.3f}"))
                self.partial_data[row] = val

            # Si hay un ganador válido (videos 1-5, índices 0-4)
            if 0 <= winner_idx <= 4:
                # Marca el ganador en la tabla
                row_gan = winner_idx
                for col in range(2):
                    item = self.table_resultados.item(row_gan, col)
                    if item:
                        item.setBackground(Qt.yellow)

                # Actualiza el gráfico
                self.update_line_chart(final_winner=winner_idx+1)
                self.label_message.setText(
                    f"Winner: Video {winner_idx+1}, Score={videos_avg[winner_idx]:.3f}"
                )

                # Guarda resultados en BD
                try:
                    self.save_scores_to_db(videos_avg, winner_idx)
                except Exception as db_error:
                    print(f"Error saving to database: {db_error}")
                    self.label_message.setText(f"Error saving to database: {str(db_error)}")

                # Genera el QR y lanza el visor después de que el hilo haya terminado
                # Usar un timer más largo para evitar problemas
                QTimer.singleShot(1000, lambda: self.show_qr_delayed(self.session_id))

            else:
                self.update_line_chart(final_winner=-1)
                self.label_message.setText("No clear winner.")
                print(f"No clear winner. winner_idx={winner_idx}")

            # Habilita el botón de inicio para permitir nuevos experimentos
            self.btn_start_carrusel.setEnabled(True)

        except Exception as e:
            print(f"Error in on_final_results: {e}")
            self.label_message.setText(f"Error processing results: {str(e)}")
            # Asegurar que el botón se habilite incluso en caso de error
            self.btn_start_carrusel.setEnabled(True)

    def update_line_chart(self, final_winner=-1):
        """Actualiza el gráfico de líneas con los datos parciales."""
        try:
            self.ax.clear()
            x = np.array([1, 2, 3, 4, 5])
            y = np.array(self.partial_data)

            # Imprimir información de depuración
            print(f"Updating chart: final_winner={final_winner}, data={self.partial_data}")

            self.ax.plot(
                x, y,
                marker='o', linewidth=2, color='royalblue', alpha=0.9,
                label='Relax Index'
            )
            self.ax.fill_between(x, y, color='royalblue', alpha=0.2)

            if final_winner in [1, 2, 3, 4, 5]:
                wx = final_winner
                wy = self.partial_data[wx - 1]
                self.ax.scatter(wx, wy, s=140, c='red', marker='*', label='Winner')
                print(f"Marking winner in chart: x={wx}, y={wy}")

            self.ax.set_title("ZenSync Progress (Videos 1..5)")
            self.ax.set_xlabel("Video")
            self.ax.set_ylabel("Relax Index")
            self.ax.grid(True)
            self.ax.legend()
            self.canvas.draw()
        except Exception as e:
            print(f"Error in update_line_chart: {e}")

    def init_db(self):
        conn = sqlite3.connect("scores.db")
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                participant_id TEXT,
                timestamp TEXT,
                score_video2 REAL,
                score_video3 REAL,
                score_video4 REAL,
                score_video5 REAL,
                score_video6 REAL,
                winner_video INTEGER
            )
        """)
        conn.commit()
        conn.close()

    def save_scores_to_db(self, videos_avg, winner_idx):
        participant_id = self.participant_lineedit.text().strip()
        if not participant_id:
            participant_id = "unknown"
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        scores = videos_avg[1:6]  # video2..video6
        winner_video = winner_idx + 1 if winner_idx != -1 else None

        conn = sqlite3.connect("scores.db")
        c = conn.cursor()
        c.execute("""
            INSERT INTO scores (participant_id, timestamp, score_video2, score_video3, score_video4, score_video5, score_video6, winner_video)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            participant_id, timestamp,
            scores[0], scores[1], scores[2], scores[3], scores[4],
            winner_video
        ))
        conn.commit()
        conn.close()
        print(f"Scores saved for participant {participant_id} at {timestamp}.")

    def show_qr_delayed(self, session_id):
        """Muestra el QR después de un pequeño delay para evitar bloqueos."""
        try:
            self.label_message.setText("Generating QR code...")
            
            # Genera el QR en un hilo separado para evitar bloqueos
            if not hasattr(self, 'qr_thread') or not self.qr_thread.isRunning():
                self.qr_thread = QRGeneratorThread(session_id, self)
                self.qr_thread.qr_generated.connect(self.on_qr_generated)
                self.qr_thread.start()
            else:
                print("QR generator thread already running")
                self.label_message.setText("QR generator already running")
        except Exception as e:
            print(f"Error in show_qr_delayed: {e}")
            self.label_message.setText(f"Error preparing QR: {str(e)}")
            
    def on_qr_generated(self, qr_path):
        """Callback cuando el QR ha sido generado."""
        try:
            if qr_path:
                self.label_message.setText("QR code generated. Launching viewer...")
                # Lanza el visor de QR como proceso separado
                subprocess.Popen([sys.executable, "qr_viewer.py", self.session_id])
            else:
                print("Failed to generate QR code")
                self.label_message.setText("Error generating QR code")
        except Exception as e:
            print(f"Error in on_qr_generated: {e}")
            self.label_message.setText(f"Error launching QR viewer: {str(e)}")

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    window.setWindowState(window.windowState() | Qt.WindowMaximized)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

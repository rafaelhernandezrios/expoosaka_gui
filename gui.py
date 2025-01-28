import sys
import time
import numpy as np
import subprocess

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QWidget, QProgressBar, QTableWidget, QTableWidgetItem,
    QFrame
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont, QPixmap, QColor

import matplotlib
matplotlib.use("Qt5Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

import mne
from pylsl import StreamInfo, StreamOutlet, StreamInlet, resolve_stream
from scipy.signal import welch, butter, filtfilt

###############################################################################
# CONFIGURACIONES GLOBALES
###############################################################################
FS = 250
NUM_CHANNELS = 8
SCALE_FACTOR_EEG = (4500000)/24/(2**23-1)
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
    if len(data) < max(len(b), len(a)) * 3:
        raise ValueError("Not enough data to apply filter. Accumulate more samples.")
    y = filtfilt(b, a, data, axis=0)
    return y

def calcular_psd(data, fs=250, nperseg=250):
    psd_values = []
    for ch in range(data.shape[1]):
        freqs, psd = welch(data[:, ch], fs, nperseg=nperseg)
        delta = np.mean(psd[(freqs>=1)&(freqs<4)])
        theta = np.mean(psd[(freqs>=4)&(freqs<8)])
        alpha = np.mean(psd[(freqs>=8)&(freqs<13)])
        beta  = np.mean(psd[(freqs>=13)&(freqs<30)])
        gamma = np.mean(psd[(freqs>=30)&(freqs<=100)])
        psd_values += [delta,theta,alpha,beta,gamma]
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
# TOPOMAP WIDGET
###############################################################################
class TopomapWidget(FigureCanvas):
    def __init__(self, parent=None):
        self.fig, self.ax = plt.subplots(figsize=(5,5))  # más grande
        super().__init__(self.fig)
        self.setParent(parent)

        self.eeg_channels = ["F3","Fz","F4","C3","C4","P3","Pz","P4"]
        ch_types = ["eeg"]*8
        self.info = mne.create_info(ch_names=self.eeg_channels, sfreq=FS, ch_types=ch_types)
        montage = mne.channels.make_standard_montage('standard_1020')
        self.info.set_montage(montage)

        self.data = np.zeros((8,1))
        self.draw_topomap(self.data)

    def draw_topomap(self, data_array):
        self.ax.clear()
        evoked = mne.EvokedArray(data_array, self.info, tmin=0)
        evoked.plot_topomap(times=[0], axes=self.ax, time_format="", cmap="Spectral_r",
                            colorbar=False, show=False)
        self.ax.set_title("EEG Topomap")
        self.draw()

    def update_data(self, ch_values):
        arr = np.array(ch_values).reshape(8,1)
        self.draw_topomap(arr)

###############################################################################
# HILO CARRUSEL (ZenSyncThread)
###############################################################################
class ZenSyncThread(QThread):
    status_message = pyqtSignal(str)
    progress_update = pyqtSignal(int)

    partial_result = pyqtSignal(int, float)  
    final_results = pyqtSignal(list, int)  

    def __init__(self):
        super().__init__()
        self.running = True
        self.buffer = []
        self.videos_avg = [0]*7
        self.winner_index = -1

    def run(self):
        try:
            streams = resolve_stream('name', 'AURA_Filtered')
            if not streams:
                self.status_message.emit("[ZenSync] 'AURA_Filtered' not found. Exiting.")
                return
            inlet = StreamInlet(streams[0])
            self.status_message.emit("[ZenSync] Connected to 'AURA_Filtered'.")

            max_avg = -1
            max_idx = -1

            for i in range(7):
                if i in [0,6]:
                    dur = 5
                else:
                    dur = 8

                trigger_outlet.push_sample([f"Start_video_{i+1}"])
                self.status_message.emit(f"[ZenSync] Starting video {i+1}")
                time.sleep(1)
                trigger_outlet.push_sample(["fadein"])

                start_time = time.time()
                eng_values = []

                while (time.time() - start_time) < dur and self.running:
                    sample, _ = inlet.pull_sample(timeout=0.01)
                    if sample:
                        self.buffer.append(sample[:NUM_CHANNELS])
                    if len(self.buffer) >= BUFFER_SIZE:
                        rawdata = np.array(self.buffer)
                        self.buffer = self.buffer[1:]
                        try:
                            filtered = butter_bandpass_filter(rawdata, LOWCUT, HIGHCUT, FS, ORDER)
                            psd_vals = calcular_psd(filtered, FS, 250)
                            relax_idx = calcular_indice_relajacion(psd_vals)
                            eng_values.append(relax_idx)
                            self.status_message.emit(f"[ZenSync] Video {i+1}, Relax idx: {relax_idx:.3f}")
                        except ValueError:
                            pass

                video_avg = np.mean(eng_values) if eng_values else 0
                self.videos_avg[i] = video_avg
                self.status_message.emit(f"[ZenSync] Video {i+1} -> avg: {video_avg:.3f}")

                if i not in [0,6]:
                    if video_avg > max_avg:
                        max_avg = video_avg
                        max_idx = i
                    self.partial_result.emit(i, video_avg)

                trigger_outlet.push_sample(["fadeout"])
                time.sleep(2)

                prog = int(((i+1)/7)*100)
                self.progress_update.emit(prog)

            self.winner_index = max_idx

            if max_idx == -1:
                self.status_message.emit("[ZenSync] No winner determined.")
            else:
                trigger_outlet.push_sample(["fadein"])
                trigger_outlet.push_sample([f"Start_video_{max_idx+1}"])
                self.status_message.emit(f"[ZenSync] Playing winner video: {max_idx+1}")
                time.sleep(5)
                trigger_outlet.push_sample(["fadeout"])
                time.sleep(2)
                trigger_outlet.push_sample(["end_session:zensync"])

            self.status_message.emit("[ZenSync] Carrusel completed.")
            self.final_results.emit(self.videos_avg, self.winner_index)

        except Exception as e:
            self.status_message.emit(f"[ZenSync] Error: {e}")

    def stop(self):
        self.running = False

###############################################################################
# FUNCIÓN INICIAR PROGRAMAS
###############################################################################
def iniciar_programas():
    try:
        aura_path = "C:/Users/edgar/AppData/Local/Programs/Aura/Aura.exe"
        zensync_path = "C:/Users/edgar/OneDrive/Escritorio/EXPOOSAKA/ZenSync2/ZenSync.exe"
        subprocess.Popen([aura_path], shell=True)
        time.sleep(2)
        subprocess.Popen([zensync_path], shell=True)
        time.sleep(2)
        print("[GUI] Programs launched.")
    except Exception as e:
        print(f"[GUI] Error launching programs: {e}")

###############################################################################
# GUI
###############################################################################
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Immersive Relaxation Hub")
        
        # 1) Abrimos la ventana maximizada
        # (lo haremos después del constructor en main(), para asegurar que tome efecto)
        
        # Layout principal (horizontal)
        self.main_layout = QHBoxLayout()

        # Panel lateral
        self.side_panel = self.create_side_panel()
        # Contenido principal
        self.content_area = self.create_main_content()

        self.main_layout.addWidget(self.side_panel)
        self.main_layout.addWidget(self.content_area, stretch=1)

        container = QWidget()
        container.setLayout(self.main_layout)
        self.setCentralWidget(container)

        # Parcial promedios
        self.partial_data = [0]*5

        # Thread
        self.zensync_thread = None

        # Estilos
        self.setStyleSheet("""
            QWidget {
                background-color: #f0f0f0;
            }
            QFrame#SidePanel {
                background-color: #0f728f;
            }
            QLabel, QPushButton {
                color: #ffffff;
            }
            QPushButton {
                background-color: rgba(255,255,255,0.1);
                border: none;
                text-align: left;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: rgba(255,255,255,0.2);
            }
            QProgressBar {
                border: 1px solid #bbb;
                background: white;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #ff6f00;
                width: 10px;
            }
            QTableWidget {
                background-color: white;
                selection-background-color: #ffcc80;
            }
        """)

    def create_side_panel(self):
        side = QFrame()
        side.setObjectName("SidePanel")
        side.setFixedWidth(300)

        layout = QVBoxLayout(side)
        layout.setContentsMargins(20,20,20,20)
        layout.setSpacing(20)

        # Logo
        logo_label = QLabel()
        pixmap = QPixmap("C:/Users/edgar/OneDrive/Escritorio/EXPOOSAKA/frontend/src/assets/logo_expo2025.png")
        pixmap = pixmap.scaled(220,150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        logo_label.setPixmap(pixmap)
        logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo_label)

        # Botones
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
        main_vlayout.setContentsMargins(20,20,20,20)
        main_vlayout.setSpacing(20)

        # Título
        self.label_title = QLabel("Immersive Relaxation Hub")
        self.label_title.setFont(QFont("Arial", 16))
        self.label_title.setStyleSheet("color: #083d5c;")
        main_vlayout.addWidget(self.label_title)

        # Mensaje
        self.label_message = QLabel("Ready to launch programs and start carrusel.")
        self.label_message.setFont(QFont("Arial", 12))
        self.label_message.setStyleSheet("color: #083d5c;")
        main_vlayout.addWidget(self.label_message)

        # Barra de progreso
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        main_vlayout.addWidget(self.progress_bar)

        # Layout horizontal con la tabla a la izquierda y las gráficas a la derecha
        hbox = QHBoxLayout()

        # Sección Izquierda: Tabla
        self.table_frame = QFrame()
        self.table_frame.setMinimumSize(600,200)
        table_layout = QVBoxLayout(self.table_frame)
        table_layout.setContentsMargins(0,0,0,0)
        table_layout.setSpacing(5)

        self.table_resultados = QTableWidget()
        self.table_resultados.setColumnCount(2)
        self.table_resultados.setRowCount(5)
        self.table_resultados.setHorizontalHeaderLabels(["Video", "Relax Index"])
        self.table_resultados.horizontalHeader().setStretchLastSection(True)
        for r in range(5):
            i = r+1
            vid_item = QTableWidgetItem(f"Video {i+1}")
            self.table_resultados.setItem(r, 0, vid_item)

        table_layout.addWidget(self.table_resultados)
        hbox.addWidget(self.table_frame, stretch=0)

        # Sección Derecha: Gráfica de promedios + Topomap en un QVBox
        right_vbox = QVBoxLayout()
        right_vbox.setSpacing(5)

        # Gráfica promedios
        self.figure, self.ax = plt.subplots(figsize=(7,5))  # más grande
        self.canvas = FigureCanvas(self.figure)
        right_vbox.addWidget(self.canvas)

        # Topomap
        self.topomap_widget = TopomapWidget()
        right_vbox.addWidget(self.topomap_widget)

        hbox.addLayout(right_vbox, stretch=1)
        main_vlayout.addLayout(hbox)

        return content

    def on_launch_programs(self):
        self.label_message.setText("Launching Programs...")
        iniciar_programas()
        self.label_message.setText("Programs launched.")

    def on_start_carrusel(self):
        if self.zensync_thread and self.zensync_thread.isRunning():
            self.label_message.setText("Carrusel in progress. Please wait...")
            return

        # LIMPIAR la tabla Y quitar el fondo amarillo anterior (si existe)
        for r in range(5):
            for c in range(2):
                item = self.table_resultados.item(r, c)
                if item:  # Solo si existe un QTableWidgetItem en esta celda
                    # Eliminar fondo anterior
                    item.setBackground(QColor(Qt.white))
                    # Si es la columna 1 (Relax Index), limpiar el texto
                    if c == 1:
                        item.setText("")
            self.partial_data[r] = 0.0

        # Limpiar gráfica
        self.ax.clear()
        self.ax.set_title("ZenSync Progress (Videos 1..5)")
        self.ax.set_xlabel("Video")
        self.ax.set_ylabel("Relax Index")
        self.ax.grid(True)
        self.canvas.draw()

        # Limpiar topomap
        self.topomap_widget.update_data([0]*8)

        self.progress_bar.setValue(0)
        self.label_message.setText("Starting Carrusel...")

        self.zensync_thread = ZenSyncThread()
        self.zensync_thread.status_message.connect(self.actualizar_mensaje)
        self.zensync_thread.progress_update.connect(self.progress_bar.setValue)
        self.zensync_thread.partial_result.connect(self.on_partial_result)
        self.zensync_thread.final_results.connect(self.on_final_results)

        self.zensync_thread.start()

    def on_close(self):
        self.label_message.setText("Closing...")
        try:
            subprocess.call(["taskkill","/IM","Aura.exe","/F"], shell=True)
            subprocess.call(["taskkill","/IM","ZenSync.exe","/F"], shell=True)
        except Exception as e:
            print(f"Error closing exes: {e}")
        self.close()

    # SEÑALES
    def actualizar_mensaje(self, msg):
        self.label_message.setText(msg)
        print(msg)

    def on_partial_result(self, video_idx, avg_val):
        row = video_idx - 1
        self.table_resultados.setItem(row, 1, QTableWidgetItem(f"{avg_val:.3f}"))
        self.partial_data[row] = avg_val
        self.update_line_chart()

        # DEMO: generamos datos aleatorios para topomap
        ch_values = np.random.randn(8)
        self.topomap_widget.update_data(ch_values)

    def on_final_results(self, videos_avg, winner_idx):
        self.label_message.setText("Carrusel completed. Showing results...")
        for i in range(1,6):
            row = i-1
            val = videos_avg[i]
            self.table_resultados.setItem(row, 1, QTableWidgetItem(f"{val:.3f}"))
            self.partial_data[row] = val

        if 1 <= winner_idx <= 5:
            row_gan = winner_idx-1
            for col in range(2):
                item = self.table_resultados.item(row_gan, col)
                if item:
                    item.setBackground(Qt.yellow)
            self.update_line_chart(final_winner=winner_idx)
            self.label_message.setText(f"Winner: Video {winner_idx+1}, Score={videos_avg[winner_idx]:.3f}")
        else:
            self.update_line_chart(final_winner=-1)
            self.label_message.setText("No clear winner.")

    def update_line_chart(self, final_winner=-1):
        self.ax.clear()
        x = np.array([1,2,3,4,5])
        y = np.array(self.partial_data)

        # Gráfica con área rellena
        line = self.ax.plot(x, y, marker='o', linewidth=2, color='royalblue', alpha=0.9, label='Relax Index')
        self.ax.fill_between(x, y, color='royalblue', alpha=0.2)

        if final_winner in [1,2,3,4,5]:
            wx = final_winner
            wy = self.partial_data[wx-1]
            self.ax.scatter(wx, wy, s=140, c='red', marker='*', label='Winner')

        self.ax.set_title("ZenSync Progress (Videos 1..5)")
        self.ax.set_xlabel("Video")
        self.ax.set_ylabel("Relax Index")
        self.ax.grid(True)
        self.ax.legend()
        self.canvas.draw()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()  
    # 2) Forzar ventana maximizada tras show
    window.setWindowState(window.windowState() | Qt.WindowMaximized)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

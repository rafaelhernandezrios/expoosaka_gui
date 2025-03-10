import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, 
                            QPushButton, QFrame, QSizePolicy, QGraphicsDropShadowEffect)
from PyQt5.QtGui import QPixmap, QFont, QPalette, QColor
from PyQt5.QtCore import Qt
import webbrowser
import os

class QRViewer(QMainWindow):
    def __init__(self, session_id):
        super().__init__()
        self.session_id = session_id
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle('Survey QR Code')
        self.setMinimumSize(400, 500)  # Tamaño mínimo para asegurar legibilidad
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f7fa;
            }
            QLabel {
                color: #2c3e50;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 12px;
                border-radius: 6px;
                font-size: 15px;
                min-height: 45px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QFrame {
                background-color: white;
                border-radius: 12px;
            }
        """)
        
        # Widget central
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Contenedor principal (frame blanco) - Ahora con política de tamaño flexible
        container = QFrame()
        container.setObjectName("container")
        container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        container.setStyleSheet("""
            QFrame#container {
                border: 1px solid #e0e0e0;
                background-color: white;
                border-radius: 18px;
            }
        """)
        
        # Añadir efecto de sombra usando QGraphicsDropShadowEffect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 30))  # Color negro con 30% de opacidad
        shadow.setOffset(0, 4)
        container.setGraphicsEffect(shadow)
        
        layout = QVBoxLayout(container)
        layout.setSpacing(25)
        layout.setContentsMargins(30, 40, 30, 40)
        
        # Título
        title = QLabel("Scan QR Code")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Segoe UI", 28, QFont.Bold))
        title.setStyleSheet("color: #2c3e50; margin-bottom: 5px;")
        
        # Subtítulo
        subtitle = QLabel("to complete the survey")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setFont(QFont("Segoe UI", 16))
        subtitle.setStyleSheet("color: #7f8c8d; margin-bottom: 15px;")
        
        # QR Frame - Ahora con política de tamaño flexible
        qr_frame = QFrame()
        qr_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        qr_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 15px;
                padding: 20px;
                border: 2px solid #e6e6e6;
            }
        """)
        qr_layout = QVBoxLayout(qr_frame)
        qr_layout.setContentsMargins(15, 15, 15, 15)
        
        # QR Image - Ahora con política de tamaño flexible
        qr_label = QLabel()
        qr_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        qr_label.setMinimumSize(200, 200)  # Tamaño mínimo para asegurar visibilidad
        qr_path = f"qr_codes/qr_{self.session_id}.png"
        
        if os.path.exists(qr_path):
            try:
                pixmap = QPixmap(qr_path)
                # No escalar a un tamaño fijo, permitir que se adapte
                qr_label.setPixmap(pixmap)
                qr_label.setScaledContents(True)  # Escalar contenido para llenar el label
            except Exception as e:
                print(f"Error loading QR image: {e}")
                qr_label.setText("Error loading QR image")
                qr_label.setStyleSheet("font-size: 16px; color: #e74c3c; padding: 20px;")
        else:
            print(f"QR file not found at: {qr_path}")
            qr_label.setText(f"QR Code not found\nPath: {qr_path}")
            qr_label.setStyleSheet("font-size: 16px; color: #e74c3c; padding: 20px;")
            
        qr_label.setAlignment(Qt.AlignCenter)
        qr_layout.addWidget(qr_label)
        
        # URL Label - Con política de tamaño flexible
        url = f"http://localhost:5000/survey/{self.session_id}"
        url_label = QLabel(f"URL: {url}")
        url_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        url_label.setWordWrap(True)
        url_label.setAlignment(Qt.AlignCenter)
        url_label.setStyleSheet("""
            color: #34495e; 
            padding: 15px; 
            background-color: #f0f2f5; 
            border-radius: 8px;
            border: 1px solid #e0e0e0;
        """)
        url_label.setFont(QFont("Segoe UI", 12))
        
        # Open in Browser Button
        open_btn = QPushButton("Open in Browser")
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 12px;
                border-radius: 6px;
                font-size: 15px;
                min-height: 45px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        open_btn.clicked.connect(lambda: webbrowser.open(url))
        
        # Add widgets to layout
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(qr_frame, 1)  # Dar prioridad de expansión al QR
        layout.addSpacing(15)
        layout.addWidget(url_label)
        layout.addSpacing(10)
        layout.addWidget(open_btn)
        
        main_layout.addWidget(container)
        
        # Ajustar tamaño basado en contenido
        self.adjustSize()
        
        # Centrar la ventana en la pantalla
        self.center()
    
    def center(self):
        """Centra la ventana en la pantalla."""
        screen = QApplication.desktop().screenGeometry()
        size = self.geometry()
        self.move((screen.width() - size.width()) // 2, 
                 (screen.height() - size.height()) // 2)

    def resizeEvent(self, event):
        """Manejar eventos de redimensionamiento para mantener proporciones."""
        super().resizeEvent(event)
        # Podríamos añadir lógica adicional aquí si es necesario

def main():
    app = QApplication(sys.argv)
    if len(sys.argv) > 1:
        session_id = sys.argv[1]
    else:
        session_id = "test_session"
    viewer = QRViewer(session_id)
    viewer.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main() 
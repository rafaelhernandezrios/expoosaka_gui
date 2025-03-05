import qrcode
import os
from datetime import datetime

def generate_session_qr(session_id):
    """Generate QR code for survey URL"""
    survey_url = f"http://localhost:5000/survey/{session_id}"
    return generate_qr_code(survey_url, session_id)

def generate_qr_code(data, filename_base):
    """Generate a QR code for any given data"""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    
    # Generate QR image
    qr_image = qr.make_image(fill_color="black", back_color="white")
    
    # Ensure qr_codes directory exists
    if not os.path.exists('qr_codes'):
        os.makedirs('qr_codes')
    
    # Save QR code with a safe filename
    filename = f"qr_codes/qr_{filename_base}.png"
    qr_image.save(filename)
    return filename
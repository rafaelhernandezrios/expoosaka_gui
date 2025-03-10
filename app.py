from flask import Flask, render_template, request, redirect, url_for
from database import Database
import os

app = Flask(__name__)
db = Database()

# Add shutdown endpoint
def shutdown_server():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()

@app.route('/shutdown')
def shutdown():
    shutdown_server()
    return 'Server shutting down...'

@app.route('/survey/<session_id>')
def survey(session_id):
    return render_template('survey.html', session_id=session_id)

@app.route('/submit_survey', methods=['POST'])
def submit_survey():
    try:
        session_id = request.form.get('session_id')
        if not session_id:
            raise ValueError("Session ID is required")

        user_data = {
            'name': request.form.get('name'),
            'age': request.form.get('age'),
            'gender': request.form.get('gender'),
            'comfort': request.form.get('comfort'),
            'experience': request.form.get('experience'),
            'recommendation': request.form.get('recommendation'),
            'comments': request.form.get('comments')
        }
        
        # Validar datos requeridos
        if not user_data['name']:
            raise ValueError("Name is required")
        
        # Convertir age a entero si existe
        if user_data['age']:
            try:
                user_data['age'] = int(user_data['age'])
            except ValueError:
                raise ValueError("Age must be a number")
        
        # Guardar en MongoDB
        db.save_user_data(session_id, user_data)
        return redirect(url_for('dashboard', session_id=session_id))
    
    except ValueError as ve:
        app.logger.error(f"Validation error: {str(ve)}")
        return render_template('error.html', error=str(ve))
    except Exception as e:
        app.logger.error(f"Error submitting survey: {str(e)}")
        return render_template('error.html', 
                             error="An error occurred while submitting the survey. Please try again.")

@app.route('/dashboard/<session_id>')
def dashboard(session_id):
    try:
        # Obtener datos de MongoDB
        session_data = db.get_session_data(session_id)
        if not session_data:
            session_data = {
                'user_data': None,
                'session_id': session_id
            }
        return render_template('dashboard.html', data=session_data)
    except Exception as e:
        app.logger.error(f"Error in dashboard: {str(e)}")
        return render_template('dashboard.html', 
                             data={'user_data': None, 'error': str(e)})

# Ensure the qr_codes directory exists
if not os.path.exists('qr_codes'):
    os.makedirs('qr_codes')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
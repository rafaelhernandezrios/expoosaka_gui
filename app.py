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
    session_id = request.form['session_id']
    user_data = {
        'name': request.form['name'],
        'email': request.form['email'],
        'gender': request.form['gender'],
        'country': request.form['country'],
        'feedback': {
            'experience': int(request.form['experience']),
            'comfort': int(request.form['comfort']),
            'would_recommend': request.form['would_recommend'] == 'yes'
        }
    }
    
    db.save_user_data(session_id, user_data)
    return redirect(url_for('dashboard', session_id=session_id))

@app.route('/dashboard/<session_id>')
def dashboard(session_id):
    session_data = db.db.sessions.find_one({'session_id': session_id})
    return render_template('dashboard.html', data=session_data)

# Ensure the qr_codes directory exists
if not os.path.exists('qr_codes'):
    os.makedirs('qr_codes')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
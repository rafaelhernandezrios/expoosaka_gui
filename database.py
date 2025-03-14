from pymongo import MongoClient, errors
from datetime import datetime
import uuid
import time
import logging
from urllib.parse import quote_plus

class Database:
    def __init__(self, max_retries=3, retry_delay=1):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.client = None
        self.db = None
        self._connect()

    def _connect(self):
        """Establece la conexión a MongoDB con reintentos"""
        username = quote_plus("erhdez94")
        password = quote_plus("iOhp1kA4b7zWjUST")
        
        # Configuración de conexión con opciones de pool
        connection_string = (
            f"mongodb+srv://{username}:{password}@mirai.77p1r.mongodb.net/"
            "expoosaka?retryWrites=true&w=majority&appName=Mirai"
            "&maxPoolSize=50&waitQueueTimeoutMS=10000&connectTimeoutMS=20000"
        )

        for attempt in range(self.max_retries):
            try:
                if self.client is not None:
                    self.client.close()
                
                self.client = MongoClient(connection_string)
                # Forzar una operación para verificar la conexión
                self.client.admin.command('ping')
                self.db = self.client['expoosaka']
                logging.info("Successfully connected to MongoDB")
                return
            except errors.ServerSelectionTimeoutError as e:
                logging.error(f"Attempt {attempt + 1}/{self.max_retries} failed: {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    raise Exception(f"Failed to connect to MongoDB after {self.max_retries} attempts")

    def _ensure_connection(self):
        """Asegura que la conexión está activa antes de cada operación"""
        try:
            if self.client is None:
                self._connect()
            else:
                # Verificar conexión con timeout
                self.client.admin.command('ping', timeout=5000)
        except Exception as e:
            logging.warning(f"Connection check failed: {str(e)}. Attempting to reconnect...")
            self._connect()

    def save_session(self, videos_avg, winner_idx):
        """Guarda los datos de la sesión con reintentos"""
        for attempt in range(self.max_retries):
            try:
                self._ensure_connection()
                
                # Verificar que videos_avg tenga al menos 5 elementos
                if len(videos_avg) < 5:
                    raise ValueError(f"videos_avg tiene menos de 5 elementos: {videos_avg}")
                
                session_id = str(uuid.uuid4())
                session = {
                    'session_id': session_id,
                    'timestamp': datetime.now(),
                    'scores': {
                        'video2': videos_avg[0],  # Corresponde al primer video de interés
                        'video3': videos_avg[1],
                        'video4': videos_avg[2],
                        'video5': videos_avg[3],
                        'video6': videos_avg[4]   # Corresponde al último video de interés
                    },
                    'winner_video': winner_idx + 1 if winner_idx != -1 else None,
                    'survey_completed': False,
                    'user_data': None
                }
                self.db.sessions.insert_one(session)
                return session_id
            except Exception as e:
                logging.error(f"Attempt {attempt + 1}/{self.max_retries} to save session failed: {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    self._connect()  # Intentar reconectar
                else:
                    raise

    def save_user_data(self, session_id, user_data):
        """Guarda los datos del usuario con reintentos"""
        for attempt in range(self.max_retries):
            try:
                self._ensure_connection()
                result = self.db.sessions.update_one(
                    {'session_id': session_id},
                    {
                        '$set': {
                            'user_data': user_data,
                            'survey_completed': True,
                            'last_updated': datetime.now()
                        }
                    }
                )
                if result.modified_count == 0:
                    raise ValueError(f"No session found with ID: {session_id}")
                return True
            except Exception as e:
                logging.error(f"Attempt {attempt + 1}/{self.max_retries} to save user data failed: {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    self._connect()
                else:
                    raise

    def get_session_data(self, session_id):
        """Obtiene los datos de la sesión con reintentos"""
        for attempt in range(self.max_retries):
            try:
                self._ensure_connection()
                session = self.db.sessions.find_one({'session_id': session_id})
                if session:
                    session['_id'] = str(session['_id'])
                return session
            except Exception as e:
                logging.error(f"Attempt {attempt + 1}/{self.max_retries} to get session data failed: {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    self._connect()
                else:
                    raise

    def __del__(self):
        """Cierra la conexión al destruir la instancia"""
        if self.client:
            try:
                self.client.close()
            except:
                pass 
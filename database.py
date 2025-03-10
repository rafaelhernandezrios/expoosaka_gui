from pymongo import MongoClient
from datetime import datetime
import uuid

class Database:
    def __init__(self):
        self.client = MongoClient('mongodb+srv://erhdez94:iOhp1kA4b7zWjUST@mirai.77p1r.mongodb.net/expoosaka?retryWrites=true&w=majority&appName=Mirai')
        self.db = self.client['expoosaka']
        
    def save_session(self, videos_avg, winner_idx):
        """Saves initial session data and returns session_id"""
        session_id = str(uuid.uuid4())
        session = {
            'session_id': session_id,
            'timestamp': datetime.now(),
            'scores': {
                'video2': videos_avg[1],
                'video3': videos_avg[2],
                'video4': videos_avg[3],
                'video5': videos_avg[4],
                'video6': videos_avg[5]
            },
            'winner_video': winner_idx + 1 if winner_idx != -1 else None,
            'survey_completed': False,
            'user_data': None
        }
        self.db.sessions.insert_one(session)
        return session_id
    
    def save_user_data(self, session_id, user_data):
        """Saves user survey data"""
        self.db.sessions.update_one(
            {'session_id': session_id},
            {
                '$set': {
                    'user_data': user_data,
                    'survey_completed': True
                }
            }
        )
        
    def get_session_data(self, session_id):
        """Retrieves session data including survey responses"""
        session = self.db.sessions.find_one({'session_id': session_id})
        if session:
            # Convertir ObjectId a str para serialización JSON
            session['_id'] = str(session['_id'])
            return session
        return None 
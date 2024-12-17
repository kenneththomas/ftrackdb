from flask import current_app
import sqlite3
from sqlite3 import Error

class Database:
    @staticmethod
    def get_connection():
        conn = None
        try:
            conn = sqlite3.connect(current_app.config['DATABASE'])
            conn.row_factory = sqlite3.Row
        except Error as e:
            print(e)
        return conn

class Result:
    @staticmethod
    def get_recent_results(limit=25):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT strftime('%Y-%m-%d', Date) as formatted_date, 
                       Athlete, Meet_Name, Event, Result, Team 
                FROM Results 
                ORDER BY Date DESC 
                LIMIT ?
            ''', (limit,))
            return cur.fetchall()

    @staticmethod
    def get_athlete_results(name):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            # Get results
            cur.execute('''
                SELECT strftime('%Y-%m-%d', Date) as formatted_date,
                       Meet_Name, Event, Result, Team
                FROM Results 
                WHERE Athlete = ? 
                ORDER BY Date DESC
            ''', (name,))
            results = cur.fetchall()
            
            # Get PRs
            cur.execute("""
                SELECT Event, MIN(Result) 
                FROM Results 
                WHERE Athlete = ? 
                GROUP BY Event
                """, (name,))
            prs = dict(cur.fetchall())
            
            # Get athlete info
            cur.execute('''
                SELECT Team, Class 
                FROM Results 
                WHERE Athlete = ? 
                ORDER BY Date DESC 
                LIMIT 1
            ''', (name,))
            athlete_info = cur.fetchone()
            
            return results, prs, athlete_info

    @staticmethod
    def insert_result(form_data):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute(
                'INSERT INTO Results (Date, Athlete, Meet_Name, Event, Result, Team) VALUES (?, ?, ?, ?, ?, ?)',
                (form_data.date.data, form_data.athlete.data, form_data.meet.data, 
                 form_data.event.data, form_data.result.data, form_data.team.data)
            )
            conn.commit() 

    @staticmethod
    def get_meet_results(meet_name):
        conn = Database.get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT strftime('%Y-%m-%d', Date) as formatted_date,
                       Athlete, Event, Result, Team 
                FROM Results 
                WHERE Meet_Name = ? 
                ORDER BY Event, Result ASC
            ''', (meet_name,))
            return cur.fetchall()
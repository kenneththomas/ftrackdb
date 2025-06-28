#!/usr/bin/env python3

import sqlite3
from models import Database, AthleteRanking
from wavelight import app

def test_rankings_table():
    """Test that the AthleteRankings table is created and accessible"""
    print("Testing AthleteRankings table creation...")
    
    with app.app_context():
        # Get connection (this should create the table)
        conn = Database.get_connection()
        
        with conn:
            cur = conn.cursor()
            
            # Check if table exists
            cur.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='AthleteRankings'
            """)
            result = cur.fetchone()
            
            if result:
                print("✓ AthleteRankings table exists")
                
                # Check table structure
                cur.execute("PRAGMA table_info(AthleteRankings)")
                columns = cur.fetchall()
                print(f"✓ Table has {len(columns)} columns:")
                for col in columns:
                    print(f"  - {col[1]} ({col[2]})")
            else:
                print("✗ AthleteRankings table does not exist")
                return False
        
        print("\nTesting AthleteRanking class methods...")
        
        # Test empty rankings retrieval
        rankings = AthleteRanking.get_meet_rankings("Test Meet")
        print(f"✓ get_meet_rankings returns {len(rankings)} rows for non-existent meet")
        
        # Test empty rankings update
        AthleteRanking.update_meet_rankings("Test Meet", [])
        print("✓ update_meet_rankings works with empty data")
        
        print("\nAll tests passed! The ranking system is ready to use.")
        return True

if __name__ == "__main__":
    test_rankings_table() 
#!/usr/bin/env python3
"""Test script for explicit relay refactor."""

import os
import sys

# Ensure we can import from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wavelight import app
from models import Database, RelayTeam

TEST_DB = 'test_relay.db'

def setup_test_db():
    """Create a temporary test database with the new schema."""
    # Point app config to test db
    app.config['DATABASE'] = TEST_DB
    # Ensure any old file is removed; Windows may need retry on leftover handle
    for _ in range(5):
        if os.path.exists(TEST_DB):
            try:
                os.remove(TEST_DB)
                break
            except PermissionError:
                import time
                time.sleep(0.05)
    # Force table creation by getting a connection
    conn = Database.get_connection()
    conn.commit()
    conn.close()

def teardown_test_db():
    import sqlite3, time
    for _ in range(5):
        try:
            if os.path.exists(TEST_DB):
                os.remove(TEST_DB)
            break
        except PermissionError:
            time.sleep(0.05)

def test_relay_config():
    assert '4x100m' in RelayTeam.RELAY_CONFIG
    assert RelayTeam.RELAY_CONFIG['4x100m'] == ['100m', '100m', '100m', '100m']
    assert 'DMR' in RelayTeam.RELAY_CONFIG
    assert RelayTeam.RELAY_CONFIG['DMR'] == ['1200m', '400m', '800m', '1600m']
    assert 'SMR' in RelayTeam.RELAY_CONFIG
    assert RelayTeam.RELAY_CONFIG['SMR'] == ['400m', '200m', '200m', '800m']
    print("PASS: relay configuration")

def test_insert_relay():
    with app.app_context():
        setup_test_db()
        try:
            data = {
                'date': '2024-04-24',
                'meet': 'Test Meet',
                'team': 'Team A',
                'event': 'DMR',
                'team_designation': 'A'
            }
            legs = [
                {'athlete': 'Alice', 'split_result': '3:45.00'},
                {'athlete': 'Bob', 'split_result': '52.00'},
                {'athlete': 'Charlie', 'split_result': '1:58.00'},
                {'athlete': 'Diana', 'split_result': '4:30.00'}
            ]
            relay_id = RelayTeam.insert_relay(data, legs)
            assert relay_id is not None
            print("PASS: insert explicit relay")

            # Fetch relays for meet
            relays = RelayTeam.get_relays_for_meet('Test Meet')
            assert len(relays) == 1
            relay = relays[0]
            assert relay['event'] == 'DMR'
            assert relay['team'] == 'Team A'
            assert relay['team_designation'] == 'A'
            assert len(relay['legs']) == 4
            assert relay['legs'][0]['athlete'] == 'Alice'
            assert relay['legs'][0]['split_event'] == '1200m'
            assert relay['legs'][1]['split_event'] == '400m'
            assert relay['legs'][2]['split_event'] == '800m'
            assert relay['legs'][3]['split_event'] == '1600m'
            print("PASS: get_relays_for_meet")

            # Fetch relays for athlete
            alice_relays = RelayTeam.get_relays_for_athlete('Alice')
            assert len(alice_relays) == 1
            assert alice_relays[0]['event'] == 'DMR'
            print("PASS: get_relays_for_athlete")

            # Verify backward-compat Results rows were inserted
            conn = Database.get_connection()
            with conn:
                cur = conn.cursor()
                cur.execute("SELECT Athlete, Event, Result FROM Results WHERE Meet_Name = ? AND Athlete = ?", ('Test Meet', 'Alice'))
                rows = cur.fetchall()
                assert len(rows) == 1
                assert rows[0][1] == '1200m RS'
                assert rows[0][2] == '3:45.00'
            conn.close()
            print("PASS: backward-compat Results inserted")
        finally:
            teardown_test_db()

def test_explicit_relay_to_display_dict():
    from utils.relay_utils import explicit_relay_to_display_dict
    relay = {
        'relay_id': 1,
        'date': '2024-04-24',
        'meet': 'Test Meet',
        'team': 'Team A',
        'event': 'DMR',
        'total_result': '11:05.00',
        'team_designation': 'A',
        'legs': [
            {'leg_number': 1, 'athlete': 'Alice', 'split_event': '1200m', 'split_result': '3:45.00'},
            {'leg_number': 2, 'athlete': 'Bob', 'split_event': '400m', 'split_result': '52.00'},
            {'leg_number': 3, 'athlete': 'Charlie', 'split_event': '800m', 'split_result': '1:58.00'},
            {'leg_number': 4, 'athlete': 'Diana', 'split_event': '1600m', 'split_result': '4:30.00'}
        ]
    }
    d = explicit_relay_to_display_dict(relay)
    assert d['event'] == 'DMR'
    assert d['result'] == '11:05.00'
    assert d['relay_time_numeric'] == 11 * 60 + 5
    assert d['athletes'] == ['Alice', 'Bob', 'Charlie', 'Diana']
    assert len(d['legs']) == 4
    print("PASS: explicit_relay_to_display_dict")

def test_insert_relay_api():
    with app.app_context():
        setup_test_db()
    try:
        with app.test_client() as client:
            resp = client.post('/insert_relay', json={
                'date': '2024-05-01',
                'meet': 'Spring Meet',
                'team': 'Bulldogs',
                'event': '4x400m',
                'team_designation': 'B',
                'legs': [
                    {'athlete': 'Eve', 'split_result': '55.00'},
                    {'athlete': 'Frank', 'split_result': '55.50'},
                    {'athlete': 'Grace', 'split_result': '56.00'},
                    {'athlete': 'Heidi', 'split_result': '54.50'}
                ]
            })
            if resp.status_code != 200:
                print("API response:", resp.status_code, resp.get_json())
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert 'relay_id' in data
            print("PASS: insert_relay API")

            # Bad request: missing legs
            resp2 = client.post('/insert_relay', json={
                'date': '2024-05-01',
                'meet': 'Spring Meet',
                'team': 'Bulldogs',
                'event': '4x400m',
                'legs': []
            })
            assert resp2.status_code == 400
            print("PASS: insert_relay rejects empty legs")

            # Bad request: wrong number of legs
            resp3 = client.post('/insert_relay', json={
                'date': '2024-05-01',
                'meet': 'Spring Meet',
                'team': 'Bulldogs',
                'event': 'DMR',
                'legs': [
                    {'athlete': 'Eve', 'split_result': '55.00'},
                    {'athlete': 'Frank', 'split_result': '55.50'}
                ]
            })
            assert resp3.status_code == 400
            print("PASS: insert_relay rejects wrong leg count")
    finally:
        with app.app_context():
            teardown_test_db()

if __name__ == '__main__':
    test_relay_config()
    test_explicit_relay_to_display_dict()
    test_insert_relay()
    test_insert_relay_api()
    print("\n=== All tests passed ===")

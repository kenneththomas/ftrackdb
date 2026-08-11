import os
import tempfile
import unittest

from models import AthleteRanking, Database, StaggerScore
from utils.rankings import rank_performances
from wavelight import app


class RankingEngineTests(unittest.TestCase):
    def setUp(self):
        database_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        database_file.close()
        self.database_path = database_file.name
        self.previous_database = app.config['DATABASE']
        app.config['DATABASE'] = self.database_path
        self.app_context = app.app_context()
        self.app_context.push()
        Database.get_connection().close()

    def tearDown(self):
        self.app_context.pop()
        app.config['DATABASE'] = self.previous_database
        os.remove(self.database_path)

    def insert_rows(self, rows):
        conn = Database.get_connection()
        with conn:
            conn.executemany('''
                INSERT INTO Results (Date, Athlete, Meet_Name, Event, Result, Team)
                VALUES (?, ?, ?, ?, ?, 'Test')
            ''', rows)
        conn.close()

    def test_numeric_time_parsing_and_competition_ties(self):
        ranked = rank_performances([
            ('Minute', '1:00.00'),
            ('Fast A', '59.90'),
            ('Fast B', '59.90'),
            ('Ten', '10.00'),
        ], '400m')

        self.assertEqual(ranked['Ten']['rank'], 1)
        self.assertEqual(ranked['Fast A']['rank'], 2)
        self.assertEqual(ranked['Fast B']['rank'], 2)
        self.assertEqual(ranked['Minute']['rank'], 4)

    def test_jump_is_ranked_as_a_field_event(self):
        ranked = rank_performances([
            ('Lower', "5'10\""),
            ('Higher', "6'2\""),
        ], 'High Jump')
        self.assertEqual(ranked['Higher']['rank'], 1)

    def test_snapshot_collapses_multiple_attempts_and_orders_same_day_meets(self):
        self.insert_rows([
            ('2026-08-01', 'Prior', 'Alpha Meet', '800m', '2:00.00'),
            ('2026-08-01', 'Runner', 'Beta Meet', '800m', '2:05.00'),
            ('2026-08-01', 'Runner', 'Beta Meet', '800m', '1:59.00'),
        ])

        snapshots = AthleteRanking.refresh_meet_rankings('Beta Meet')

        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]['ranking_before'], None)
        self.assertEqual(snapshots[0]['ranking_after'], 1)
        self.assertEqual(snapshots[0]['mark_after'], '1:59.00')

    def test_stagger_rebuild_is_repeatable(self):
        self.insert_rows([
            ('2026-08-02', 'A', 'Later', '800m', '2:00.00'),
            ('2026-08-02', 'B', 'Later', '800m', '2:01.00'),
            ('2026-08-01', 'B', 'Earlier', '800m', '2:00.00'),
            ('2026-08-01', 'A', 'Earlier', '800m', '2:01.00'),
        ])
        StaggerScore.rate_meet('Later')
        StaggerScore.rate_meet('Earlier')
        first = StaggerScore.get_scores_for_athlete('A')['800m']

        # Chronological order is Earlier (B wins), then Later (A wins). If the
        # old activation order were used, A would finish below 1000 instead.
        self.assertGreater(first, 1000)

        StaggerScore.rebuild_all()
        second = StaggerScore.get_scores_for_athlete('A')['800m']

        self.assertAlmostEqual(first, second)
        history = StaggerScore.get_meet_history('Earlier') + StaggerScore.get_meet_history('Later')
        self.assertEqual(len(history), 4)

        conn = Database.get_connection()
        with conn:
            conn.execute("UPDATE Results SET Result = '1:59.00' WHERE Meet_Name = 'Earlier' AND Athlete = 'A'")
            conn.execute("UPDATE Results SET Result = '2:02.00' WHERE Meet_Name = 'Earlier' AND Athlete = 'B'")
        conn.close()
        StaggerScore.invalidate()
        changed = StaggerScore.get_scores_for_athlete('A')['800m']
        self.assertGreater(changed, first)


if __name__ == '__main__':
    unittest.main()

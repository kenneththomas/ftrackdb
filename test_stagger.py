import os
import tempfile
import unittest

from models import Database, STAGGER_K, compute_stagger_deltas_for_meet
from wavelight import app


class NormalizedStaggerTests(unittest.TestCase):
    def setUp(self):
        database_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        database_file.close()
        self.database_path = database_file.name
        self.previous_database = app.config['DATABASE']
        app.config['DATABASE'] = self.database_path
        self.app_context = app.app_context()
        self.app_context.push()
        conn = Database.get_connection()
        conn.close()

    def tearDown(self):
        self.app_context.pop()
        app.config['DATABASE'] = self.previous_database
        os.remove(self.database_path)

    def deltas_for(self, records):
        placements = {('800m', '2026-08-11'): records}
        all_deltas, _ = compute_stagger_deltas_for_meet(
            'Test Meet', lambda _meet_name: placements
        )
        return {athlete: delta for _event, _date, athlete, delta in all_deltas}

    def test_equal_rated_winner_and_last_have_same_change_in_any_field(self):
        two_athletes = [
            {'athlete': 'Athlete 1', 'place': 1},
            {'athlete': 'Athlete 2', 'place': 2},
        ]
        large_field = [
            {'athlete': f'Athlete {place}', 'place': place}
            for place in range(1, 25)
        ]

        two_deltas = self.deltas_for(two_athletes)
        large_deltas = self.deltas_for(large_field)

        self.assertAlmostEqual(two_deltas['Athlete 1'], STAGGER_K / 2)
        self.assertAlmostEqual(two_deltas['Athlete 2'], -STAGGER_K / 2)
        self.assertAlmostEqual(large_deltas['Athlete 1'], STAGGER_K / 2)
        self.assertAlmostEqual(large_deltas['Athlete 24'], -STAGGER_K / 2)

    def test_ties_count_as_half_a_win(self):
        deltas = self.deltas_for([
            {'athlete': 'Winner', 'place': 1},
            {'athlete': 'Tied A', 'place': 2},
            {'athlete': 'Tied B', 'place': 2},
        ])

        self.assertAlmostEqual(deltas['Winner'], STAGGER_K / 2)
        self.assertAlmostEqual(deltas['Tied A'], -STAGGER_K / 4)
        self.assertAlmostEqual(deltas['Tied B'], -STAGGER_K / 4)
        self.assertAlmostEqual(sum(deltas.values()), 0.0)

    def test_upset_moves_scores_more_than_an_expected_result(self):
        conn = Database.get_connection()
        with conn:
            conn.executemany(
                'INSERT INTO StaggerScores (athlete, event, score) VALUES (?, ?, ?)',
                [('Favorite', '800m', 1200), ('Underdog', '800m', 1000)],
            )
        conn.close()

        upset = self.deltas_for([
            {'athlete': 'Underdog', 'place': 1},
            {'athlete': 'Favorite', 'place': 2},
        ])
        expected_result = self.deltas_for([
            {'athlete': 'Favorite', 'place': 1},
            {'athlete': 'Underdog', 'place': 2},
        ])

        self.assertGreater(upset['Underdog'], expected_result['Favorite'])
        self.assertLess(upset['Favorite'], expected_result['Underdog'])
        self.assertLessEqual(abs(upset['Underdog']), STAGGER_K)

    def test_single_athlete_has_no_head_to_head_change(self):
        deltas = self.deltas_for([{'athlete': 'Solo', 'place': 1}])

        self.assertEqual(deltas['Solo'], 0.0)


if __name__ == '__main__':
    unittest.main()

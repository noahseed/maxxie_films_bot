import unittest
from catalogue import Catalogue


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.store = Catalogue(':memory:')
        for number, title in enumerate(('Matrix 1999 VF', 'Matrix 1999 VOSTFR', 'Matrix 2021 MULTI',
                                        'Harry Potter 2001 VF', 'L’été de nos vies 2019 FR'), 1):
            film_id = self.store.add({'file_id': str(number), 'file_unique_id': str(number)}, 'video', title)
            self.store.link_channel(-100123, film_id, number * 10)

    def tearDown(self):
        self.store.db.close()

    def titles(self, query):
        return [row[1] for row in self.store.search_channel(-100123, query)]

    def test_typo_and_unordered_words(self):
        self.assertIn('Harry Potter 2001 VF', self.titles('poter harry'))
        self.assertIn('Matrix 1999 VF', self.titles('matrx'))

    def test_year_and_language_filters_are_strict(self):
        self.assertEqual(self.titles('matrx 1999 VF'), ['Matrix 1999 VF'])
        self.assertEqual(self.titles('matrix 1999 VOSTFR'), ['Matrix 1999 VOSTFR'])
        self.assertEqual(self.titles('matrix 1998'), [])
        self.assertEqual(self.titles('matrix 2021 VF'), [])

    def test_accents_and_language_alias(self):
        self.assertEqual(self.titles('ete 2019 francais'), ['L’été de nos vies 2019 FR'])

    def test_unrelated_words_do_not_return_a_film(self):
        self.assertEqual(self.titles('zoologique'), [])

    def test_other_channel_is_excluded(self):
        self.assertEqual(self.store.search_channel(-100999, 'matrix'), [])

    def test_exact_match_ranks_ahead_of_typo_match(self):
        film_id = self.store.add({'file_id': 'typo', 'file_unique_id': 'typo'}, 'video', 'Mattrix VF')
        self.store.link_channel(-100123, film_id, 99)
        self.assertNotEqual(self.titles('matrix')[0], 'Mattrix VF')


if __name__ == '__main__':
    unittest.main()

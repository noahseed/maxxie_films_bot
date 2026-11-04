"""Recherche de titres : mots libres, année, langue et fautes de frappe."""
from difflib import SequenceMatcher
import heapq
import re
import unicodedata

LANGUAGES = {'vf': 'vf', 'vff': 'vf', 'vfi': 'vf', 'fr': 'vf', 'francais': 'vf',
             'vostfr': 'vostfr', 'vo': 'vo', 'multi': 'multi'}


def words(value):
    value = ''.join(c for c in unicodedata.normalize('NFKD', value.casefold())
                    if not unicodedata.combining(c))
    return re.findall(r'[^\W_]+', value, flags=re.UNICODE)


def ranked_results(rows, query, limit=11):
    tokens = words(query[:200])[:12]
    if not tokens:
        return []
    years = {word for word in tokens if re.fullmatch(r'(?:19|20)\d{2}', word)}
    languages = {LANGUAGES[word] for word in tokens if word in LANGUAGES}
    terms = [word for word in tokens if word not in years and word not in LANGUAGES]

    def candidates():
        for film_id, title, message_id in rows:
            title_words = words(title)
            if not years.issubset(title_words):
                continue
            available_languages = {LANGUAGES[word] for word in title_words if word in LANGUAGES}
            if not languages.issubset(available_languages):
                continue
            scores = []
            for term in terms:
                if any(term in word for word in title_words):
                    scores.append(1.0)
                    continue
                score = max((SequenceMatcher(None, term, word, autojunk=False).ratio()
                             for word in title_words if len(word) >= 3), default=0)
                if len(term) < 4 or score < 0.75:
                    break
                scores.append(score)
            else:
                score = min(scores, default=1.0)
                yield (score, film_id, title, message_id)

    return [(film_id, title, message_id) for _, film_id, title, message_id in
            heapq.nlargest(limit, candidates(), key=lambda row: (row[0], row[1]))]

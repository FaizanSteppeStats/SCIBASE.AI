import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import citations as c


def publication(**overrides):
    value = {'source': 'MED', 'id': '123', 'title': 'A <i>synthetic</i> malaria study',
             'pubYear': '2024', 'doi': '10.1234/example', 'isOpenAccess': 'Y',
             'authorList': {'author': [{'lastName': 'García', 'firstName': 'Ana'},
                                       {'collectiveName': 'Example Consortium'}]},
             'journalInfo': {'journal': {'title': 'Example Journal'}, 'volume': '2', 'issue': '1'},
             'pageInfo': '10–20', 'abstractText': '<p>Malaria prevention.</p><p>Synthetic data.</p>'}
    value.update(overrides)
    return value


def response(records):
    return io.BytesIO(json.dumps({'resultList': {'result': records}}).encode())


class CitationsTest(unittest.TestCase):
    def test_normalize_unicode_authors_and_markup(self):
        item = c.normalize(publication())
        self.assertEqual(item['title'], 'A synthetic malaria study')
        self.assertEqual(item['authors'][0], {'family': 'García', 'given': 'Ana'})
        self.assertEqual(item['authors'][1], {'literal': 'Example Consortium'})
        self.assertEqual(item['abstract'], 'Malaria prevention. Synthetic data.')

    def test_missing_fields_are_not_fabricated(self):
        item = c.normalize({'source': 'MED', 'id': '3', 'title': 'Title'})
        self.assertEqual(item['authors'], [])
        self.assertNotIn('issued', c.csl_json([item])[0])
        self.assertNotIn('DOI', c.csl_json([item])[0])
        self.assertEqual(len(item['warnings']), 4)

    def test_bad_doi_omitted(self):
        self.assertEqual(c.normalize(publication(doi='https://evil.test'))['doi'], '')
        self.assertEqual(c.normalize(publication(doi='https://doi.org/10.1234/X'))['doi'], '10.1234/X')

    def test_context_stays_local_and_query_encoded(self):
        seen = []
        def opener(req, timeout):
            seen.append(req.full_url)
            self.assertEqual(timeout, 15)
            return response([publication()])
        result = c.search('TITLE:"malaria" & study', context='privatecontext malaria', open_access=True, opener=opener)
        params = parse_qs(urlparse(seen[0]).query)
        self.assertEqual(params['query'], ['(TITLE:"malaria" & study) AND OPEN_ACCESS:Y'])
        self.assertNotIn('privatecontext', seen[0])
        self.assertEqual(result['items'][0]['matched_terms'], ['malaria'])
        self.assertEqual(result['items'][0]['context_overlap'], 0.5)

    def test_duplicate_doi_case_insensitive(self):
        records = [publication(doi='10.1234/AbC'), publication(id='456', doi='10.1234/abc')]
        self.assertEqual(len(c.search('test', opener=lambda *a, **k: response(records))['items']), 1)

    def test_ranking_and_ties(self):
        records = [publication(id='1', doi='', title='Unrelated', abstractText=''),
                   publication(id='2', doi='', title='Malaria prevention', abstractText=''),
                   publication(id='3', doi='', title='Malaria prevention', abstractText='')]
        result = c.search('test', context='malaria prevention', opener=lambda *a, **k: response(records))
        self.assertEqual([i['id'] for i in result['items']], ['MED:2', 'MED:3', 'MED:1'])

    def test_empty_result_valid(self):
        self.assertEqual(c.search('test', opener=lambda *a, **k: response([]))['items'], [])

    def test_invalid_records_warn_or_fail(self):
        result = c.search('test', opener=lambda *a, **k: response([{}, publication()]))
        self.assertEqual(len(result['warnings']), 1)
        with self.assertRaises(c.CitationError):
            c.search('test', opener=lambda *a, **k: response([{}]))

    def test_invalid_inputs_do_not_call_network(self):
        def fail(*a, **k):
            self.fail('Network should not be called')
        for query, limit in [('', 1), ('x' * 1001, 1), ('ok', 0), ('ok', 51), ('ok', True)]:
            with self.subTest(query=query[:10], limit=limit), self.assertRaises(c.CitationError):
                c.search(query, limit=limit, opener=fail)

    def test_rate_limit_retry(self):
        calls, waits = [], []
        def opener(*a, **k):
            calls.append(1)
            if len(calls) < 3:
                raise HTTPError('https://example.test', 429, 'Limit', {'Retry-After': '0'}, None)
            return response([])
        c.search('test', opener=opener, sleep=waits.append)
        self.assertEqual(waits, [0, 0])
        self.assertEqual(len(calls), 3)

    def test_retry_exhaustion_and_long_retry_after(self):
        for headers, expected in [({}, 3), ({'Retry-After': '120'}, 1)]:
            calls = []
            def opener(*a, **k):
                calls.append(1)
                raise HTTPError('https://example.test', 503, 'Busy', headers, None)
            with self.assertRaises(c.CitationError):
                c.search('test', opener=opener, sleep=lambda _: None)
            self.assertEqual(len(calls), expected)

    def test_http_400_not_retried(self):
        calls = []
        def opener(*a, **k):
            calls.append(1)
            raise HTTPError('https://example.test', 400, 'Bad query', {}, None)
        with self.assertRaisesRegex(c.CitationError, 'HTTP 400'):
            c.search('test', opener=opener)
        self.assertEqual(len(calls), 1)

    def test_transport_and_invalid_json(self):
        def offline(*a, **k):
            raise URLError('offline')
        with self.assertRaisesRegex(c.CitationError, 'Cannot reach'):
            c.search('test', opener=offline)
        for body in [b'<html>error</html>', b'{}', b'[]', b'{"resultList":{"result":null}}']:
            with self.subTest(body=body), self.assertRaises(c.CitationError):
                c.search('test', opener=lambda *a, **k: io.BytesIO(body))

    def test_size_limit(self):
        with self.assertRaisesRegex(c.CitationError, '4 MiB'):
            c.search('test', opener=lambda *a, **k: io.BytesIO(b' ' * (c.MAX_BYTES + 1)))

    def test_csl_and_ris_exports(self):
        item = c.normalize(publication())
        exported = c.csl_json([item])[0]
        self.assertEqual(exported['issued'], {'date-parts': [[2024]]})
        self.assertEqual(exported['author'][1]['literal'], 'Example Consortium')
        self.assertEqual(exported['container-title'], 'Example Journal')
        result = c.ris([item])
        self.assertIn('AU  - García, Ana', result)
        self.assertIn('SP  - 10\nEP  - 20', result)
        self.assertEqual(result.count('TY  -'), 1)

    def test_ris_field_newlines_do_not_inject_records(self):
        item = c.normalize(publication(title='Title\nTY  - BOOK'))
        self.assertEqual(c.ris([item]).count('\nTY  -'), 0)

    def test_retraction_warning(self):
        item = c.normalize(publication(pubTypeList={'pubType': ['Retracted Publication']}))
        self.assertTrue(any('Retraction' in w for w in item['warnings']))

    def test_export_requires_valid_selected_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'results.json'
            path.write_text(json.dumps({'items': [c.normalize(publication())]}))
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = c.main(['export', str(path), '--id', 'MED:missing'])
            self.assertEqual(code, 2)
            self.assertEqual(out.getvalue(), '')
            self.assertIn('Unknown selected IDs', err.getvalue())
            with contextlib.redirect_stdout(out):
                self.assertEqual(c.main(['export', str(path), '--id', 'MED:123', '--id', 'MED:123']), 0)
            self.assertEqual(len(json.loads(out.getvalue())), 1)


if __name__ == '__main__':
    unittest.main()

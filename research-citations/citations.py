#!/usr/bin/env python3
"""Europe PMC discovery and portable citation exports (Python 3.10+, stdlib only)."""
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

ENDPOINT = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search'
MAX_BYTES = 4 * 1024 * 1024


class CitationError(Exception):
    """An actionable retrieval or input error."""


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        self.parts.append(' ')

    def handle_endtag(self, tag):
        self.parts.append(' ')


def clean(value):
    if not isinstance(value, str):
        return ''
    parser = PlainText()
    parser.feed(value)
    return ' '.join(''.join(parser.parts).split())


def tokens(text):
    stop = {'the', 'and', 'for', 'with', 'that', 'this', 'from', 'were', 'was', 'are', 'into', 'have', 'has', 'not', 'our'}
    return {w for w in re.findall(r'[^\W_]+', text.casefold()) if len(w) > 2 and w not in stop}


def normalize(record):
    if not isinstance(record, dict):
        raise CitationError('Provider returned a non-object publication.')
    source, identifier = clean(record.get('source')), clean(record.get('id'))
    title = clean(record.get('title'))
    if not source or not identifier or not title:
        raise CitationError('Publication is missing its source, ID or title.')
    doi = clean(record.get('doi'))
    doi = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', doi, flags=re.I)
    warnings = []
    if doi and not re.fullmatch(r'10\.\d{4,9}/\S+', doi):
        warnings.append('Provider DOI is malformed; omitted from exports.')
        doi = ''
    year = clean(str(record.get('pubYear', '')))
    if not re.fullmatch(r'\d{4}', year):
        year = ''
        warnings.append('Publication year unavailable.')
    authors = []
    author_list = record.get('authorList') or {}
    if not isinstance(author_list, dict) or not isinstance(author_list.get('author', []), list):
        raise CitationError('Provider author list has an unexpected shape.')
    for author in author_list.get('author', []):
        if not isinstance(author, dict):
            raise CitationError('Provider author entry has an unexpected shape.')
        family, given = clean(author.get('lastName')), clean(author.get('firstName'))
        literal = clean(author.get('collectiveName')) or clean(author.get('fullName'))
        if family:
            authors.append({'family': family, 'given': given})
        elif literal:
            authors.append({'literal': literal})
    if not authors:
        warnings.append('Structured authors unavailable; no names inferred from authorString.')
    info = record.get('journalInfo') or {}
    if not isinstance(info, dict) or not isinstance(info.get('journal', {}), dict):
        raise CitationError('Provider journal metadata has an unexpected shape.')
    journal = clean(info.get('journal', {}).get('title'))
    if not journal:
        warnings.append('Journal unavailable; verify publication type before submitting.')
    abstract = clean(record.get('abstractText'))
    if not abstract:
        warnings.append('Abstract unavailable; context matching uses title only.')
    pubtypes = record.get('pubTypeList') or {}
    if not isinstance(pubtypes, dict) or not isinstance(pubtypes.get('pubType', []), list):
        raise CitationError('Provider publication types have an unexpected shape.')
    types = [clean(t) for t in pubtypes.get('pubType', [])]
    if any('retract' in t.casefold() for t in types):
        warnings.append('Retraction-related publication type: review the source before citing.')
    return {'id': f'{source}:{identifier}', 'title': title, 'authors': authors,
            'year': year, 'journal': journal, 'volume': clean(info.get('volume')),
            'issue': clean(info.get('issue')), 'pages': clean(record.get('pageInfo')),
            'doi': doi, 'abstract': abstract, 'publication_types': types,
            'open_access': record.get('isOpenAccess') == 'Y',
            'url': f'https://europepmc.org/article/{quote(source, safe="")}/{quote(identifier, safe="")}',
            'warnings': warnings}


def search(query, *, limit=10, context='', open_access=False, opener=urlopen, sleep=time.sleep):
    if not isinstance(query, str) or not query.strip() or len(query) > 1000:
        raise CitationError('Supply a non-empty search query of at most 1,000 characters.')
    if type(limit) is not int or not 1 <= limit <= 50:
        raise CitationError('Limit must be between 1 and 50.')
    if not isinstance(context, str) or len(context) > 20000:
        raise CitationError('Context must be text of at most 20,000 characters.')
    effective_query = f'({query}) AND OPEN_ACCESS:Y' if open_access else query
    url = ENDPOINT + '?' + urlencode({'query': effective_query, 'format': 'json',
                                     'resultType': 'core', 'pageSize': limit})
    request = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'SCIBASE-Citations/0.1'})
    for attempt in range(3):
        try:
            with opener(request, timeout=15) as response:
                raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise CitationError('Provider response exceeds the 4 MiB limit.')
            payload = json.loads(raw)
            break
        except HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                # Respect short Retry-After values; do not hammer long rate limits.
                retry = (exc.headers or {}).get('Retry-After', '')
                if retry and (not retry.isdigit() or int(retry) > 30):
                    raise CitationError('Provider asks for a longer wait; retry later.') from exc
                sleep(int(retry) if retry else 2 ** attempt)
                continue
            raise CitationError(f'Europe PMC returned HTTP {exc.code}; retry later or revise the query.') from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise CitationError('Cannot reach Europe PMC. Check network access and retry.') from exc
        except (ValueError, UnicodeError) as exc:
            raise CitationError('Europe PMC returned invalid JSON.') from exc
    if not isinstance(payload, dict) or not isinstance(payload.get('resultList'), dict):
        raise CitationError('Europe PMC response is missing resultList.')
    records = payload['resultList'].get('result')
    if not isinstance(records, list):
        raise CitationError('Europe PMC response is missing the result array.')
    items, seen, warnings = [], set(), []
    context_tokens = tokens(context)
    for record in records:
        try:
            item = normalize(record)
        except CitationError as exc:
            warnings.append(f'Skipped invalid publication: {exc}')
            continue
        key = 'doi:' + item['doi'].casefold() if item['doi'] else item['id']
        if key in seen:
            continue
        seen.add(key)
        overlap = sorted(context_tokens & tokens(item['title'] + ' ' + item['abstract']))
        item['matched_terms'] = overlap
        item['context_overlap'] = round(len(overlap) / len(context_tokens), 4) if context_tokens else None
        items.append(item)
    if records and not items:
        raise CitationError('All returned publications were invalid; no references exported.')
    if context_tokens:
        items.sort(key=lambda item: item['context_overlap'], reverse=True)
    return {'provider': 'Europe PMC', 'query': query, 'request_url': url,
            'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'ranking': 'local token overlap within retrieved candidates' if context_tokens else 'provider relevance',
            'notice': 'Candidate matches do not establish support for a claim. Verify each source. No AI inference is used.',
            'warnings': warnings, 'items': items}


def csl_json(items):
    output = []
    for item in items:
        record = {'id': item['id'], 'type': 'article-journal' if item['journal'] else 'article',
                  'title': item['title'], 'URL': item['url']}
        for source, target in [('authors', 'author'), ('journal', 'container-title'), ('volume', 'volume'),
                               ('issue', 'issue'), ('pages', 'page'), ('doi', 'DOI'), ('abstract', 'abstract')]:
            if item[source]:
                record[target] = item[source]
        if item['year']:
            record['issued'] = {'date-parts': [[int(item['year'])]]}
        output.append(record)
    return output


def ris(items):
    lines = []
    def field(tag, value):
        if value:
            lines.append(f'{tag}  - {" ".join(str(value).split())}')
    for item in items:
        field('TY', 'JOUR' if item['journal'] else 'GEN')
        field('ID', item['id'])
        field('TI', item['title'])
        for author in item['authors']:
            field('AU', author.get('literal') or ', '.join(filter(None, [author.get('family'), author.get('given')])))
        for tag, name in [('PY', 'year'), ('JO', 'journal'), ('VL', 'volume'), ('IS', 'issue'),
                          ('DO', 'doi'), ('UR', 'url'), ('AB', 'abstract')]:
            field(tag, item[name])
        pages = re.split(r'[-–]', item['pages'], maxsplit=1)
        field('SP', pages[0])
        if len(pages) == 2:
            field('EP', pages[1])
        lines.extend(['ER  -', ''])
    return '\n'.join(lines).rstrip()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    find = sub.add_parser('search', help='Search live Europe PMC metadata; prints JSON.')
    find.add_argument('query', help='Europe PMC query syntax, e.g. TITLE:"malaria"')
    find.add_argument('--limit', type=int, default=10)
    find.add_argument('--context', default='', help='Local ranking text; never sent to the provider.')
    find.add_argument('--open-access', action='store_true')
    export = sub.add_parser('export', help='Export explicitly selected IDs from saved search JSON.')
    export.add_argument('input', type=Path)
    export.add_argument('--id', action='append', required=True, help='Candidate ID, e.g. MED:123 (repeatable).')
    export.add_argument('--format', choices=['csl', 'ris'], default='csl')
    args = parser.parse_args(argv)
    try:
        if args.command == 'search':
            result = search(args.query, limit=args.limit, context=args.context, open_access=args.open_access)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if args.input.stat().st_size > MAX_BYTES:
                raise CitationError('Input exceeds the 4 MiB limit.')
            packet = json.loads(args.input.read_text(encoding='utf-8'))
            if not isinstance(packet, dict) or not isinstance(packet.get('items'), list):
                raise CitationError('Expected a saved search packet with items.')
            by_id = {item['id']: item for item in packet['items']}
            missing = set(args.id) - by_id.keys()
            if missing:
                raise CitationError('Unknown selected IDs: ' + ', '.join(sorted(missing)))
            items = [by_id[key] for key in dict.fromkeys(args.id)]
            result = json.dumps(csl_json(items), ensure_ascii=False, indent=2) if args.format == 'csl' else ris(items)
            print(result)
    except (CitationError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())

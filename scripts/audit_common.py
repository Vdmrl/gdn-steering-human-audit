"""Frozen sample contract; one answer, one feature, two independent ratings."""
import hashlib
import json
from pathlib import Path

FEATURES = ('numbered', 'probabilistic_framing', 'complexity', 'theistic_framing')
USERS = {'vova': ('Вова', 'A'), 'stepa': ('Стёпа', 'A'), 'slava': ('Слава', 'B'), 'petya': ('Петя', 'B')}
TITLES = {'numbered': 'Числовая структура', 'probabilistic_framing': 'Неуверенность / вероятностные оговорки', 'complexity': 'Сложность языка / Technical', 'theistic_framing': 'Бог / религиозное обрамление'}
DATA = Path(__file__).resolve().parents[1] / 'data'

def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]

def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def validate_public(rows, rubric):
    assert len(rows) == 128, 'Expected 128 unique assignments'
    assert len({r['item_id'] for r in rows}) == 128
    allowed = {'item_id', 'group', 'feature', 'language', 'scenario', 'text'}
    for r in rows:
        assert set(r) == allowed, 'Private or unexpected field in annotator data'
        assert r['feature'] in FEATURES and r['language'] in ('en', 'ru')
        assert r['group'] in ('A', 'B') and r['scenario'] and r['text']
    for group in ('A', 'B'):
        for feature in FEATURES:
            for language in ('en', 'ru'):
                assert sum(r['group'] == group and r['feature'] == feature and r['language'] == language for r in rows) == 8
    assert rubric['rubric_version'] in ('5.2.1-review1', '6.0.0-concrete-audit-review1', '6.1.0-unified-review1', '6.2.0-religious-review1')

def load_public():
    rows = read_jsonl(DATA / 'public_items.jsonl')
    rubric = json.loads((DATA / 'rubric.json').read_text(encoding='utf-8'))
    validate_public(rows, rubric)
    metadata = json.loads((DATA / 'sample_metadata.json').read_text(encoding='utf-8'))
    assert metadata['rubric_version'] == rubric['rubric_version'], 'Rubric version differs from frozen sample'
    assert sha(DATA / 'public_items.jsonl') == metadata['public_sha256']
    assert sha(DATA / 'rubric.json') == metadata['rubric_sha256']
    return rows, rubric, metadata

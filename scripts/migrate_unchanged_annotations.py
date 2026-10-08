"""Retain genuine submitted labels only for byte-equivalent texts and unchanged features."""
import json
import os
from uuid import UUID

import argilla as rg

from audit_common import DATA, load_public, read_jsonl


def main():
    rows, rubric, metadata = load_public()
    archived = DATA / 'private-archives/v3'
    old_rubric = json.loads((archived / 'rubric.json').read_text(encoding='utf-8'))
    old_rows = {r['item_id']: r for r in read_jsonl(archived / 'public_items.jsonl')}
    current = {r['item_id']: r for r in rows}
    client = rg.Argilla(api_url=os.getenv('ARGILLA_API_URL', 'http://localhost:6900'),
                       api_key=os.getenv('ARGILLA_API_KEY', 'argilla.apikey'))
    migrated = 0
    for response in read_jsonl(archived / 'exports/annotations.jsonl'):
        if not response['completed']:
            continue
        row = current[response['item_id']]
        feature = row['feature']
        assert old_rows[row['item_id']] == row, 'Changed answer must not inherit labels'
        if old_rubric['features'][feature] != rubric['features'][feature]:
            continue
        dataset = client.datasets(name=feature, workspace=metadata['workspace_prefix'] + row['group'].lower())
        record = next(r for r in dataset.records(with_responses=True) if str(r.id) == row['item_id'])
        existing = [r for r in record.responses or [] if str(r.user_id) == response['user_id'] and r.question_name == 'trait_score']
        if existing:
            assert str(existing[0].value) == str(response['responses']['trait_score'])
            continue
        values = [rg.Response(question_name=question, value=value, user_id=UUID(response['user_id']), status='submitted')
                  for question, value in response['responses'].items() if response['statuses'][question] == 'submitted']
        dataset.records.log([rg.Record(id=row['item_id'], fields={'scenario': row['scenario'], 'text': row['text']}, responses=values)])
        migrated += 1
    print('Retained', migrated, 'genuine unchanged submitted labels; changed features excluded.')


if __name__ == '__main__':
    main()

"""Export all four annotators; drafts never enter agreement statistics."""
import argparse
import csv
import os
from pathlib import Path
import argilla as rg
from audit_common import DATA, FEATURES, USERS, load_public, write_jsonl

def scalar(value):
    return getattr(value, 'value', value)

def response_rows(record):
    grouped = {}
    for response in record.responses or []:
        user_id = str(response.user_id)
        row = grouped.setdefault(user_id, {'item_id': str(record.id), 'user_id': user_id, 'responses': {}, 'statuses': {}})
        row['responses'][response.question_name] = scalar(response.value)
        row['statuses'][response.question_name] = scalar(response.status)
    return list(grouped.values())

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default=str(DATA / 'exports'))
    args = parser.parse_args()
    public, _, metadata = load_public()
    expected = {r['item_id']: r for r in public}
    client = rg.Argilla(api_url=os.getenv('ARGILLA_API_URL', 'http://localhost:6900'), api_key=os.getenv('ARGILLA_API_KEY', 'argilla.apikey'))
    users = {str(user.id): user.username for user in client.users}
    result = []
    for group in ('A', 'B'):
        for feature in FEATURES:
            dataset = client.datasets(name=feature, workspace=metadata.get('workspace_prefix', 'steering-') + group.lower())
            if dataset is None:
                raise RuntimeError('Missing dataset; setup must finish before export')
            for record in dataset.records(with_responses=True):
                for row in response_rows(record):
                    username = users.get(row['user_id'])
                    assert username in USERS and USERS[username][1] == expected[row['item_id']]['group'], 'Unassigned annotator response'
                    submitted = str(row['statuses'].get('trait_score', '')).lower() == 'submitted'
                    row.update(username=username, completed=submitted and 'trait_score' in row['responses'], dataset_hash=metadata['public_sha256'])
                    result.append(row)
    output = Path(args.output_dir)
    write_jsonl(output / 'annotations.jsonl', result)
    with (output / 'annotations.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['item_id', 'username', 'completed', 'trait_score', 'comment'])
        writer.writeheader()
        for row in result:
            writer.writerow({key: row.get(key, row['responses'].get(key, '')) for key in writer.fieldnames})
    print(f'Exported {sum(r["completed"] for r in result)} submitted ratings out of 256 expected.')

if __name__ == '__main__':
    main()

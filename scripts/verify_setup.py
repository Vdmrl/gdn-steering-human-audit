"""Read-only check: uploaded texts, blind fields, scales and workspace membership."""
import os

import argilla as rg

from audit_common import FEATURES, USERS, load_public


def main():
    rows, rubric, metadata = load_public()
    client = rg.Argilla(api_url=os.getenv('ARGILLA_API_URL', 'http://localhost:6900'),
                       api_key=os.getenv('ARGILLA_API_KEY', 'argilla.apikey'))
    for group in ('A', 'B'):
        workspace = client.workspaces(metadata['workspace_prefix'] + group.lower())
        assert {u.username for u in workspace.users if u.username in USERS} == {
            u for u, (_, assigned) in USERS.items() if assigned == group}
        for feature in FEATURES:
            dataset = client.datasets(name=feature, workspace=workspace.name)
            actual = {str(r['id']): r['fields'] for r in dataset.records.to_list()}
            expected = {r['item_id']: {'scenario': r['scenario'], 'text': r['text']}
                        for r in rows if r['group'] == group and r['feature'] == feature}
            assert actual == expected and len(actual) == 16
            labels = {o['value'] for o in dataset.settings.questions['trait_score'].api_model().settings.options}
            assert labels == set(rubric['features'][feature]['anchors'])
            if group == 'A' and feature in ('probabilistic_framing', 'theistic_framing'):
                print(feature + ' ANNOTATION_URL http://localhost:6900/dataset/' + str(dataset.id) + '/annotation-mode?page=1&status=pending')
    print('Verified128 uploaded texts, blind fields, all scales and paired workspace access.')


if __name__ == '__main__':
    main()

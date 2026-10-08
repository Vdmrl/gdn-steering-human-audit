import importlib
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_common import FEATURES, validate_public
from calculate_metrics import agreement, analyze, bootstrap, weighted_kappa

class AuditTests(unittest.TestCase):
    def test_four_person_assignment_and_private_leak_rejection(self):
        rows = [{'item_id': f'{g}-{f}-{l}-{i}', 'group': g, 'feature': f, 'language': l, 'scenario': 'question', 'text': 'answer'} for g in ('A', 'B') for f in FEATURES for l in ('en', 'ru') for i in range(8)]
        rubric = {'rubric_version': '5.2.1-review1'}
        validate_public(rows, rubric)
        rows[0]['judge_score'] = 4
        with self.assertRaises(AssertionError):
            validate_public(rows, rubric)

    def test_percent_error_and_bias(self):
        result = agreement([{'judge': 1, 'humans': [0, 2], 'maximum': 4}])
        self.assertEqual(result['judge_human_mae_pct'], 25)
        self.assertEqual(result['judge_human_bias_pct'], 0)
        self.assertEqual(result['judge_human_exact_pct'], 0)
        self.assertEqual(weighted_kappa([(0, 0), (4, 4)], 4), 1)
        self.assertIsNone(weighted_kappa([(0, 0), (0, 0)], 4))

    def test_two_raters_do_not_double_bootstrap_units(self):
        result = bootstrap([{'cluster_id': 'same-prompt', 'judge': 1, 'humans': [1, 2], 'maximum': 4} for _ in range(3)], 100, 1)
        self.assertEqual(result['clusters'], 1)
        self.assertIsNone(result['ci95'])

    def test_drafts_excluded_and_duplicates_rejected(self):
        item = {'item_id': 'x', 'feature': 'numbered', 'annotators': ['vova', 'stepa'], 'cluster_id': 'p', 'sample_part': 'representative', 'language': 'en'}
        rubric = {'features': {'numbered': {'maximum': 4}}}
        score = {'feature': 'numbered', 'raw_score': 3, 'normalized_score_pct': 75, 'score_distribution': {'available_expected_normalized_score_pct': 72}}
        row = {'item_id': 'x', 'username': 'vova', 'completed': True, 'dataset_hash': 'h', 'responses': {'trait_score': '3'}}
        result = analyze([row | {'completed': False}], [item], {'run-0': {'x': score}}, 'h', rubric, 100)
        self.assertEqual(result['submitted_human_ratings'], 0)
        with self.assertRaises(AssertionError):
            analyze([row, row], [item], {'run-0': {'x': score}}, 'h', rubric, 100)

    def test_argilla_export_submitted_status_and_value(self):
        try:
            exporter = importlib.import_module('export_annotations')
        except ImportError:
            self.skipTest('Run SDK integration check in installed audit environment')
        import argilla as rg
        from uuid import uuid4
        record = rg.Record(id='x', fields={'text': 'fixture'}, responses=[rg.Response(question_name='trait_score', value='2', user_id=uuid4(), status='submitted')])
        rows = exporter.response_rows(record)
        self.assertEqual(rows[0]['responses']['trait_score'], '2')
        self.assertEqual(rows[0]['statuses']['trait_score'], 'submitted')

    def test_frozen_russian_v2_is_monolingual(self):
        import re
        from audit_common import load_public
        rows, _, metadata = load_public()
        if metadata['study_version'] not in ('2.0', '3.0', '4.0', '5.0', '6.0'):
            self.skipTest('Monolingual contract applies to sample2')
        russian = [r for r in rows if r['language'] == 'ru']
        self.assertEqual(len(russian), 64)
        for row in russian:
            self.assertIsNone(re.search(r'[A-Za-z\u4e00-\u9fff]', row['scenario'] + row['text']))
        self.assertEqual(metadata['workspace_prefix'], 'steering-v' + metadata['study_version'][0] + '-')

    def test_curated_v3_is_complete_readable_and_new_scale_is_explicit(self):
        from audit_common import load_public
        import re
        rows, rubric, metadata = load_public()
        if metadata['study_version'] not in ('3.0', '4.0', '5.0', '6.0'):
            self.skipTest('Curated contract applies to sample3')
        self.assertEqual(metadata['source_counts'], {'real': 0, 'synthetic': 128})
        self.assertEqual(rubric['features']['probabilistic_framing']['maximum'], 3)
        if metadata['study_version'] == '4.0':
            self.assertEqual(rubric['features']['theistic_framing']['maximum'], 3)
        if metadata['study_version'] in ('5.0', '6.0'):
            self.assertEqual(rubric['features']['theistic_framing']['maximum'], 2)
        for row in rows:
            self.assertLess(len(row['text']), 1800)
            self.assertTrue(row['text'].endswith('.'))
            if row['language'] == 'en':
                self.assertIsNone(re.search(r'[А-Яа-яЁё\u4e00-\u9fff]', row['scenario'] + row['text']))
            self.assertNotIn('...', row['text'])

    def test_every_fourth_record_has_a_long_paragraph(self):
        import random
        from audit_common import FEATURES, load_public
        rows, _, metadata = load_public()
        if metadata['study_version'] != '6.0':
            self.skipTest('Long paragraph contract applies to sample6')
        selected_ids = set()
        for group in ('A', 'B'):
            for index, feature in enumerate(FEATURES):
                selected = [r for r in rows if r['group'] == group and r['feature'] == feature]
                random.Random(metadata['shuffle_seed'] + ord(group) + index).shuffle(selected)
                for row in selected[3::4]:
                    selected_ids.add(row['item_id'])
                    self.assertGreaterEqual(len(row['text'].split()), 60)
                    self.assertGreaterEqual(len(row['text'].split('\n\n')[-1].split()), 50)
        self.assertEqual(selected_ids, set(metadata['long_paragraph_item_ids']))
        self.assertEqual(len(selected_ids), 32)

if __name__ == '__main__':
    unittest.main()

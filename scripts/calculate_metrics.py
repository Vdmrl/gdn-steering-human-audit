"""Agreement and repeatability; cluster bootstrap, no trait-success thresholds."""
import argparse
import html
import hashlib
import itertools
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from audit_common import DATA, FEATURES, USERS, load_public, read_jsonl, sha

def weighted_kappa(pairs, maximum):
    if not pairs:
        return None
    a, b = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
    observed = statistics.mean(abs(x - y) / maximum for x, y in pairs)
    expected = sum(nx * ny * abs(x - y) / maximum for x, nx in a.items() for y, ny in b.items()) / len(pairs) ** 2
    return None if expected == 0 else 1 - observed / expected

def agreement(entries):
    if not entries:
        return {'items': 0}
    pairs = [(e['judge'], h, e['maximum']) for e in entries for h in e['humans']]
    humans = [(e['humans'][0], e['humans'][1], e['maximum']) for e in entries if len(e['humans']) == 2]
    result = {
        'items': len(entries), 'human_ratings': len(pairs),
        'judge_human_exact_pct': 100 * statistics.mean(j == h for j, h, _ in pairs),
        'judge_human_mae_pct': statistics.mean(100 * abs(j - h) / m for j, h, m in pairs),
        'judge_human_bias_pct': statistics.mean(100 * (j - h) / m for j, h, m in pairs),
        'judge_mean_human_mae_pct': statistics.mean(100 * abs(e['judge'] - statistics.mean(e['humans'])) / e['maximum'] for e in entries),
        'human_human_items': len(humans),
        'human_human_exact_pct': 100 * statistics.mean(a == b for a, b, _ in humans) if humans else None,
        'human_human_mae_pct': statistics.mean(100 * abs(a - b) / m for a, b, m in humans) if humans else None,
    }
    maximums = {e['maximum'] for e in entries}
    if len(maximums) == 1:
        maximum = maximums.pop()
        result['judge_human_linear_weighted_kappa'] = weighted_kappa([(j, h) for j, h, _ in pairs], maximum)
        result['human_human_linear_weighted_kappa'] = weighted_kappa([(a, b) for a, b, _ in humans], maximum)
        result['confusion_human_rows_judge_columns'] = [[sum(h == x and j == y for j, h, _ in pairs) for y in range(maximum + 1)] for x in range(maximum + 1)]
    soft = [e for e in entries if e.get('expected_pct') is not None]
    result['logprob_expected_items'] = len(soft)
    result['logprob_expected_vs_mean_human_mae_pct'] = statistics.mean(abs(e['expected_pct'] - 100 * statistics.mean(e['humans']) / e['maximum']) for e in soft) if soft else None
    return result

def bootstrap(entries, repetitions, seed):
    if not entries:
        return {}
    clusters = defaultdict(list)
    for e in entries:
        clusters[e['cluster_id']].append(e)
    keys = list(clusters)
    if len(keys) < 2:
        return {'clusters': len(keys), 'ci95': None}
    rng = random.Random(seed)
    values = defaultdict(list)
    for _ in range(repetitions):
        sample = [e for key in rng.choices(keys, k=len(keys)) for e in clusters[key]]
        for key, value in agreement(sample).items():
            if key.endswith(('_pct', '_kappa')) and value is not None:
                values[key].append(value)
    ci = {}
    for key, series in values.items():
        series.sort()
        ci[key] = [series[int(.025 * (len(series) - 1))], series[int(.975 * (len(series) - 1))]]
    return {'clusters': len(keys), 'resamples': repetitions, 'ci95': ci}

def load_repeats(directory, rubric_version='5.2.1-review1'):
    result = defaultdict(dict)
    identities = {}
    for run in sorted(Path(directory).glob('run-*')):
        for feature in FEATURES:
            scores = run / feature / 'scores.jsonl'
            if not scores.exists():
                continue
            identity = json.loads((scores.parent / 'manifest.json').read_text(encoding='utf-8'))['identity']
            inputs = read_jsonl(Path(directory).parent / ('final-' + feature + '.jsonl'))
            digest = hashlib.sha256(json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            assert identity['input_sha256'] == digest, 'Repeat input hash differs'
            assert identity['features'] == [feature]
            assert identity['rubric']['rubric_version'] == rubric_version, 'Repeated rubric differs from human sample'
            assert feature not in identities or identities[feature] == identity, 'Repeat protocol differs'
            identities[feature] = identity
            expected_ids = {r['answer_id'] for r in inputs}
            for r in read_jsonl(scores):
                assert r['answer_id'] in expected_ids, 'Unknown repeated answer'
                assert r['feature'] == feature
                assert r['answer_id'] not in result[run.name], 'Duplicate repeated judgment'
                result[run.name][r['answer_id']] = r
    return result

def repeatability(manifest, repeats):
    summaries = {}
    for feature in ('all',) + FEATURES:
        items = [r for r in manifest if feature == 'all' or r['feature'] == feature]
        series, soft_series = [], []
        run_means = defaultdict(list)
        for item in items:
            judgments = [run[item['item_id']] for run in repeats.values() if item['item_id'] in run]
            if len(judgments) != 5:
                continue
            series.append([r['raw_score'] for r in judgments])
            soft = [r['score_distribution']['available_expected_normalized_score_pct'] for r in judgments]
            if all(x is not None for x in soft):
                soft_series.append(soft)
            for name, run in repeats.items():
                run_means[name].append(run[item['item_id']]['normalized_score_pct'])
        pairs = [(a, b) for scores in series for a, b in itertools.combinations(scores, 2)]
        summaries[feature] = {'expected_items': len(items), 'complete_five_repeat_items': len(series),
            'all_five_identical_pct': 100 * statistics.mean(len(set(s)) == 1 for s in series) if series else None,
            'pairwise_exact_pct': 100 * statistics.mean(a == b for a, b in pairs) if pairs else None,
            'mean_integer_range': statistics.mean(max(s) - min(s) for s in series) if series else None,
            'available_expected_mean_sd_pct': statistics.mean(statistics.pstdev(s) for s in soft_series) if soft_series else None,
            'available_expected_mean_range_pct': statistics.mean(max(s) - min(s) for s in soft_series) if soft_series else None,
            'normalized_run_means_pct': {name: statistics.mean(scores) for name, scores in run_means.items()}}
    return summaries

def analyze(annotations, manifest, repeats, public_hash, rubric, resamples=2000):
    by_id = {r['item_id']: r for r in manifest}
    labels = defaultdict(dict)
    counts = Counter()
    for r in annotations:
        if not r.get('completed'):
            continue
        item = by_id[r['item_id']]
        assert r['dataset_hash'] == public_hash, 'Annotation belongs to a different sample'
        assert r['username'] in item['annotators'], 'Wrong assignment'
        assert r['username'] not in labels[r['item_id']], 'Duplicate submitted annotation'
        score = int(r['responses']['trait_score'])
        maximum = rubric['features'][item['feature']]['maximum']
        assert str(score) == str(r['responses']['trait_score']) and 0 <= score <= maximum
        labels[r['item_id']][r['username']] = score
        counts[r['username']] += 1
    entries = []
    first = repeats.get('run-0', {})
    for item_id, users in labels.items():
        if item_id not in first:
            continue
        item, judge = by_id[item_id], first[item_id]
        assert judge['feature'] == item['feature']
        entries.append(item | {'judge': judge['raw_score'], 'humans': list(users.values()), 'human_by_user': users,
            'maximum': rubric['features'][item['feature']]['maximum'], 'expected_pct': judge['score_distribution']['available_expected_normalized_score_pct']})
    report = {'study': 'steering-human-audit-1.0', 'submitted_by_user': {u: counts[u] for u in USERS},
        'expected_human_ratings': 256, 'submitted_human_ratings': sum(counts.values()),
        'complete_human_pairs': sum(len(users) == 2 for users in labels.values()),
        'primary_judge_run': 'run-0 (fresh evaluation after sample freezing)',
        'repeatability': repeatability(manifest, repeats), 'agreement': {},
        'interpretation': 'Report representative and authored diagnostic sets separately when present. Authored diagnostics do not certify real steering performance. No success thresholds. Normalized scores are ordinal strength, not probabilities. CI resamples whole topic clusters; two raters are not two independent items. Logprob expectation uses available labels and is secondary.'}
    views = {'all_descriptive': entries}
    for part in ('representative', 'diagnostic'):
        views[part] = [e for e in entries if e['sample_part'] == part]
    for language in ('en', 'ru'):
        views['language/' + language] = [e for e in entries if e['language'] == language]
    for feature in FEATURES:
        views[feature] = [e for e in entries if e['feature'] == feature]
        for part in ('representative', 'diagnostic'):
            views[feature + '/' + part] = [e for e in views[feature] if e['sample_part'] == part]
        for language in ('en', 'ru'):
            views[feature + '/' + language] = [e for e in views[feature] if e['language'] == language]
    for user in USERS:
        views['annotator/' + user] = [e | {'humans': [e['human_by_user'][user]]} for e in entries if user in e['human_by_user']]
    for name, selected in views.items():
        report['agreement'][name] = agreement(selected) | bootstrap(selected, resamples, 20261008)
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default=str(DATA / 'exports/annotations.jsonl'))
    parser.add_argument('--manifest', default=str(DATA / 'private_manifest.jsonl'))
    parser.add_argument('--judge-repeats')
    parser.add_argument('--output', default=str(DATA / 'exports/audit_metrics.json'))
    parser.add_argument('--bootstrap', type=int, default=2000)
    args = parser.parse_args()
    assert args.bootstrap >= 100
    _, rubric, metadata = load_public()
    if args.judge_repeats is None:
        args.judge_repeats = str(DATA / metadata.get('judge_repeats_path', 'private/judge-repeats'))
    assert sha(args.manifest) == metadata['private_manifest_sha256']
    manifest = read_jsonl(args.manifest)
    for feature in FEATURES:
        frozen = [{'prompt_id': r['prompt_id'], 'answer_id': r['item_id'], 'scenario': r['scenario'], 'text': r['text']} for r in manifest if r['feature'] == feature]
        actual = read_jsonl(Path(args.judge_repeats).parent / ('final-' + feature + '.jsonl'))
        assert actual == frozen, 'Repeated Judge input differs from frozen human sample'
    annotations = read_jsonl(args.input) if Path(args.input).exists() else []
    report = analyze(annotations, manifest, load_repeats(args.judge_repeats, rubric['rubric_version']), metadata['public_sha256'], rubric, args.bootstrap)
    report['sample_version'] = metadata['study_version']
    report['study'] = 'steering-human-audit-' + metadata['study_version']
    report['sample_selection'] = metadata['selection']
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    rows = ''.join('<tr><td>' + html.escape(name) + '</td><td>' + str(r['complete_five_repeat_items']) + '</td><td>' + str(r['all_five_identical_pct']) + '</td><td>' + str(r['pairwise_exact_pct']) + '</td></tr>' for name, r in report['repeatability'].items())
    agreement_rows = ''.join('<tr><td>' + html.escape(name) + '</td><td>' + str(r['items']) + '</td><td>' + str(r.get('judge_human_exact_pct')) + '</td><td>' + str(r.get('judge_human_mae_pct')) + '</td><td>' + str(r.get('judge_human_bias_pct')) + '</td></tr>' for name, r in report['agreement'].items())
    output.with_suffix('.html').write_text('<!doctype html><meta charset="utf-8"><title>Judge human audit</title><style>body{font:16px system-ui;max-width:1100px;margin:40px auto}td,th{padding:8px;text-align:left;border-bottom:1px solid #ddd}table{border-collapse:collapse}</style><h1>Judge human audit</h1><p>Submitted human ratings: ' + str(report['submitted_human_ratings']) + '/256. Full confidence intervals and confusion matrices are in audit_metrics.json.</p><h2>Repeatability</h2><table><tr><th>Feature</th><th>Items with 5 runs</th><th>All runs identical (%)</th><th>Pairwise agreement (%)</th></tr>' + rows + '</table><h2>Human agreement</h2><table><tr><th>Sample</th><th>Items</th><th>Exact (%)</th><th>MAE (percentage points)</th><th>Judge − human (pp)</th></tr>' + agreement_rows + '</table>', encoding='utf-8')
    print(json.dumps({'submitted': report['submitted_human_ratings'], 'paired': report['complete_human_pairs'], 'output': str(output)}))

if __name__ == '__main__':
    main()

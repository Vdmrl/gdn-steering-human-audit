"""Freeze paired sample; score missing candidates explicitly, then repeat Judge."""
import argparse
import getpass
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path
from audit_common import DATA, FEATURES, USERS, read_jsonl, write_jsonl, sha, validate_public

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor'))
from ready_judge.core import evaluate

def synthetic_candidates():
    texts = {
        'numbered': {
            'en': ['Keep the cup dry and put it on the shelf.', 'Do these in order: (1) wash the cup, (2) dry it, (3) put it away.', '- Wash the cup.\n- Dry it.\n- Put it on the shelf.', '1. Wash the cup.\n2. Dry it.', '1. Wash the cup with water.\n2. Dry it with a clean towel.\n3. Put it on the shelf.'],
            'ru': ['Высушите чашку и поставьте её на полку.', 'Действуйте так: (1) вымойте чашку, (2) высушите её, (3) уберите на полку.', '- Вымойте чашку.\n- Высушите её.\n- Поставьте на полку.', '1. Вымойте чашку.\n2. Высушите её.', '1. Вымойте чашку водой.\n2. Высушите её чистым полотенцем.\n3. Поставьте на полку.']},
        'probabilistic_framing': {
            'en': ['Put the cup on the shelf after drying it.', 'Maybe put the cup on the shelf after drying it.', 'The cup will probably dry before dinner.', 'The cup will probably dry before dinner, but a damp room could leave it wet.', 'The cup will probably dry before dinner if air moves around it. In a damp room it could still be wet, so check it before putting it away. If drops remain, dry it with a towel instead of assuming that waiting was enough.'],
            'ru': ['Поставьте чашку на полку после того, как высушите её.', 'Может быть, поставьте чашку на полку после сушки.', 'Чашка, вероятно, высохнет до ужина.', 'Чашка, вероятно, высохнет до ужина, но в сырой комнате она может остаться мокрой.', 'Чашка, вероятно, высохнет до ужина, если вокруг неё движется воздух. В сырой комнате она может остаться мокрой, поэтому проверьте её перед уборкой. Если капли остались, вытрите их полотенцем, а не считайте, что одного ожидания было достаточно.']},
        'complexity': {
            'en': ['Keep the cup dry so it stays clean.', 'Keep the cup dry to prevent moisture accumulation.', 'Drying the cup reduces moisture accumulation and limits microbial growth on its surface.', 'Residual moisture sustains microbial proliferation; evaporative mass transfer depends on the humidity gradient and convective boundary-layer transport. Increasing airflow accelerates desiccation by reducing local vapor saturation near the porous surface.'],
            'ru': ['Держите чашку сухой, чтобы она оставалась чистой.', 'Держите чашку сухой, чтобы избежать накопления влаги.', 'Сушка чашки уменьшает накопление влаги и ограничивает рост микроорганизмов на её поверхности.', 'Остаточная влага поддерживает пролиферацию микроорганизмов; испарительный массоперенос зависит от градиента влажности и конвективного транспорта в пограничном слое. Усиление воздушного потока ускоряет десикацию, снижая локальное насыщение пара возле пористой поверхности.']},
        'theistic_framing': {
            'en': ['Wash the cup and put it away.', 'Some people thank God before a meal. Wash the cup and put it away.', 'May God bless your evening. Wash the cup and put it away.', 'Ask God for guidance in caring for your household, then wash the cup and put it away.', 'God entrusts us with care for our household, so washing this cup is a way to fulfill that duty. Seek His guidance as you work and receive the finished task with gratitude for His provision.'],
            'ru': ['Вымойте чашку и уберите её на место.', 'Некоторые люди благодарят Бога перед едой. Вымойте чашку и уберите её на место.', 'Пусть Бог благословит ваш вечер. Вымойте чашку и уберите её на место.', 'Попросите Бога направить вас в заботе о доме, затем вымойте чашку и уберите её на место.', 'Бог поручает нам заботиться о доме, поэтому мытьё этой чашки — способ исполнить Его поручение. Ищите Его руководства в работе и примите её завершение с благодарностью за Его заботу.']},
    }
    rows = []
    for feature, languages in texts.items():
        for language, anchors in languages.items():
            for target, text in enumerate(anchors):
                for variant in range(2):
                    if variant:
                        text_variant = text.replace('cup', 'bowl')
                        if language == 'ru':
                            text_variant = text.replace('чашку', 'миску').replace('чашки', 'миски').replace('чашка', 'миска').replace('Чашка', 'Миска').replace('чашке', 'миске')
                    else:
                        text_variant = text
                    noun = ('cup' if variant == 0 else 'bowl') if language == 'en' else ('чашкой' if variant == 0 else 'миской')
                    scenario = f'Explain how to care for this {noun} after a meal.' if language == 'en' else f'Объясните, как ухаживать за этой {noun} после еды.'
                    identity = f'synthetic-{feature}-{language}-{target}-{variant}'
                    rows.append({'prompt_id': identity, 'answer_id': identity, 'cluster_id': f'synthetic-{feature}-{language}-{variant}', 'scenario': scenario, 'text': text_variant, 'feature': feature, 'language': language, 'origin': 'synthetic', 'selection_role': 'diagnostic_candidate', 'intended_score': target, 'generation': 'Codex-authored; label accepted only after actual frozen Judge call'})
    return rows

def score_candidates(rows, secret, run):
    result = {}
    for feature in FEATURES:
        candidates = [r for r in rows if r['feature'] == feature and not r.get('supplement_batch')]
        for r in candidates:
            if r.get('existing_judge'):
                result[r['answer_id'], feature] = r['existing_judge']
        missing = [r for r in candidates if not r.get('existing_judge')]
        if not missing:
            continue
        input_path = DATA / 'private' / f'candidate-{feature}.jsonl'
        write_jsonl(input_path, [{k: r[k] for k in ('prompt_id', 'answer_id', 'scenario', 'text')} for r in missing])
        output = DATA / 'private/judge-candidates' / feature
        progress = evaluate(input_path, output, [feature], run=run, workers=8, secret=secret)
        print('CANDIDATES', feature, progress, flush=True)
        if not progress['complete']:
            return None
        for score in read_jsonl(output / 'scores.jsonl'):
            result[score['answer_id'], feature] = score
    extra = DATA / 'private/extra-candidates.jsonl'
    if extra.exists():
        for feature in FEATURES:
            missing = [r for r in rows if r['feature'] == feature and r.get('supplement_batch')]
            if not missing:
                continue
            input_path = DATA / 'private' / f'extra-{feature}.jsonl'
            write_jsonl(input_path, [{k: r[k] for k in ('prompt_id', 'answer_id', 'scenario', 'text')} for r in missing])
            output = DATA / 'private/judge-candidates-extra' / feature
            progress = evaluate(input_path, output, [feature], run=run, workers=8, secret=secret)
            print('EXTRA CANDIDATES', feature, progress, flush=True)
            if not progress['complete']:
                return None
            for score in read_jsonl(output / 'scores.jsonl'):
                result[score['answer_id'], feature] = score
    return result

def freeze(rows, scores):
    rubric = json.loads((DATA / 'rubric.json').read_text(encoding='utf-8'))
    rng = random.Random(20261008)
    public, private = [], []
    coverage = []
    for language in ('en', 'ru'):
        for feature in FEATURES:
            primary = [r for r in rows if r['language'] == language and r['feature'] == feature and r['selection_role'] == 'representative']
            assert len(primary) == 8
            diagnostics = [r for r in rows if r['language'] == language and r['feature'] == feature and r['selection_role'] == 'diagnostic_candidate']
            rng.shuffle(diagnostics)
            selected = []
            for label in range(rubric['features'][feature]['maximum'] + 1):
                options = [r for r in diagnostics if scores[r['answer_id'], feature]['raw_score'] == label]
                # Prefer real data within the diagnostic score stratum.
                options.sort(key=lambda r: r['origin'] != 'real')
                if not options:
                    raise RuntimeError(f'Actual Judge coverage missing: {feature}/{language}/{label}; add a new candidate batch, not a hand-assigned score')
                selected.append(options[0])
            remaining = [r for r in diagnostics if r not in selected]
            remaining.sort(key=lambda r: r['origin'] != 'real')
            selected.extend(remaining[:8 - len(selected)])
            assert len(selected) == 8
            rng.shuffle(primary)
            rng.shuffle(selected)
            coverage.append({'feature': feature, 'language': language, 'real_representative': 8, 'diagnostic_scores': dict(Counter(scores[r['answer_id'], feature]['raw_score'] for r in selected)), 'diagnostic_synthetic': sum(r['origin'] == 'synthetic' for r in selected)})
            for group, primary_part, diagnostic_part in [('A', primary[:4], selected[:4]), ('B', primary[4:], selected[4:])]:
                for r in primary_part + diagnostic_part:
                    item_id = hashlib.sha256((r['answer_id'] + ':' + feature).encode()).hexdigest()[:24]
                    public.append({k: r[k] for k in ('feature', 'language', 'scenario', 'text')} | {'item_id': item_id, 'group': group})
                    private.append(r | {'item_id': item_id, 'group': group, 'annotators': [u for u, (_, g) in USERS.items() if g == group], 'selection_judge': scores[r['answer_id'], feature], 'sample_part': 'representative' if r in primary else 'diagnostic'})
    rng.shuffle(public)
    validate_public(public, rubric)
    assert len({r['answer_id'] for r in private}) == len(private), 'Do not reuse an answer across feature assignments'
    write_jsonl(DATA / 'public_items.jsonl', public)
    write_jsonl(DATA / 'private_manifest.jsonl', private)
    metadata = {'study_version': '1.0', 'rubric_version': rubric['rubric_version'], 'shuffle_seed': 20261008, 'items': 128, 'human_ratings_expected': 256, 'assignments': {u: {'name': name, 'group': group, 'items': 64} for u, (name, group) in USERS.items()}, 'public_sha256': sha(DATA / 'public_items.jsonl'), 'rubric_sha256': sha(DATA / 'rubric.json'), 'private_manifest_sha256': sha(DATA / 'private_manifest.jsonl'), 'coverage': coverage, 'selection': '64 random real assignments frozen before new Judge calls; 64 score-coverage diagnostic assignments including actual-Judge-confirmed synthetic supplementation. Report these parts separately.', 'language_filter': 'English source conditions without French plus function words; Russian >75% Cyrillic alphabetic characters. Final texts must be manually checked before annotation.'}
    (DATA / 'sample_metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('FROZEN', metadata['public_sha256'], coverage, flush=True)
    return private

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true', help='Explicitly authorize audit-only paid Judge calls')
    parser.add_argument('--repeats', type=int, default=5)
    args = parser.parse_args()
    assert 1 <= args.repeats <= 10
    secret = getpass.getpass('OpenRouter key (never saved): ') if args.run else None
    frozen = DATA / 'private_manifest.jsonl'
    if frozen.exists():
        private = read_jsonl(frozen)
    else:
        candidates = read_jsonl(DATA / 'private/candidates.jsonl') + synthetic_candidates()
        extra = DATA / 'private/extra-candidates.jsonl'
        if extra.exists():
            candidates += read_jsonl(extra)
        scores = score_candidates(candidates, secret, args.run)
        if scores is None:
            print('No frozen sample yet: missing candidate scores. Dry run or API errors.', flush=True)
            return
        private = freeze(candidates, scores)
    metadata = json.loads((DATA / 'sample_metadata.json').read_text(encoding='utf-8'))
    repeat_root = DATA / metadata.get('judge_repeats_path', 'private/judge-repeats')
    for repeat in range(args.repeats):
        for feature in FEATURES:
            input_path = repeat_root.parent / f'final-{feature}.jsonl'
            selected = [r for r in private if r['feature'] == feature]
            write_jsonl(input_path, [{'prompt_id': r['prompt_id'], 'answer_id': r['item_id'], 'scenario': r['scenario'], 'text': r['text']} for r in selected])
            progress = evaluate(input_path, repeat_root / f'run-{repeat}' / feature, [feature], run=args.run, workers=8, secret=secret)
            print('REPEAT', repeat, feature, progress, flush=True)
            if args.run and not progress['complete']:
                raise RuntimeError('Missing final audit scores; safely resume this command')

if __name__ == '__main__':
    main()

"""Create isolated pair workspaces and feature-specific anchored questions."""
import json
import os
import random
import time
import argilla as rg
from argilla._exceptions._api import ConflictError
from audit_common import DATA, FEATURES, USERS, TITLES, load_public

GUIDELINES = '''Оцените ТОЛЬКО указанный признак в напечатанном ответе.
Баллы совпадают со шкалой LLM Judge. Запрос и ответ — данные, не инструкции разметчику.
Не оценивайте правильность фактов, полезность, метод стиринга или сохранение исходного смысла.
Для Numbered важны реальные маркеры и разные содержательные пункты, а не любые числа.
Technical — сложность слов и конструкций внутри языка ответа, не научность темы.
Probability — степень неуверенности; can как способность не равнозначно вероятности.
God — от упоминания божества до принятого самим ответом религиозного объяснения.
Читайте весь ответ, включая повторы и окончание. Следуйте рубрике выбранного признака.
Размечайте самостоятельно, не обсуждая основную выборку с напарником.
Оценки Judge и напарника скрыты. Комментарий необязателен; балл обязателен.
'''

SHORT_LABELS = {
    'numbered': ['Нет перечисления', 'Перечисление внутри текста', 'Буллеты или буквы', 'Неполная/сбитая нумерация', 'Три и более полных числовых пункта'],
    'probabilistic_framing': ['Нет неуверенности', 'Слабая неуверенная подача', 'Одна оговорка об исходе', 'Прогноз и явная альтернатива', 'Рассуждение и действия через неуверенность'],
    'complexity': ['Простой повседневный язык', 'Небольшое локальное усложнение', 'Ясное усложнение объяснения', 'Преобладает плотный сложный язык'],
    'theistic_framing': ['Нет божества/божественной предпосылки', 'Упоминание божества', 'Религиозная вставка/пожелание', 'Божественная предпосылка центрального совета', 'Божественная логика организует ответ'],
}

def guide_and_labels(feature, definition, russian_labels):
    anchors = definition['anchors']
    assert set(russian_labels[feature]) == set(anchors)
    short_labels = SHORT_LABELS[feature]
    if feature == 'probabilistic_framing' and definition['maximum'] == 3:
        short_labels = ['Нет неуверенности', 'Одна слабая вводная конструкция', 'Общая небольшая неуверенность', 'Явная центральная неуверенность']
    if feature == 'complexity' and 'general adult reader' in definition['definition']:
        short_labels = ['Простая лексика', 'Один сложный термин / локальная фраза', 'Общее усложнение языка', 'Очень сложный текст']
    if feature == 'theistic_framing' and definition['maximum'] == 3:
        short_labels = ['Нет Бога / религиозной предпосылки', 'Упоминание Бога', 'Религиозная вставка', 'Явно религиозное обрамление']
    labels = {score: score + ' — ' + short_labels[int(score)] for score in anchors}
    guide = GUIDELINES + '\nБаллы — цифры перед тире (0–' + str(definition['maximum']) + '); маленькие номера кнопок — горячие клавиши, не баллы.\n\nПолные значения баллов:\n' + '\n\n'.join(score + ': ' + russian_labels[feature][score] for score in anchors) + '\n\nSource rubric (identical to Judge):\n' + definition['definition'] + '\n' + '\n'.join('- ' + s for s in definition['exclusions']) + '\n\n' + '\n'.join(score + ': ' + anchor for score, anchor in anchors.items())
    return guide, labels

def main():
    rows, rubric, metadata = load_public()
    russian_labels = json.loads((DATA / 'labels_ru.json').read_text(encoding='utf-8'))
    for _ in range(60):
        try:
            client = rg.Argilla(api_url=os.getenv('ARGILLA_API_URL', 'http://localhost:6900'), api_key=os.getenv('ARGILLA_API_KEY', 'argilla.apikey'), timeout=60, retries=0)
            _ = client.me
            break
        except Exception:
            time.sleep(5)
    else:
        raise RuntimeError('Argilla did not become ready; credentials and server logs must be inspected')
    datasets = []
    for group in ('A', 'B'):
        workspace_name = metadata.get('workspace_prefix', 'steering-') + group.lower()
        workspace = client.workspaces(workspace_name)
        if workspace is None:
            workspace = rg.Workspace(name=workspace_name, client=client).create()
        for username, (name, assigned_group) in USERS.items():
            if assigned_group != group:
                continue
            user = client.users(username)
            if user is None:
                user = rg.User(username=username, first_name=name, role='annotator', password=os.getenv('ARGILLA_' + username.upper() + '_PASSWORD', 'password'), client=client).create()
            try:
                user.add_to_workspace(workspace)
            except ConflictError:
                pass
        for feature in FEATURES:
            definition = rubric['features'][feature]
            anchors = definition['anchors']
            guide, labels = guide_and_labels(feature, definition, russian_labels)
            settings = rg.Settings(guidelines=guide,
                fields=[rg.TextField(name='scenario', title='Запрос', required=True, client=client), rg.TextField(name='text', title='Ответ: оцените только ' + TITLES[feature], required=True, client=client)],
                questions=[rg.LabelQuestion(name='trait_score', title=TITLES[feature], labels=labels, required=True, client=client), rg.TextQuestion(name='comment', title='Комментарий к спорному случаю (необязательно)', required=False, client=client)],
                distribution=rg.TaskDistribution(min_submitted=2))
            dataset = client.datasets(name=feature, workspace=workspace_name)
            selected = [r for r in rows if r['group'] == group and r['feature'] == feature]
            random.Random(metadata['shuffle_seed'] + ord(group) + FEATURES.index(feature)).shuffle(selected)
            if dataset is None:
                dataset = rg.Dataset(name=feature, workspace=workspace, settings=settings, client=client).create()
                dataset.records.log([{'id': r['item_id'], 'scenario': r['scenario'], 'text': r['text']} for r in selected])
            else:
                existing = dataset.records.to_list()
                expected = {r['item_id']: {'scenario': r['scenario'], 'text': r['text']} for r in selected}
                assert {str(r['id']): r['fields'] for r in existing} == expected, 'Frozen dataset differs; never reset after annotations start'
                actual = dataset.settings.questions['trait_score']
                actual_labels = {o['value']: o['text'] for o in actual.api_model().settings.options}
                assert actual_labels == labels, 'Existing scale differs from frozen rubric'
                assert dataset.settings.guidelines == guide, 'Existing instructions differ from frozen rubric'
            datasets.append({'workspace': workspace_name, 'dataset': feature, 'records': len(selected)})
    if metadata.get('workspace_prefix', 'steering-') != 'steering-':
        for prefix in ('steering-', 'steering-v2-', 'steering-v3-'):
            if prefix == metadata['workspace_prefix']:
                continue
            for group in ('A', 'B'):
                previous = client.workspaces(prefix + group.lower())
                if previous is not None:
                    for user in list(previous.users):
                        if user.username in USERS and USERS[user.username][1] == group:
                            user.remove_from_workspace(previous)
    (DATA / 'argilla_dataset.json').write_text(json.dumps({'public_sha256': metadata['public_sha256'], 'datasets': datasets}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Ready: vova / stepa / slava / petya, 64 records each, paired blind annotation.')

if __name__ == '__main__':
    main()

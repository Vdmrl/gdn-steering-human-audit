"""Select an annotator, start the existing Argilla stack and open its login."""
import argparse
import subprocess
import webbrowser
from pathlib import Path

USERS = [('vova', 'Вова'), ('stepa', 'Стёпа'), ('slava', 'Слава'), ('petya', 'Петя')]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--user', choices=[user for user, _ in USERS])
    parser.add_argument('--no-start', action='store_true')
    args = parser.parse_args()
    user = args.user
    while user is None:
        print('\nВыберите разметчика:')
        for index, (_, name) in enumerate(USERS, 1):
            print(f'{index}. {name}')
        choice = input('Номер 1–4: ').strip()
        if choice in ('1', '2', '3', '4'):
            user = USERS[int(choice) - 1][0]
    if not args.no_start:
        subprocess.run(['docker', 'compose', 'up', '-d', 'argilla', 'worker', 'postgres', 'elasticsearch', 'redis'], cwd=Path(__file__).resolve().parent, check=True)
        subprocess.run(['docker', 'compose', 'run', '--rm', '--build', 'setup'], cwd=Path(__file__).resolve().parent, check=True)
    print(f'Войдите в Argilla как {user}. Локальный пароль по умолчанию: password (можно изменить через .env).')
    print('Вам доступны только ваши 64 задания: четыре набора по 16. Оценки напарника и Judge скрыты.')
    webbrowser.open('http://localhost:6900')

if __name__ == '__main__':
    main()

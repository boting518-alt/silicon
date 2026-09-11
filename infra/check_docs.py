"""Current-task checks; historical TASK-000 assertions remain historical."""
import hashlib
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
config = json.loads((root/'runtime/project.json').read_text())
assert config['current_task'] == 'TASK-009'
assert config['status'] in {'executing', 'review_ready'}
for path in config['paths'].values():
    assert not Path(path).is_absolute() and (root/path).is_dir(), path
assert 'status: accepted' in (root/'docs/tasks/TASK-000/task.md').read_text()
assert 'status: accepted' in (root/'docs/tasks/TASK-008/task.md').read_text()
current_task = root/'docs/tasks/TASK-009/task.md'
assert f"status: {config['status']}" in current_task.read_text()
assert '当前只执行已明确分配的 TASK-009' in (root/'AGENTS.md').read_text()
assert 'status: accepted' in (root/'docs/tasks/TASK-002/task.md').read_text()
assert 'status: accepted' in (root/'docs/tasks/TASK-001/task.md').read_text()
assert 'status: accepted' in (root/'docs/tasks/TASK-003/task.md').read_text()
assert 'status: accepted' in (root/'docs/tasks/TASK-004/task.md').read_text()
assert 'status: accepted' in (root/'docs/tasks/TASK-005/task.md').read_text()
assert 'status: accepted' in (root/'docs/tasks/TASK-007/task.md').read_text()
for name, digest in {
 'TASK-009-c08079e-review.md': '78c6ff2612eda32ed2230e034d445c46ee33cfcb21768a6d43088f2b7973bcad',
 'TASK-008-b56ed65-review.md': 'e60e48a6175fc7f2517ab56ae9a4555117a3c69e55291b6474c0fb72167213b0',
 'TASK-008-dd4031f-review.md': 'df954797318527495b7cf0b5eaa966740f85422e9d45247f6f80e0fc5f7deaad',
 'TASK-007-4802fcc-review.md': '713038cfbec303e650904470326a1cf3b1e64c5602d2b8bc0ff0d63261d496a7',
 'TASK-007-732089f-review.md': 'fc607a71ccad6119daf7258a11b9069f252adabd4b96998ac27e82ca93cf703e',
 'TASK-006-59f55c8-review.md': '1da78889525f4dfedd870724f8732a73cd287fb6caae40299166b20adb3d568a',
 'TASK-005-da215ad-review.md': 'f8ecc6536a9a8c3d35acbac5dfb46a660d0f2db4494f1c8801cdba94637ae3b3',
 'TASK-005-6d2a818-review.md': '1a27276947e33b2044a46ed091cb7741b1b251c3687324cd5933a94e5e4ea788',
 'TASK-004-a8ce3e2-review.md': '5d8b40dbf106c64401c330aa85937556b5e0c1502337bc8e09fdde69d92cb442',
 'TASK-004-1d627b1-review.md': 'bd5f932eb7144d799f1b56e4307c8c7ea528b67b11e5bcdfb8987fea6b509531',
 'TASK-003-a6b640e-review.md': '38e06323f15a9113420bc0a4088f03df3300f68db4556c3701350cb838b8d221',
 'TASK-003-45453c7-review.md': '3a5fba49d08d6f87bb90501ef52edea1b212aca14a1d5cd1bc517c7634eb0170',
 'TASK-002-9936743-review.md': '65c01e11f572499f061f1008b5ce6d2a9d9cd5d86c1797f0e7fdfe4726dcf9f5',
 'TASK-001-c50a951-review.md': '1beb182690c5aeb003e8105061613995caa76ee7f83a74eaffc40d9bb7452a70',
 'TASK-001-8b7cf4a-review.md': '57ad643e89edab14558aed19a7e499c1396781ab0b46060bda59bbb2e06e1dce',
 'TASK-000-91ac217-review.md': 'a5ccfd9404ad303cf790bbea912933868f3297aa24119b2986b54507076087a3',
 'TASK-000-88e3044-review.md': '84da45e54b6f844d60365e012ee9edf802cc877b185e0d5ea2db2ec904cb1c81'
}.items():
    assert hashlib.sha256((root/'docs/reviews'/name).read_bytes()).hexdigest() == digest
count = 0
for file in [root/'README.md', root/'AGENTS.md', *list((root/'docs').rglob('*.md'))]:
    if file.name.startswith('._'): continue
    content = re.sub(r'```.*?```','',file.read_text(),flags=re.S)
    for link in re.findall(r'\]\(([^)]+)\)',content):
        if '://' in link or link.startswith(('#','sandbox:')):continue
        assert (file.parent/link.split('#')[0]).exists(), (file, link)
        count += 1
print(f'PASS task handoff/state, relative paths, unchanged reviews, {count} local links')

assert 'status: accepted' in (root/'docs/tasks/TASK-006/task.md').read_text()

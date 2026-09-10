"""Current-task checks; historical TASK-000 assertions remain historical."""
import hashlib
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
config = json.loads((root/'runtime/project.json').read_text())
assert config['current_task'] == 'TASK-004'
assert config['status'] in {'executing', 'review_ready'}
for path in config['paths'].values():
    assert not Path(path).is_absolute() and (root/path).is_dir(), path
assert 'status: accepted' in (root/'docs/tasks/TASK-000/task.md').read_text()
assert f"status: {config['status']}" in (root/'docs/tasks/TASK-004/task.md').read_text()
assert '当前只执行已明确分配的 TASK-004' in (root/'AGENTS.md').read_text()
assert 'status: accepted' in (root/'docs/tasks/TASK-002/task.md').read_text()
assert 'status: accepted' in (root/'docs/tasks/TASK-001/task.md').read_text()
assert 'status: accepted' in (root/'docs/tasks/TASK-003/task.md').read_text()
for name, digest in {
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
        if '://' in link or link.startswith('#'):continue
        assert (file.parent/link.split('#')[0]).exists(), (file, link)
        count += 1
print(f'PASS task handoff/state, relative paths, unchanged reviews, {count} local links')

"""Current-task checks; historical TASK-000 assertions remain historical."""
import hashlib
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
config = json.loads((root/'runtime/project.json').read_text())
assert config['current_task'] == 'TASK-001'
assert config['status'] in {'executing', 'review_ready'}
for path in config['paths'].values():
    assert not Path(path).is_absolute() and (root/path).is_dir(), path
assert 'status: accepted' in (root/'docs/tasks/TASK-000/task.md').read_text()
assert f"status: {config['status']}" in (root/'docs/tasks/TASK-001/task.md').read_text()
assert '当前只执行已明确分配的 TASK-001' in (root/'AGENTS.md').read_text()
assert 'status: planned' in (root/'docs/tasks/TASK-002/task.md').read_text()
for name, digest in {
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

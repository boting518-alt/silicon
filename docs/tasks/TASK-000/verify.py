"""Read-only TASK-000 documentation and source checks; run from repository root."""
from pathlib import Path, PurePosixPath
import hashlib, json, re, subprocess
root=Path.cwd()
required=['README.md','AGENTS.md','runtime/project.json','docs/product/scope.md','docs/design/demo-baseline.md','docs/design/source-manifest.json','docs/architecture/architecture.md','docs/architecture/data-model.md','docs/architecture/api-conventions.md','docs/architecture/agent-policy.md','docs/architecture/metrics.md','docs/architecture/open-decisions.md','docs/tasks/backlog.md','docs/tasks/TASK-000/result.md']+[f'docs/architecture/adr/ADR-{i:03d}.md' for i in range(1,5)]+[f'docs/tasks/TASK-{i:03d}/task.md' for i in range(4)]
for name in required: assert (root/name).is_file(),name
print('PASS required documents:',len(required))
config=json.loads((root/'runtime/project.json').read_text())
assert config['current_task']=='TASK-000' and config['status']=='review_ready'
assert config['path_base']=='repository_root'
for p in list(config['paths'].values())+[x['path'] for x in config['demo_references'].values()]:
 assert not PurePosixPath(p).is_absolute() and not re.match(r'^[A-Za-z]:',p),p
assert not config['deployment']['configured']
for n in range(1,4):
 text=(root/f'docs/tasks/TASK-{n:03d}/task.md').read_text()
 assert f'TASK-{n:03d}' in text and 'status: planned' in text
 assert f'TASK-{n:03d}' in (root/'docs/tasks/backlog.md').read_text()
print('PASS relative configuration, task IDs, status and deployment boundary')
links=0
for f in root.rglob('*.md'):
 if f.name.startswith('._'):continue
 text=re.sub(r'```.*?```','',f.read_text(),flags=re.S)
 for link in re.findall(r'\]\(([^)]+)\)',text):
  if '://' in link or link.startswith('#'):continue
  target=link.split('#')[0]
  assert (f.parent/target).exists(),f'{f.relative_to(root)}: {link}'
  links+=1
print('PASS local Markdown links:',links)
manifest=json.loads((root/'docs/design/source-manifest.json').read_text())
js=assets=files=0
for ref in manifest['sources']:
 p=(root/ref['path']).resolve()
 def git(*args):return subprocess.check_output(['git','-C',str(p),*args],stderr=subprocess.DEVNULL)
 assert git('rev-parse','HEAD').decode().strip()==ref['commit']
 assert not git('status','--porcelain','--untracked-files=no').strip()
 assert json.loads((p/'.openai/hosting.json').read_text())['project_id']==ref['project_id']
 for item in ref['files']:
  f=p/item['path']; data=f.read_bytes()
  assert hashlib.sha256(data).hexdigest()==item['sha256']
  assert data==git('show','HEAD:'+item['path']); files+=1
  if f.suffix=='.js':
   subprocess.run(['node','--check',str(f)],check=True,capture_output=True);js+=1
   assert not re.search(r'\b(fetch\s*\(|XMLHttpRequest|localStorage|indexedDB)',data.decode()),f
  if f.suffix=='.html':
   for asset in re.findall(r'(?:src|href)="([^"]+)"',data.decode()):
    if asset.startswith(('#','http:','https:','mailto:')):continue
    target=f.parent/asset
    assert target.is_file() or (target.is_dir() and (target/'index.html').is_file()),asset;assets+=1
 css=(p/'dist/style.css').read_text()
 for color in ['#f5f7f8','#202e2d']:assert color in css
 if ref['name']=='workspace':
  for color in ['#254f3d','#244d3e','#eaf3ed','#e0e7e2']:assert color in css
 else:assert '#214f3c' in css and '#edf3ef' in css
print(f'PASS Demo commits/identities, {files} file hashes/blob comparisons, tracked trees clean')
print(f'PASS JavaScript syntax: {js}; HTML local asset references: {assets}; token values; no detected persistence entrypoints')
print('NOT_RUN browser/visual/E2E, static HTTP serving, app build, PostgreSQL/Worker tests: outside TASK-000')

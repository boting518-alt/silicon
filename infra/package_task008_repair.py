"""Export committed TASK-008 review source; refuse dirty trees or unsafe materials."""
import argparse,gzip,hashlib,io,json,re,subprocess,tarfile,tempfile,zipfile
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--implementation',required=True)
p.add_argument('--destination',type=Path,required=True)
args=p.parse_args()
repo=Path(__file__).resolve().parents[1]
def git(*parts):return subprocess.check_output(['git',*parts],cwd=repo)
base='dd4031fb6950e28446855131642cc01e54095991'
handoff=base
implementation=git('rev-parse',args.implementation).decode().strip()
head=git('rev-parse','HEAD').decode().strip()
for a,b in [(base,handoff),(handoff,implementation),(implementation,head)]:
    subprocess.run(['git','merge-base','--is-ancestor',a,b],cwd=repo,check=True)
status=git('status','--porcelain=v1','--untracked-files=all')
assert not status,'Inspect and preserve uncommitted files before exporting'
assert not args.destination.exists(),'Never overwrite a prior review package'
def extract(commit,destination):
    with tarfile.open(fileobj=io.BytesIO(git('archive',commit))) as archive:
        for m in archive:
            assert not m.issym() and not m.islnk(),m.name
            for part in Path(m.name).parts:
                assert part not in {'.git','.tools','.venv','node_modules','__MACOSX'} and not part.startswith('._'),m.name
                assert not (part.startswith('.env') and part!='.env.example'),m.name
        archive.extractall(destination,filter='data')
with tempfile.TemporaryDirectory(prefix='silicon-task008-review-') as temporary:
    root=Path(temporary);source=root/'source';source.mkdir();extract(head,source)
    changes=root/'changes';changes.mkdir()
    for label,a,b in [('base-to-final',base,head),('review-to-implementation',handoff,implementation),('implementation-to-final',implementation,head)]:
        for suffix,command in [('patch',['diff','--binary','--full-index',a,b]),('log.txt',['log','--format=fuller','--reverse',a+'..'+b]),('changed-files.txt',['diff','--name-status',a,b]),('stat.txt',['diff','--stat',a,b])]:
            (changes/(label+'.'+suffix)).write_bytes(git(*command))
    (changes/'worktree-status.txt').write_bytes(status)
    for name in ['AGENTS.md','docs/tasks/backlog.md','docs/tasks/TASK-008/task.md']:
        dest=changes/'review-base'/name;dest.parent.mkdir(parents=True,exist_ok=True)
        result=subprocess.run(['git','show',base+':'+name],cwd=repo,capture_output=True)
        if result.returncode==0:dest.write_bytes(result.stdout)
        else:dest.with_suffix('.absent.txt').write_text(f'{name} absent at {base}\n')
    evidence=root/'evidence';evidence.mkdir()
    (evidence/'INDEX.md').write_text('''# Evidence index

All evidence is in the complete committed source, without duplicate copies.

- [Result](../source/docs/tasks/TASK-008/result.md)
- [Repair validation](../source/docs/tasks/TASK-008/evidence/r1-r2/validation.json)
- [Repair browser evidence](../source/docs/tasks/TASK-008/evidence/r1-r2/browser-notes.md)
- [Repair screenshots](../source/docs/tasks/TASK-008/evidence/r1-r2/screenshots.json)
- [Original review](../source/docs/reviews/TASK-008-dd4031f-review.md)
- [Historical validation](../source/docs/tasks/TASK-008/evidence/validation.json)
- [Browser reproduction and limitations](../source/docs/tasks/TASK-008/browser-acceptance.md)
- [Screenshot files, dimensions and checksums](../source/docs/tasks/TASK-008/evidence/screenshots.json)
- [ADR-013](../source/docs/architecture/adr/ADR-013.md)
- [Original visual inheritance](../source/docs/design/demo-baseline.md)

Raw test logs, compressed exact originals where whitespace normalization was necessary, browser observations, fictional CSVs and JPEGs are under TASK-008/evidence. All earlier review reports, results and visual evidence remain in source. Original Demo checkouts are read-only external references, not runtime dependencies.
''')
    (root/'REVIEW_MANIFEST.md').write_text(f'''# SILICON TASK-008 R1/R2 incremental review package

Status: review_ready. No independent acceptance implied. TASK-009 remains planned.

- Repair review base: {base}
- Original accepted base: 4802fcccb739fa89cada3be5179e21e0066121a0
- Original handoff: 0992ffbf6da59ea7237d20aeac2d9c3cb6e7e9ab
- Implementation/evidence: {implementation}
- Final HEAD: {head}
- Branch: {git('branch','--show-current').decode().strip()}
- Packaging worktree: clean; all ancestry relationships verified.

source/ is the entire git archive of final HEAD, not only changed files. changes/ contains complete binary patches, changed-files, stats and logs for the three named ranges. review-base/ contains AGENTS/backlog/task from the repair review base. evidence/ indexes source files; screenshots and original logs are physically included under source. SHA256SUMS excludes only itself. PACKAGE_CHECKS.json records exact blob/diff replay and archive checks.

## Reproduce from source directory

Use Node24.15.0/npm11.12.1, Python3.12.7, uv0.12.11, PostgreSQL17.11, Java21.0.6, Keycloak26.7.3. Actual local version output and exact test commands/results are in source/docs/tasks/TASK-008/evidence/environment.json and validation.json. No dependency upgrade was performed. Full final backend, Node, component substitutes, true browser and not_run items are distinguished in result.md; read those rather than inferring success from a script's presence.

```bash
cd source
npm ci --ignore-scripts
uv sync --locked
npm run typecheck
npm run build
# Run only repository test files; exclude AppleDouble companion names.
node --test $(git ls-files 'apps/web/tests/*.test.ts')
.venv/bin/python infra/export_openapi.py
npm run api:types
.venv/bin/python infra/check_docs.py
```

Install Java21.0.6 in your own test environment and expose it through JAVA_HOME/PATH. No global identity or SSH change required. Use already available verified PG17.11 binaries via PG17_HOME, or build verified source; do not start or bootstrap a resident server:

```bash
.venv/bin/python infra/build_test_postgres.py --prefix "$PWD/.tools/review-pg17"
export PG17_HOME="$PWD/.tools/review-pg17"
.venv/bin/python infra/fetch_keycloak.py --destination .tools/keycloak
export KEYCLOAK_HOME="$PWD/.tools/keycloak/keycloak-26.7.3"
export SILICON_TEST_PG_BIN="$PG17_HOME/bin"
export SILICON_TEST_KEYCLOAK_HOME="$KEYCLOAK_HOME"
.venv/bin/python -m pytest apps/api/tests/test_inventory_files.py -q
.venv/bin/python -m pytest apps/api/tests -q
```

Fetch script verifies Keycloak SHA256 77657f30b7e90d70f727712ce1c967f430fd6a5e9f458d32d8c6df0635345f47; PG script verifies source. Existing installation destinations aren't overwritten. Test fixture owns initdb, loopback random port, migration/runtime roles, fictional identities/data, private temp files and cleanup. Real runtime silicon_app is neither owner, superuser nor BYPASSRLS. Empty0009 migration and0008->0009 signed-contract retention are tested; old-schema setup uses a real downgrade/upgrade with preserved prior data, not an old executable checkout. Tests do not use README resident createdb instructions. OIDC fixture creates and trusts its own CA with hostname checks, never verify=False.

### Browser

Finish full backend before starting browser IdP. Provide a legitimately available `.tools/visual/PingFang.ttc` matching the script's documented SHA256; not distributed here. Generate local TLS via `.venv/bin/python infra/dev_tls.py .tools/tls` only if missing, then obtain explicit browser SSL trust authorization on the review machine; generating a file does not install trust. Never copy another machine's private key or ignore certificate errors. This implementation did not change certificate trust.

```bash
SILICON_BROWSER_INVENTORY_REPAIR=1 SILICON_BROWSER_INVENTORY=1 SILICON_BROWSER_CONTRACTS=1 SILICON_BROWSER_CATALOG=1 SILICON_BROWSER_CATALOG_SEED=1 .venv/bin/python infra/browser_stack.py
```

Open https://localhost:5173. Follow source/docs/tasks/TASK-008/evidence/r1-r2/browser-notes.md; original browser-acceptance.md remains historical evidence. Fictional alice/Fictional-alice-17! is Aadmin/Bviewer; explicit inventory seed makes carol/Fictional-carol-17! a warehouse member. The opt-in repair fixture creates fictional procurement sources, an attachment-free draft and closed opening inventory; these are setup, not browser actions. Use infra/create_inventory_test_csv.py with the newly created location UUID and saved cutoff. Component page /tests/inventory-component.html uses HTTP substitutes and is not production entry or real database evidence. Ctrl-C/SIGTERM stops only owned test processes and prints BROWSER_STACK_CLEANED.

## Limits and excluded materials

No .env, real credentials/customer data, private keys, active sessions/tokens, database files/backups, dependency directories, .tools, .git or AppleDouble. .env.example, locked dependencies, all tracked scripts/CI/migrations/tests, fictional fixtures and screenshots retained. Original Demo checkouts in runtime/project.json are external read-only sources; independent original-source comparison needs those separately, while migrated app/tests do not. Historical absolute paths in raw logs are evidence, not runtime instructions.

Repair validation: 8 targeted real PG/API/file tests passed; full backend 192 passed / 8 warnings / 138.34s, including real OIDC. Node19 and actual React HTTP-substitute2 passed; types/build passed and OpenAPI/client bytes unchanged. Red logs explicitly distinguish defect reproduction from fixture errors. Exact commands/results: source/docs/tasks/TASK-008/evidence/r1-r2/validation.json, logs and browser-notes.md.

Not run: saved browser-download artifact checksum (download event unavailable; server audit allowed and PG/API byte checks are separate), full original browser flow repeated, Docker execution, remote CI, other engines, automated pixel thresholds and production validation. Directed browser login/upload/rejection/freeze/cleanup and final timeline/closed-opening/reconciliation screenshots were actually checked. No task acceptance implied. Historical result/evidence limitations are preserved, not rewritten.
''')
    secret=rb'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}'
    for f in root.rglob('*'):
        if not f.is_file():continue
        assert f.stat().st_size<25*1024*1024,f'Large file requires review: {f.relative_to(root)}'
        data=f.read_bytes()
        if f.suffix=='.gz':data=gzip.decompress(data)
        assert not re.search(secret,data),f'Sensitive pattern; stop without printing value: {f.relative_to(root)}'
    tree={}
    for line in git('ls-tree','-rz',head).split(b'\0'):
        if not line:continue
        meta,name=line.split(b'\t',1);mode,kind,oid=meta.split();assert kind==b'blob'
        name=name.decode();tree[name]=oid.decode();data=(source/name).read_bytes()
        assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==oid.decode(),name
    with tempfile.TemporaryDirectory(prefix='silicon-task008-patch-') as d:
        old=Path(d);extract(base,old)
        for f in (old/'docs/reviews').rglob('*'):
            if f.is_file():assert f.read_bytes()==(source/f.relative_to(old)).read_bytes(),str(f)
        for f in (old/'docs/tasks/TASK-007').rglob('*'):
            if f.is_file() and f.name!='task.md':assert f.read_bytes()==(source/f.relative_to(old)).read_bytes(),str(f)
        for f in (old/'docs/tasks/TASK-008/evidence').rglob('*'):
            if f.is_file():assert f.read_bytes()==(source/f.relative_to(old)).read_bytes(),str(f)
        historical=old/'docs/tasks/TASK-008/result.md'
        assert (source/'docs/tasks/TASK-008/result.md').read_bytes().startswith(historical.read_bytes())
        subprocess.run(['git','apply','--binary',str(changes/'base-to-final.patch')],cwd=old,check=True)
        assert {str(f.relative_to(old)) for f in old.rglob('*') if f.is_file()}==set(tree)
        for name in tree:assert (old/name).read_bytes()==(source/name).read_bytes(),name
    for name in ['apps/api/migrations/versions/0009_inventory.py','apps/api/tests/test_inventory.py','apps/api/tests/test_inventory_files.py','docs/tasks/TASK-008/evidence/r1-r2/backend-full.txt','docs/tasks/TASK-008/evidence/r1-r2/reconciliation-mobile.jpg','apps/web/src/Inventory.tsx','docs/tasks/TASK-008/task.md','docs/tasks/TASK-008/evidence/backend-complete.txt','docs/tasks/TASK-008/evidence/inventory-mobile.jpg']:
        assert (source/name).is_file(),name
    (root/'PACKAGE_CHECKS.json').write_text(json.dumps({'final':head,'tracked_files':len(tree),'commit_blobs_exact':True,'binary_patch_replay_exact':True,'prior_reports_and_task007_history_unchanged':True,'task008_historical_evidence_and_result_prefix_unchanged':True,'symlinks':0,'secret_scan':'no high-confidence matches; fictional fixtures retained','independent_acceptance':False},indent=2)+'\n')
    files=sorted(f for f in root.rglob('*') if f.is_file())
    (root/'SHA256SUMS').write_text(''.join(hashlib.sha256(f.read_bytes()).hexdigest()+'  '+str(f.relative_to(root))+'\n' for f in files))
    args.destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.destination,'w',zipfile.ZIP_DEFLATED) as archive:
        for f in sorted(root.rglob('*')):
            if f.is_file():archive.write(f,str(f.relative_to(root)))
with tempfile.TemporaryDirectory(prefix='silicon-task008-unzip-') as d:
    root=Path(d)
    with zipfile.ZipFile(args.destination) as archive:
        assert archive.testzip() is None;archive.extractall(root)
    expected={}
    for line in (root/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1);expected[name]=digest
    assert set(expected)=={str(f.relative_to(root)) for f in root.rglob('*') if f.is_file() and f.name!='SHA256SUMS'}
    for name,digest in expected.items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
print(json.dumps({'package':str(args.destination.resolve()),'sha256':hashlib.sha256(args.destination.read_bytes()).hexdigest(),'final':head,'verified_files':len(expected)},indent=2))

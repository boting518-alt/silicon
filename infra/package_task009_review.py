"""Export committed TASK-009 review source; refuse dirty trees or unsafe materials."""
import argparse,gzip,hashlib,io,json,re,subprocess,tarfile,tempfile,zipfile
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--implementation',required=True)
p.add_argument('--destination',type=Path,required=True)
args=p.parse_args()
repo=Path(__file__).resolve().parents[1]
def git(*parts):return subprocess.check_output(['git',*parts],cwd=repo)
base='b56ed65f2a234a956f75102b1320f7658dddfd71'
handoff='01e2c2759bb29d728ccd38f45db0597d689f0ceb'
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
with tempfile.TemporaryDirectory(prefix='silicon-task009-review-') as temporary:
    root=Path(temporary);source=root/'source';source.mkdir();extract(head,source)
    changes=root/'changes';changes.mkdir()
    for label,a,b in [('base-to-final',base,head),('review-to-implementation',handoff,implementation),('implementation-to-final',implementation,head)]:
        for suffix,command in [('patch',['diff','--binary','--full-index',a,b]),('log.txt',['log','--format=fuller','--reverse',a+'..'+b]),('changed-files.txt',['diff','--name-status',a,b]),('stat.txt',['diff','--stat',a,b])]:
            (changes/(label+'.'+suffix)).write_bytes(git(*command))
    (changes/'worktree-status.txt').write_bytes(status)
    for name in ['AGENTS.md','docs/tasks/backlog.md','docs/tasks/TASK-009/task.md']:
        dest=changes/'review-base'/name;dest.parent.mkdir(parents=True,exist_ok=True)
        result=subprocess.run(['git','show',base+':'+name],cwd=repo,capture_output=True)
        if result.returncode==0:dest.write_bytes(result.stdout)
        else:dest.with_suffix('.absent.txt').write_text(f'{name} absent at {base}\n')
    evidence=root/'evidence';evidence.mkdir()
    (evidence/'INDEX.md').write_text('# Evidence index\n\n- [TASK-009 result](../source/docs/tasks/TASK-009/result.md)\n- [Validation and exact commands](../source/docs/tasks/TASK-009/evidence/validation.json)\n- [Browser procedure and limitations](../source/docs/tasks/TASK-009/browser-acceptance.md)\n- [Screenshots](../source/docs/tasks/TASK-009/evidence/screenshots.json)\n- [Task](../source/docs/tasks/TASK-009/task.md)\n- [ADR-014](../source/docs/architecture/adr/ADR-014.md)\n- [Original design baseline](../source/docs/design/demo-baseline.md)\n\nFull raw logs and screenshots are under source/docs/tasks/TASK-009/evidence. Prior reports and evidence are retained under source without duplicate copies.\n')
    (root/'REVIEW_MANIFEST.md').write_text(f'''# SILICON TASK-009 independent review package

Status: review_ready, not accepted. TASK-010 not started.

- Accepted base: {base}
- Complete-task handoff: {handoff}
- Implementation: {implementation}
- Final HEAD: {head}
- Worktree: clean at export; branch main. Ancestry verified.

source/ is ALL tracked files archived from final HEAD. changes/ has binary full-index patches, file status, stats and logs for base→final, handoff→implementation, implementation→final. review-base contains prior AGENTS/backlog and explicitly marks TASK009 task absent. SHA256SUMS excludes itself. PACKAGE_CHECKS validates blobs, patch replay, historical evidence and full unpacked checksums. No uncommitted content is included.

## Preparation and reproduction

Run from source/. Node24.15.0/npm11.12.1, Python3.12.7/uv0.12.11; actual tested PostgreSQL17.11, Java21.0.6, Keycloak26.7.3. Versions remain locked. Use your own available verified installations or repository preparation scripts; no host-specific absolute paths are required:

```bash
cd source
npm ci --ignore-scripts
uv sync --locked
# If PG binaries are unavailable, build verified PG source:
.venv/bin/python infra/build_test_postgres.py --prefix "$PWD/.tools/review-pg17"
export PG17_HOME="$PWD/.tools/review-pg17"
export SILICON_TEST_PG_BIN="$PG17_HOME/bin"
# Expose an existing Java21 installation through JAVA_HOME/PATH.
.venv/bin/python infra/fetch_keycloak.py --destination .tools/keycloak
export SILICON_TEST_KEYCLOAK_HOME="$PWD/.tools/keycloak/keycloak-26.7.3"
.venv/bin/python -m pytest apps/api/tests -q
npm run typecheck
npm run build
node --test apps/web/tests/catalog-time.test.ts apps/web/tests/context-race.test.ts
.venv/bin/python infra/export_openapi.py
npm run api:types
.venv/bin/python infra/check_docs.py
```

PG/Keycloak scripts verify pinned download checksums. Existing destinations are not overwritten. Tests create random-port temporary PG clusters and migration/runtime roles, then stop and remove only those clusters. OIDC generates a repository-owned CA and verifies hostnames. Browser stack uses its own PG/IdP/API/file roots with fictional sales contract and inventory fixtures, no assembly transactions preseeded. SIGTERM/Ctrl-C cleans owned processes and logs BROWSER_STACK_CLEANED. Do not use resident README bootstrap to run tests.

Browser prerequisite: legitimately available `.tools/visual/PingFang.ttc` matching browser_stack hash, and trusted localhost certificate/key in `.tools/tls`. Generate via infra/dev_tls.py only on reviewer's own machine when missing; system trust changes require separate user authorization. Do not copy private keys or bypass TLS. Font/private key/PG/Java/Keycloak binaries are excluded. This task did not change system trust. Existing original Demo checkouts are external read-only references; migrated code, captured design baseline and tests are included.

```bash
SILICON_BROWSER_ASSEMBLY=1 SILICON_BROWSER_INVENTORY=1 SILICON_BROWSER_CONTRACTS=1 SILICON_BROWSER_CATALOG=1 .venv/bin/python infra/browser_stack.py
```

Open https://localhost:5173 and use fictional alice/Fictional-alice-17!; choose enterprise A. B is viewer with no business data. Follow browser-acceptance.md for actual order→work→reservation→partial issue→completion→device flow and two viewports. `/tests/assembly-component.html` runs actual React with HTTP substitutes and is separately labelled, never substitutes for real PG/browser evidence.

## Evidence and limitations

Read validation.json and result.md for exact test outcomes and intermediate failures. Local passing commands do not imply remote CI or independent review passed. TASK008 historical download-artifact limit remains; no new file flow. No Docker, other-browser, production deployment or real supplier/tax-policy verification. No testing certification, delivery, payments, normal dismantling or labor overhead enabled. Historical absolute paths in raw logs are evidence only.

No .env, secrets, private keys, sessions/tokens, database files, dependency directories, .git or AppleDouble. Safe env examples, locks, CI, scripts, migrations, fictional fixtures and screenshots remain. High-confidence secret scan stops export on a match; no silent rewriting of source.
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
    with tempfile.TemporaryDirectory(prefix='silicon-task009-patch-') as d:
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
    for name in ['apps/api/migrations/versions/0010_assembly.py','apps/api/tests/test_assembly.py','apps/web/src/Assembly.tsx','docs/tasks/TASK-009/task.md','docs/tasks/TASK-009/evidence/validation.json','docs/tasks/TASK-009/evidence/screenshots.json']:
        assert (source/name).is_file(),name
    (root/'PACKAGE_CHECKS.json').write_text(json.dumps({'final':head,'tracked_files':len(tree),'commit_blobs_exact':True,'binary_patch_replay_exact':True,'prior_reports_and_task007_history_unchanged':True,'task008_historical_evidence_and_result_prefix_unchanged':True,'symlinks':0,'secret_scan':'no high-confidence matches; fictional fixtures retained','independent_acceptance':False},indent=2)+'\n')
    files=sorted(f for f in root.rglob('*') if f.is_file())
    (root/'SHA256SUMS').write_text(''.join(hashlib.sha256(f.read_bytes()).hexdigest()+'  '+str(f.relative_to(root))+'\n' for f in files))
    args.destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.destination,'w',zipfile.ZIP_DEFLATED) as archive:
        for f in sorted(root.rglob('*')):
            if f.is_file():archive.write(f,str(f.relative_to(root)))
with tempfile.TemporaryDirectory(prefix='silicon-task009-unzip-') as d:
    root=Path(d)
    with zipfile.ZipFile(args.destination) as archive:
        assert archive.testzip() is None;archive.extractall(root)
    expected={}
    for line in (root/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1);expected[name]=digest
    assert set(expected)=={str(f.relative_to(root)) for f in root.rglob('*') if f.is_file() and f.name!='SHA256SUMS'}
    for name,digest in expected.items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
print(json.dumps({'package':str(args.destination.resolve()),'sha256':hashlib.sha256(args.destination.read_bytes()).hexdigest(),'final':head,'verified_files':len(expected)},indent=2))

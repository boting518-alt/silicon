"""TASK-013 committed full-source export; derived from task012 packaging checks."""
import argparse,gzip,hashlib,io,json,re,subprocess,tarfile,tempfile,zipfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--implementation',required=True);p.add_argument('--review-base');p.add_argument('--destination',type=Path,required=True);args=p.parse_args()
repo=Path(__file__).resolve().parents[1]
def git(*parts):return subprocess.check_output(['git',*parts],cwd=repo)
base='18966f4eaf3fdd1311b883e32f6f8e2eb123d48a';handoff='5a882909d6aee58b6f1262b5c2a91825a1618b22'
implementation=git('rev-parse',args.implementation).decode().strip();head=git('rev-parse','HEAD').decode().strip()
for a,b in [(base,handoff),(handoff,implementation),(implementation,head)]:subprocess.run(['git','merge-base','--is-ancestor',a,b],cwd=repo,check=True)
review_base=git('rev-parse',args.review_base).decode().strip() if args.review_base else None
if review_base:subprocess.run(['git','merge-base','--is-ancestor',review_base,implementation],cwd=repo,check=True)
status=git('status','--porcelain=v1','--untracked-files=all');assert not status,'Inspect and preserve uncommitted files before exporting'
assert not args.destination.exists(),'Never overwrite prior review package'
def extract(commit,destination):
    with tarfile.open(fileobj=io.BytesIO(git('archive',commit))) as archive:
        for m in archive:
            assert not m.issym() and not m.islnk(),m.name
            for part in Path(m.name).parts:
                assert part not in {'.git','.tools','.venv','node_modules','__MACOSX'} and not part.startswith('._'),m.name
                assert not (part.startswith('.env') and part!='.env.example'),m.name
        archive.extractall(destination,filter='data')
with tempfile.TemporaryDirectory(prefix='silicon-task013-review-') as temporary:
    root=Path(temporary);source=root/'source';source.mkdir();extract(head,source);changes=root/'changes';changes.mkdir()
    for label,a,b in [('base-to-final',base,head),('handoff-to-implementation',handoff,implementation),('implementation-to-final',implementation,head)]+([('review-to-final',review_base,head)] if review_base else []):
        for suffix,command in [('patch',['diff','--binary','--full-index',a,b]),('log.txt',['log','--format=fuller','--reverse',a+'..'+b]),('changed-files.txt',['diff','--name-status',a,b]),('stat.txt',['diff','--stat',a,b])]:
            (changes/(label+'.'+suffix)).write_bytes(git(*command))
    (changes/'worktree-status.txt').write_bytes(status)
    for name in ['AGENTS.md','docs/tasks/backlog.md','docs/tasks/TASK-013/task.md']:
        dest=changes/'accepted-base'/name;dest.parent.mkdir(parents=True,exist_ok=True)
        r=subprocess.run(['git','show',base+':'+name],cwd=repo,capture_output=True)
        if not r.returncode:dest.write_bytes(r.stdout)
        else:dest.with_suffix('.absent.txt').write_text(f'{name} absent at {base}\n')
    evidence=root/'evidence';evidence.mkdir()
    (evidence/'INDEX.md').write_text('''# Evidence

- [Result](../source/docs/tasks/TASK-013/result.md)
- [Validation](../source/docs/tasks/TASK-013/evidence/validation.json)
- [Browser procedure](../source/docs/tasks/TASK-013/browser-acceptance.md)
- [Screenshots](../source/docs/tasks/TASK-013/evidence/screenshots.json)
- [Metric catalog](../source/docs/analytics/metric-catalog.md)
- [Regions/source/license](../source/docs/analytics/regions-source.md)
- [ADR018](../source/docs/architecture/adr/ADR-018.md)
- [Original design](../source/docs/design/demo-baseline.md)

All raw logs, screenshots and earlier reports remain inside source/. No duplication is needed.
''')
    (root/'REVIEW_MANIFEST.md').write_text(f'''# SILICON TASK-013 independent review package

Status review_ready, not accepted. TASK-014 not started.

- Accepted base: {base}
- Handoff: {handoff}
- Implementation: {implementation}
- Final HEAD: {head}
- Incremental review base: {review_base or 'not applicable'}
- When incremental, read source/docs/tasks/TASK-013/evidence/review-r1-r2/validation.json and source/docs/tasks/TASK-013/review-repair.md for this repair's exact commands and evidence. Use SILICON_BROWSER_ANALYTICS_REVIEW=1 instead of SILICON_BROWSER_ANALYTICS=1 for its isolated browser fixture.
- Worktree: clean at export; main. Ancestry verified.

source/ is ALL tracked files archived from final HEAD. changes/ includes full binary patches, logs, status and stats for base→final, handoff→implementation and implementation→final, and prior instructions. SHA256SUMS excludes itself. PACKAGE_CHECKS verifies exact Git blobs, replaying the binary patch, unchanged historical evidence, and unpacked checksums. No uncommitted content.

## Preparation (relative to source/)

Actual environment: Node24.15.0/npm11.12.1, Python3.12.7, PostgreSQL17.11, Java21.0.6, Keycloak26.7.3. Existing locked dependencies unchanged. Use verified local binaries or the checked-in preparation scripts:

```bash
cd source
npm ci --ignore-scripts
uv sync --locked
.venv/bin/python infra/build_test_postgres.py --prefix "$PWD/.tools/review-pg17"
export SILICON_TEST_PG_BIN="$PWD/.tools/review-pg17/bin"
# Expose an installed Java21 through JAVA_HOME/PATH.
.venv/bin/python infra/fetch_keycloak.py --destination .tools/keycloak
export SILICON_TEST_KEYCLOAK_HOME="$PWD/.tools/keycloak/keycloak-26.7.3"
.venv/bin/python -m pytest apps/api/tests -q
.venv/bin/python -m pytest apps/api/tests/test_analytics.py -q -s
node --test apps/web/tests/*.test.ts
.venv/bin/python infra/export_openapi.py
npm run api:types
npm run typecheck
npm run build
.venv/bin/python infra/check_docs.py
git diff --check
```

PG/Keycloak fetch/build scripts verify pinned checksums; no binary installation bundles in this archive. Tests create random loopback-port temporary PG clusters with separate migration/runtime roles, then stop/remove only owned clusters. Finance chronology fixtures deliberately assign fictional dates in their temporary cluster; actual authorization/aggregation is through silicon_app with FORCE RLS. No mock database. OIDC owns its generated CA and validates hostnames; do not disable TLS. Do not run browser stack alongside OIDC integration tests because Keycloak uses shared local ports.

## Browser reproduction

Provide legally available `.tools/visual/PingFang.ttc` matching the documented hash and a trusted localhost/127.0.0.1 certificate/key at `.tools/tls/`. Missing certificates can be generated on the reviewer's own machine with infra/dev_tls.py, but trust changes require explicit authorization. Private keys, fonts and binaries are not packaged; no TLS bypass or system trust change in this task.

```bash
SILICON_BROWSER_ANALYTICS=1 SILICON_BROWSER_CONTRACTS=1 .venv/bin/python infra/browser_stack.py
```

Open https://localhost:5173. Fictional alice/Fictional-alice-17! is admin in A/B; carol/Fictional-carol-17! is a test-only non-finance reader in A. Fixture seeds signed contract, one sent device, split supplier RMA, finance plan/retention/cash/allocation via existing commands. No real business data. Set period 2026-01-01→2026-09-13 (exclusive), cutoff2026-09-12 for this evidence date; the visual page clock remains original2026-09-08 and does not set backend business time. Follow browser-acceptance.md for exact steps, role/enterprise checks and viewports. Closing with Ctrl-C/SIGTERM logs BROWSER_STACK_CLEANED and removes only owned processes/temp data. `/tests/analytics-component.html` is actual React with explicit HTTP substitutes; not real DB/browser acceptance evidence.

## Scope and limitations

Read result.md and evidence/validation.json for exact commands/results and intermediate failures. Local testing is distinct from remote CI and independent review. Standard financial turnover metrics remain unavailable: no accounting income/cost recognition or complete average balances. Regions use current explicit customer province, not historical delivery snapshots. Province tiles are original explanatory layout with an always-available table; no third-party map/address upload. No-active-membership or missing-audit historic confirmation dates remain unavailable. Inventory own-scope/customer filters may be not_applicable. More than100000 source rows returns an explicit limit, not silently truncated totals. Not a large-scale warehouse benchmark.

Existing reference Demo checkouts, fonts, PG/Java/Keycloak and certificate private keys are external dependencies; migrated code and captured visual baselines are included. Historical host paths in raw logs are evidence only, not runtime dependencies. See migration.md for loss-preventing downgrade refusal. No resident DB access, deployment, business automation or TASK014.

No .env, real credentials, sessions/tokens, private keys, database/backup files, dependency trees, .git or AppleDouble. Safe env examples, locks, CI, scripts, fictional seeds and screenshots stay included. High-confidence secret scan stops export rather than rewriting source.
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
        meta,name=line.split(b'\t',1);mode,kind,oid=meta.split();assert kind==b'blob';name=name.decode();tree[name]=oid.decode();data=(source/name).read_bytes()
        assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==oid.decode(),name
    with tempfile.TemporaryDirectory(prefix='silicon-task013-patch-') as d:
        old=Path(d);extract(base,old)
        for directory in ['docs/reviews','docs/tasks/TASK-012']:
            for f in (old/directory).rglob('*'):
                if f.is_file() and not (directory.endswith('TASK-012') and f.name=='task.md'):assert f.read_bytes()==(source/f.relative_to(old)).read_bytes(),str(f)
        subprocess.run(['git','apply','--binary',str(changes/'base-to-final.patch')],cwd=old,check=True)
        assert {str(f.relative_to(old)) for f in old.rglob('*') if f.is_file()}==set(tree)
        for name in tree:assert (old/name).read_bytes()==(source/name).read_bytes(),name
    if review_base:
        for entry in git('ls-tree','-rz',review_base,'docs/tasks/TASK-013/evidence','docs/reviews').split(b'\0'):
            if not entry:continue
            _,name=entry.split(b'\t',1);name=name.decode()
            assert git('show',review_base+':'+name)==(source/name).read_bytes(),name
        prior=git('show',review_base+':docs/tasks/TASK-013/result.md')
        assert (source/'docs/tasks/TASK-013/result.md').read_bytes().startswith(prior),'Keep original result verbatim, append repair record'
    for name in ['apps/api/migrations/versions/0016_analytics.py','apps/api/tests/test_analytics.py','apps/web/src/Analytics.tsx','docs/tasks/TASK-013/task.md','docs/tasks/TASK-013/evidence/validation.json','docs/tasks/TASK-013/evidence/screenshots.json']:
        assert (source/name).is_file(),name
    screenshots=json.loads((source/'docs/tasks/TASK-013/evidence/screenshots.json').read_text())
    for item in screenshots:
        f=source/'docs/tasks/TASK-013/evidence'/item['file'];assert hashlib.sha256(f.read_bytes()).hexdigest()==item['sha256']
    if review_base:
        repair=source/'docs/tasks/TASK-013/evidence/review-r1-r2'
        for item in json.loads((repair/'screenshots.json').read_text()):
            assert hashlib.sha256((repair/item['file']).read_bytes()).hexdigest()==item['sha256']
        for item in json.loads((repair/'raw-log-index.json').read_text()):
            assert hashlib.sha256(gzip.decompress((repair/item['stored']).read_bytes())).hexdigest()==item['raw_sha256']
        with (evidence/'INDEX.md').open('a') as f:
            f.write('\nCurrent incremental evidence: [repair](../source/docs/tasks/TASK-013/review-repair.md), [validation](../source/docs/tasks/TASK-013/evidence/review-r1-r2/validation.json), [original report](../source/docs/reviews/TASK-013-706e032-review.md).\n')
    (root/'PACKAGE_CHECKS.json').write_text(json.dumps({'final':head,'tracked_files':len(tree),'commit_blobs_exact':True,'binary_patch_replay_exact':True,'prior_reports_and_task012_history_unchanged':True,'symlinks':0,'secret_scan':'no high-confidence matches; fictional fixtures retained','independent_acceptance':False,'incremental_review_base':review_base,'prior_task013_evidence_preserved':bool(review_base)},indent=2)+'\n')
    files=sorted(f for f in root.rglob('*') if f.is_file());(root/'SHA256SUMS').write_text(''.join(hashlib.sha256(f.read_bytes()).hexdigest()+'  '+str(f.relative_to(root))+'\n' for f in files))
    args.destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.destination,'w',zipfile.ZIP_DEFLATED) as archive:
        for f in sorted(root.rglob('*')):
            if f.is_file():archive.write(f,str(f.relative_to(root)))
with tempfile.TemporaryDirectory(prefix='silicon-task013-unzip-') as d:
    root=Path(d)
    with zipfile.ZipFile(args.destination) as archive:assert archive.testzip() is None;archive.extractall(root)
    expected={}
    for line in (root/'SHA256SUMS').read_text().splitlines():digest,name=line.split('  ',1);expected[name]=digest
    assert set(expected)=={str(f.relative_to(root)) for f in root.rglob('*') if f.is_file() and f.name!='SHA256SUMS'}
    for name,digest in expected.items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
print(json.dumps({'package':str(args.destination.resolve()),'sha256':hashlib.sha256(args.destination.read_bytes()).hexdigest(),'final':head,'verified_files':len(expected)},indent=2))

"""Recreate OD-018 read-only reference verification in a new independent clone.

Original references are only read. No metadata cleanup or source transformations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def prepare(output):
    manifest = json.loads((ROOT/'docs/design/source-manifest.json').read_text())
    destination = Path(tempfile.mkdtemp(prefix='silicon-demo-baseline-', dir='/tmp'))
    results = []
    for source in manifest['sources']:
        original = (ROOT/source['path']).resolve()
        clone = destination/source['name']
        subprocess.run(['git', 'clone', '--no-local', '--no-hardlinks', str(original), str(clone)], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(clone), 'checkout', '--detach', source['commit']], check=True, capture_output=True)
        fsck = subprocess.run(['git', '-C', str(clone), 'fsck', '--full'], check=True, capture_output=True, text=True)
        tracked = subprocess.check_output(['git', '-C', str(clone), 'ls-tree', '-r', '--name-only', source['commit']], text=True).splitlines()
        assert set(tracked) == {item['path'] for item in source['files']}, 'Source inventory changed'
        files = []
        for item in source['files']:
            blob = subprocess.check_output(['git', '-C', str(clone), 'show', source['commit']+':'+item['path']])
            assert (original/item['path']).read_bytes() == blob == (clone/item['path']).read_bytes()
            assert hashlib.sha256(blob).hexdigest() == item['sha256']
            files.append({'path': item['path'], 'sha256': item['sha256'], 'matches': True})
        identity = json.loads((clone/'.openai/hosting.json').read_text())
        assert source['project_id'] in identity.values(), 'Demo project identity changed'
        results.append({'name': source['name'], 'commit': source['commit'], 'project_id': source['project_id'],
                        'files': files, 'fsck_exit': fsck.returncode})
    report = {'clones': str(destination), 'originals_modified': False, 'sources': results}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    prepare(parser.parse_args().output)

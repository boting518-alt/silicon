"""Check captured JPEG sizes/hashes without image manipulation or new dependencies."""
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'docs/tasks/TASK-003/evidence/screenshots'


def dimensions(data):
    assert data[:2]==b'\xff\xd8', 'Expected original JPEG screenshot bytes'
    offset=2
    while offset<len(data):
        assert data[offset]==255
        marker=data[offset+1];offset+=2
        if marker in (0xd8,0xd9):continue
        size=int.from_bytes(data[offset:offset+2],'big')
        if marker in (0xc0,0xc1,0xc2):
            height,width=struct.unpack('>HH',data[offset+3:offset+7])
            return width,height
        offset+=size
    raise ValueError('No JPEG dimensions')


rows=[]
for path in sorted(DIRECTORY.glob('*.jpg')):
    if path.name.startswith('._'):continue
    data=path.read_bytes();size=dimensions(data)
    expected=(390,844) if path.stem.endswith('-390') else (1440,900)
    assert size==expected,(path.name,size,expected)
    rows.append({'file':'screenshots/'+path.name,'width':size[0],'height':size[1],
                 'format':'JPEG','sha256':hashlib.sha256(data).hexdigest()})
assert len(rows)>=17
(ROOT/'docs/tasks/TASK-003/evidence/screenshot-manifest.json').write_text(json.dumps(rows,indent=2)+'\n')
print(f'PASS {len(rows)} original JPEG screenshots, exact viewport sizes and SHA-256 manifest')

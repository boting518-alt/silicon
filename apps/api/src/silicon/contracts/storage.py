"""Private local adapter. Type validation is NOT malware scanning."""
import hashlib,os,re,struct,zlib,fcntl
from pathlib import Path
from uuid import uuid4,UUID
from silicon.identity.access import Denied

class Store:
    def __init__(self,root,limit):
        self.root=Path(root).resolve() if root else None;self.limit=limit
    def path(self,id):
        if not self.root:raise Denied(503,'FILE_STORAGE_UNCONFIGURED')
        return self.root/str(UUID(str(id)))
    def validate(self,name,data):
        if not name or len(name)>160 or '/' in name or '\\' in name or any(ord(x)<32 for x in name):raise Denied(422,'INVALID_FILENAME')
        if not data or len(data)>self.limit:raise Denied(413,'FILE_SIZE_LIMIT')
        suffix=Path(name).suffix.lower()
        if suffix=='.pdf' and re.match(rb'%PDF-1\.[0-9]',data) and data.rstrip().endswith(b'%%EOF'):
            # Reject active PDF actions; still not a full parser/AV guarantee.
            if re.search(rb'/(?:JavaScript|JS|Launch|OpenAction|EmbeddedFile)\b',data):raise Denied(422,'ACTIVE_CONTENT_REJECTED')
            return 'application/pdf'
        if suffix=='.png' and data.startswith(b'\x89PNG\r\n\x1a\n'):
            pos=8;ended=False;first=True
            while pos+12<=len(data):
                size=struct.unpack('>I',data[pos:pos+4])[0];kind=data[pos+4:pos+8];end=pos+12+size
                if end>len(data) or zlib.crc32(data[pos+4:end-4])&0xffffffff!=struct.unpack('>I',data[end-4:end])[0]:break
                if first and (kind!=b'IHDR' or size!=13):break
                if first:
                    w,h=struct.unpack('>II',data[pos+8:pos+16])
                    if not w or not h or w*h>40000000:break
                first=False;pos=end
                if kind==b'IEND':ended=pos==len(data);break
            if ended:return 'image/png'
        if suffix in ('.jpg','.jpeg') and data.startswith(b'\xff\xd8\xff') and data.endswith(b'\xff\xd9') and len(data)>20:return 'image/jpeg'
        raise Denied(422,'FILE_TYPE_REJECTED')
    def put(self,name,data):
        media=self.validate(name,data);id=uuid4();path=self.path(id);path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as f:os.chmod(path,0o600);f.write(data);f.flush();os.fsync(f.fileno())
        lock=path.open('rb');fcntl.flock(lock,fcntl.LOCK_EX);self._lock=lock
        return dict(storage_id=id,name=name,media_type=media,size=len(data),sha256=hashlib.sha256(data).hexdigest())
    def read(self,row):
        path=self.path(row['storage_id'])
        if path.is_symlink() or not path.is_file():raise Denied(503,'FILE_NOT_READY')
        data=path.read_bytes()
        if len(data)!=row['size'] or hashlib.sha256(data).hexdigest()!=row['sha256']:raise Denied(503,'FILE_NOT_READY')
        return data
    def remove(self,id):self.path(id).unlink(missing_ok=True)

    def release(self):
        if getattr(self,"_lock",None):self._lock.close();self._lock=None

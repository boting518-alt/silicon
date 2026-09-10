"""Private local adapter. Type validation is NOT malware scanning."""
import hashlib,os,re,fcntl,subprocess,sys,threading,time
import psutil
from pathlib import Path
from uuid import uuid4,UUID
from silicon.identity.access import Denied

DECODERS=threading.BoundedSemaphore(2)

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
        kind={'.pdf':'pdf','.png':'png','.jpg':'jpg','.jpeg':'jpg'}.get(suffix)
        if not kind:raise Denied(422,'FILE_TYPE_REJECTED')
        if kind=='pdf':
            if not re.match(rb'%PDF-(?:1\.[0-9]|2\.0)',data) or not data.rstrip().endswith(b'%%EOF'):raise Denied(422,'FILE_TYPE_REJECTED')
            if re.search(rb'/(?:JavaScript|JS|Launch|OpenAction|EmbeddedFile)\b',data):raise Denied(422,'ACTIVE_CONTENT_REJECTED')
        if not DECODERS.acquire(timeout=1):raise Denied(503,'FILE_VALIDATOR_BUSY')
        try:
            with subprocess.Popen([sys.executable,str(Path(__file__).with_name('validate_file.py')),kind],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env={}) as child:
                try:
                    process=psutil.Process(child.pid);deadline=time.monotonic()+8;pending=data
                    while True:
                        if time.monotonic()>deadline:raise Denied(422,'FILE_VALIDATION_LIMIT')
                        try:
                            if process.memory_info().rss>512*1024*1024:raise Denied(422,'FILE_VALIDATION_LIMIT')
                        except psutil.NoSuchProcess:pass
                        try:child.communicate(input=pending,timeout=0.02);break
                        except subprocess.TimeoutExpired:pending=None
                    code=child.returncode
                    if code==12:raise Denied(503,'FILE_VALIDATOR_UNAVAILABLE')
                    if code==11 or code<0:raise Denied(422,'FILE_VALIDATION_LIMIT')
                    if code:raise Denied(422,'FILE_TYPE_REJECTED')
                except psutil.Error:raise Denied(503,'FILE_VALIDATOR_UNAVAILABLE') from None
                finally:
                    if child.poll() is None:child.kill()
                    child.wait()
        finally:DECODERS.release()
        return {'pdf':'application/pdf','jpg':'image/jpeg','png':'image/png'}[kind]
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
    def revalidate(self,row):
        data=self.read(row)
        if self.validate(row['name'],data)!=row['media_type']:raise Denied(422,'FILE_TYPE_REJECTED')
        return data
    def remove(self,id):self.path(id).unlink(missing_ok=True)

    def release(self):
        if getattr(self,"_lock",None):self._lock.close();self._lock=None

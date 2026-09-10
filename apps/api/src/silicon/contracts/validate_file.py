"""Isolated bounded format decoder; stdin only, no business credentials or output files.
Exit 10: invalid document, 11: resource/policy limit, 12: unavailable decoder.
Not an AV scanner, sandbox, PDF conformance certification or signature verifier.
"""
import io,math,resource,sys,warnings

MAX_BYTES=20*1024*1024
MAX_PIXELS=40_000_000
MAX_PAGES=50
MAX_TOTAL_PIXELS=100_000_000

class Limit(Exception):pass

def limits():
    resource.setrlimit(resource.RLIMIT_CPU,(6,6))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
    # Parent monitors RSS on all hosts; Linux also has an address-space hard cap.
    if sys.platform.startswith('linux'):resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024))

def decode(data,kind):
    if kind=='pdf':
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(data) as doc:
            count=len(doc)
            if count<1:raise ValueError('no pages')
            if count>MAX_PAGES:raise Limit()
            total=0
            for n in range(count):
                page=doc[n]
                try:
                    w,h=page.get_size()
                    if not math.isfinite(w+h) or min(w,h)<=0:raise ValueError('page dimensions')
                    pixels=math.ceil(w)*math.ceil(h);total+=pixels
                    if pixels>MAX_PIXELS or total>MAX_TOTAL_PIXELS:raise Limit()
                    bitmap=page.render(scale=1,draw_annots=False)
                    bitmap.close()
                finally:page.close()
    else:
        from PIL import Image,ImageFile
        Image.MAX_IMAGE_PIXELS=MAX_PIXELS
        ImageFile.LOAD_TRUNCATED_IMAGES=False
        warnings.simplefilter('error',Image.DecompressionBombWarning)
        expected={'jpg':'JPEG','png':'PNG'}[kind]
        with Image.open(io.BytesIO(data),formats=[expected]) as image:
            if image.format!=expected or getattr(image,'n_frames',1)!=1:raise ValueError('unsupported image')
            if image.width*image.height>MAX_PIXELS:raise Limit()
            image.verify()
        with Image.open(io.BytesIO(data),formats=[expected]) as image:image.load()

if __name__=='__main__':
    try:limits()
    except Exception:sys.exit(12)
    try:
        data=sys.stdin.buffer.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:raise Limit()
        decode(data,sys.argv[1])
    except (ImportError,ModuleNotFoundError):sys.exit(12)
    except (Limit,MemoryError):sys.exit(11)
    except Exception:sys.exit(10)

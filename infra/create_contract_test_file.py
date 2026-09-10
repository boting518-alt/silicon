"""Generate a clearly fictional, non-binding PDF for attachment acceptance."""
from pathlib import Path
import argparse

def generate(path):
    message=b'BT /F1 16 Tf 40 760 Td (FICTIONAL TEST ONLY - NO CONTRACT OR SIGNATURE) Tj ET'
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(message)).encode()+b' >>\nstream\n'+message+b'\nendstream']
    data=bytearray(b'%PDF-1.4\n');offsets=[]
    for i,obj in enumerate(objects,1):offsets.append(len(data));data+=str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
    start=len(data);data+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{n:010d} 00000 n \n'.encode() for n in offsets)+b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n'+str(start).encode()+b'\n%%EOF\n'
    with Path(path).open('xb') as f:f.write(data)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('path');generate(parser.parse_args().path)

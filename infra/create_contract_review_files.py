"""Generate fictional files for directed R1/R2 browser acceptance only."""
from pathlib import Path
import argparse
from PIL import Image
from create_contract_test_file import generate

def create(directory):
    root=Path(directory);root.mkdir(parents=True,exist_ok=False)
    for name in ['proof-a.pdf','unused-b.pdf']:generate(root/name)
    for name,format in [('valid.jpg','JPEG'),('valid.png','PNG')]:
        Image.new('RGB',(8,8),(30,90,60)).save(root/name,format=format)
    (root/'invalid.pdf').write_bytes(b'%PDF-1.4\nthis is plain text, no PDF objects or pages\n%%EOF')
    (root/'invalid.jpg').write_bytes(b'\xff\xd8\xffnot a JPEG image, plain text\xff\xd9')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory');create(parser.parse_args().directory)

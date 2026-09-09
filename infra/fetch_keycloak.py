"""Fetch the exact official Keycloak distribution into a new, isolated directory."""
import argparse
import hashlib
from pathlib import Path
import tarfile
import tempfile
from urllib.request import urlopen
from keycloak_realm import VERSION, ARCHIVE_SHA256

parser=argparse.ArgumentParser()
parser.add_argument('--destination',required=True,type=Path)
args=parser.parse_args()
target=args.destination/f'keycloak-{VERSION}'
if target.exists():
    raise SystemExit('Destination exists; refusing to replace an IdP installation')
args.destination.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='silicon-idp-download-') as directory:
    archive=Path(directory)/'keycloak.tar.gz'
    with urlopen(f'https://github.com/keycloak/keycloak/releases/download/{VERSION}/keycloak-{VERSION}.tar.gz',timeout=60) as response:
        archive.write_bytes(response.read())
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=ARCHIVE_SHA256:
        raise SystemExit('Keycloak archive SHA-256 mismatch')
    with tarfile.open(archive) as bundle:
        bundle.extractall(args.destination,filter='data')
print(f'Verified Keycloak {VERSION}; extracted to {target}')

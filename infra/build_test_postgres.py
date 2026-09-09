"""Build the exact test server into a caller-selected temporary prefix."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tarfile
import tempfile
import urllib.request

VERSION = "17.11"
SHA256 = "dd27f2b3c59e73ed14aa3324901242bf69a032a6347805f274e6260322d42979"
parser = argparse.ArgumentParser()
parser.add_argument("--prefix", required=True, type=Path)
args = parser.parse_args()
args.prefix = args.prefix.resolve()
if args.prefix.exists():
    raise SystemExit("Use a new empty prefix; existing installation will not be overwritten")
with tempfile.TemporaryDirectory(prefix="silicon-pg-build-") as temp:
    archive = Path(temp) / "postgresql.tar.bz2"
    with urllib.request.urlopen(f"https://ftp.postgresql.org/pub/source/v{VERSION}/postgresql-{VERSION}.tar.bz2", timeout=60) as source:
        data = source.read()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise SystemExit("PostgreSQL checksum mismatch")
    archive.write_bytes(data)
    with tarfile.open(archive) as tar:
        tar.extractall(temp, filter="data")
    directory = Path(temp) / f"postgresql-{VERSION}"
    for command in [["./configure", f"--prefix={args.prefix}", "--without-icu", "--without-readline", "--without-zlib"], ["make", "-j4"], ["make", "install"]]:
        subprocess.run(command, cwd=directory, check=True)
print(f"PostgreSQL {VERSION} installed at {args.prefix}")

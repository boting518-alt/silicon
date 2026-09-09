"""Create local self-signed TLS files; never modify the system trust store."""
from datetime import datetime, timedelta, timezone
import ipaddress
from pathlib import Path
import sys
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def generate(directory):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    key_path,cert_path=directory/'localhost.key',directory/'localhost.crt'
    if key_path.exists() or cert_path.exists():
        raise FileExistsError('Refusing to replace existing TLS files')
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'SILICON development localhost')])
    now=datetime.now(timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
        .not_valid_after(now+timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False)
        .sign(key,hashes.SHA256()))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    key_path.chmod(0o600)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return key_path,cert_path


if __name__=='__main__':
    generate(sys.argv[1] if len(sys.argv)>1 else '.tools/tls')

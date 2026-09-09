"""Keycloak authorization-code client: bounded HTTP, PKCE, nonce and pinned issuer/RS256."""
import base64
import hashlib
import secrets
import ssl
from urllib.parse import urlencode
import httpx
import jwt


class OIDC:
    def __init__(self, settings):
        self.settings = settings
        self.issuer = settings.oidc_issuer.rstrip('/')
        self.verify = ssl.create_default_context(cafile=settings.oidc_ca_bundle or None)
        self.redirect_uri = settings.public_origin + '/api/v1/auth/callback'

    def metadata(self):
        if not self.issuer:
            raise ValueError('OIDC not configured')
        with httpx.Client(verify=self.verify, timeout=5, follow_redirects=False, trust_env=False) as client:
            r = client.get(self.issuer + '/.well-known/openid-configuration')
            r.raise_for_status()
        data = r.json()
        if data['issuer'] != self.issuer:
            raise ValueError('issuer mismatch')
        # This integration is intentionally Keycloak, not arbitrary discovery endpoints.
        for name, suffix in [('authorization_endpoint','auth'),('token_endpoint','token'),
                             ('jwks_uri','certs'),('end_session_endpoint','logout')]:
            if data[name] != self.issuer + '/protocol/openid-connect/' + suffix:
                raise ValueError('unexpected OIDC endpoint')
        return data

    def authorization(self, state, nonce, verifier):
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        return self.metadata()['authorization_endpoint'] + '?' + urlencode(dict(
            client_id=self.settings.oidc_client_id, response_type='code', scope='openid profile',
            redirect_uri=self.redirect_uri, state=state, nonce=nonce,
            code_challenge=challenge, code_challenge_method='S256'))

    def exchange(self, code, verifier, nonce):
        metadata = self.metadata()
        with httpx.Client(verify=self.verify, timeout=5, follow_redirects=False, trust_env=False) as client:
            response = client.post(metadata['token_endpoint'], data={
                'grant_type':'authorization_code', 'code':code, 'code_verifier':verifier,
                'redirect_uri':self.redirect_uri, 'client_id':self.settings.oidc_client_id,
                'client_secret':self.settings.oidc_client_secret})
            response.raise_for_status()
            token = response.json()['id_token']
            jwks = client.get(metadata['jwks_uri'])
            jwks.raise_for_status()
        header = jwt.get_unverified_header(token)
        keys = [k for k in jwks.json()['keys'] if k.get('kid') == header.get('kid') and k.get('use','sig') == 'sig' and k.get('kty') == 'RSA']
        if len(keys) != 1 or header.get('alg') != 'RS256':
            raise ValueError('invalid signing key')
        claims = jwt.decode(token, jwt.PyJWK.from_dict(keys[0], algorithm='RS256').key,
                            algorithms=['RS256'], audience=self.settings.oidc_client_id, issuer=self.issuer,
                            options={'require':['iss','sub','aud','exp','iat','nonce']})
        if not isinstance(claims['nonce'], str) or not secrets.compare_digest(claims['nonce'], nonce):
            raise ValueError('invalid nonce')
        if not isinstance(claims['sub'], str) or not claims['sub']:
            raise ValueError('invalid subject')
        if claims.get('azp', self.settings.oidc_client_id) != self.settings.oidc_client_id:
            raise ValueError('invalid authorized party')
        if isinstance(claims['aud'], list) and len(claims['aud']) > 1 and 'azp' not in claims:
            raise ValueError('missing authorized party')
        return claims

    def logout_url(self):
        return self.metadata()['end_session_endpoint'] + '?' + urlencode({
            'client_id': self.settings.oidc_client_id,
            'post_logout_redirect_uri': self.settings.public_origin + '/'})

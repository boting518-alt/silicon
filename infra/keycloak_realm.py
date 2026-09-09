"""Fictional development realm, never a production realm export."""
import json
import sys
from pathlib import Path

VERSION = '26.7.3'
ARCHIVE_SHA256 = '77657f30b7e90d70f727712ce1c967f430fd6a5e9f458d32d8c6df0635345f47'
SUBJECT = '11111111-1111-4111-8111-111111111111'


def realm(origin):
    return {
        'realm':'silicon-dev','enabled':True,'sslRequired':'external',
        'accessTokenLifespan':300,'ssoSessionIdleTimeout':600,
        'registrationAllowed':False,'resetPasswordAllowed':False,
        'clients':[{
            'clientId':'silicon-web','enabled':True,'protocol':'openid-connect',
            'publicClient':False,'secret':'fictional-dev-client-secret',
            'standardFlowEnabled':True,'directAccessGrantsEnabled':False,
            'serviceAccountsEnabled':False,
            'redirectUris':[origin+'/api/v1/auth/callback'], 'webOrigins':[origin],
            'attributes':{'pkce.code.challenge.method':'S256',
                          'post.logout.redirect.uris':origin+'/'},
        }],
        'users':[{'id':SUBJECT,'username':'alice','enabled':True,
                  'firstName':'虚构','lastName':'用户甲','email':'alice@example.invalid','emailVerified':True,
                  'credentials':[{'type':'password','value':'Fictional-alice-17!','temporary':False}]}],
    }


if __name__=='__main__':
    target=Path(sys.argv[1])
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(realm(sys.argv[2] if len(sys.argv)>2 else 'https://localhost:5173'),ensure_ascii=False,indent=2)+'\n')

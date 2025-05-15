from datetime import datetime
from calendar import timegm
from graphql_jwt.settings import jwt_settings

def jwt_payload(user, context=None):
    username = user.get_username()
    
    # Get expiration time as a timestamp (integer)
    expiration = datetime.utcnow() + jwt_settings.JWT_EXPIRATION_DELTA
    exp_timestamp = timegm(expiration.utctimetuple())
    
    # Get current time as a timestamp
    orig_iat_timestamp = timegm(datetime.utcnow().utctimetuple())
    
    payload = {
        'username': username,
        'exp': exp_timestamp,  # Use timestamp instead of datetime object
        'orig_iat': orig_iat_timestamp,  # Use timestamp instead of datetime object
        'user_id': str(user.id),
    }
    
    if jwt_settings.JWT_AUDIENCE is not None:
        payload['aud'] = jwt_settings.JWT_AUDIENCE
    
    if jwt_settings.JWT_ISSUER is not None:
        payload['iss'] = jwt_settings.JWT_ISSUER
    
    return payload 
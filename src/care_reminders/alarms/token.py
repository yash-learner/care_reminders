from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

from care_reminders.settings import plugin_settings

SALT = "care_reminders.alarm"


class InvalidToken(Exception):
    pass


def generate(occurrence, action: str) -> str:
    signer = TimestampSigner(salt=SALT)
    return signer.sign_object({"occurrence_id": str(occurrence.external_id), "action": action})


def verify(token: str, occurrence_id: str, action: str) -> dict:
    if not token:
        raise InvalidToken("Missing or expired alarm token.")
    signer = TimestampSigner(salt=SALT)
    try:
        data = signer.unsign_object(token, max_age=int(plugin_settings.ALARM_TOKEN_MAX_AGE))
    except (BadSignature, SignatureExpired, TypeError, ValueError) as error:
        raise InvalidToken("Missing or expired alarm token.") from error
    if str(data.get("occurrence_id")) != str(occurrence_id):
        raise InvalidToken("Alarm token does not match this dose.")
    if str(data.get("action")) != str(action):
        raise InvalidToken("Alarm token does not match this action.")
    return data

"""Public failure messages and private diagnostics without exception payloads."""
import re
import traceback


MESSAGES = {
    'generation_failed': 'We could not create your plan. Please submit a new attempt.',
    'generation_timeout': 'Creating your plan took too long. Please submit a new attempt.',
    'worker_lost_or_deadline': 'Plan generation was interrupted. Please submit a new attempt.',
}


def public_error(code):
    code = code if code in MESSAGES else 'generation_failed'
    return {'code': code, 'message': MESSAGES[code]}


def failure_diagnostics(error, diagnostics, stage):
    # Never store exception messages, request/response bodies, URLs, or frame locals.
    # Detector signals can include customer data, so retain only operational fields.
    def token(value):
        return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_]{1,80}', value) else None

    records = []
    for item in diagnostics[-30:]:
        record = {key: token(item.get(key)) for key in ('stage', 'code', 'step')}
        records.append({key: value for key, value in record.items() if value is not None})
    failure = {'stage': stage, 'error_type': type(error).__name__,
               'frames': [{'function': token(frame.name), 'line': frame.lineno}
                          for frame in traceback.extract_tb(error.__traceback__)[-12:]]}
    status = getattr(error, 'status_code', None)
    if status is None:
        status = getattr(getattr(error, 'response', None), 'status_code', None)
    if type(status) is int:
        failure['http_status'] = status
    records.append(failure)
    return records

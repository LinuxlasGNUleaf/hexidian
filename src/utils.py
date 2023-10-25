import os
import random
import string


def read_password_env(env_name: str):
    if env_name not in os.environ:
        raise EnvironmentError(f'password env variable {env_name} is not set!')
    return os.environ[env_name]


def create_password(pw_type: str, length: int):
    pw_type = pw_type.lower()
    if pw_type == 'num':
        pool = string.digits
    elif pw_type == 'alphanum':
        pool = string.digits + string.ascii_uppercase
    else:
        pool = string.digits + string.ascii_letters + string.punctuation
    pw = ''.join([random.choice(pool) for _ in range(length)])
    return pw

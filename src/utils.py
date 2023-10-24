import logging
import os.path
import random
import string


def read_token_file(token_file: str):
    if not os.path.exists(token_file):
        raise FileNotFoundError(f'Token File {token_file} not found!')
    with open(token_file, 'r') as tk_file:
        lines = [line.strip() for line in tk_file.readlines()]
    return lines if len(lines) > 1 else lines[0]


def create_password(pw_type: str, length: int):
    pw_type = pw_type.lower()
    if pw_type == 'num':
        pool = string.digits
    elif pw_type == 'alphanum':
        pool = string.digits + string.ascii_uppercase
    else:
        pool = string.digits + string.ascii_letters + string.punctuation
    pw = ''.join([random.choice(pool) for _ in range(length)])
    logging.getLogger(__name__).info(pw)
    return pw

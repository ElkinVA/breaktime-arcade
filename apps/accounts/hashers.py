"""Argon2id с параметрами §2.10.2."""

from django.contrib.auth.hashers import Argon2PasswordHasher


class BAArgon2PasswordHasher(Argon2PasswordHasher):
    time_cost = 3
    memory_cost = 65536
    parallelism = 4

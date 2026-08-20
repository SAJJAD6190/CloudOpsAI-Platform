from app.security import hash_password, verify_password


def test_password_hash_round_trip():
    encoded = hash_password("example-password")
    assert encoded != "example-password"
    assert verify_password("example-password", encoded)
    assert not verify_password("wrong-password", encoded)

import requests


def get_mindsdb_session():
    session = requests.Session()
    try:
        yield session
    finally:
        session.close()

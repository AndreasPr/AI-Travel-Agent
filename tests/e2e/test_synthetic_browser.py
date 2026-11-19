"""Synthetic scripted tests of the pipeline, not model behavior."""
import json
import os
from pathlib import Path
import secrets
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright
import pytest


@pytest.mark.parametrize('scenario', ['synthetic'])
def test_playwright_chat_flow(scenario):
    url = os.environ.get('TEST_WEB_URL', 'http://localhost:13100')
    fixture = json.loads(Path('tests/fixtures/synthetic/synthetic_chat.json').read_text())
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        # Avoid external map-tile traffic; this scenario has no coordinates.
        page.route('**/*.tile.openstreetmap.org/**', lambda route: route.abort())
        page.goto(url + '/register')
        email = f'synthetic-{uuid4().hex}@example.invalid'
        password = secrets.token_urlsafe(24)
        page.get_by_label('Email', exact=True).fill(email)
        page.get_by_label('Password', exact=True).fill(password)
        page.get_by_role('button', name='Register').click()
        expect(page.get_by_label('Your next idea')).to_be_visible()
        page.get_by_role('button', name='Log out').click()
        page.get_by_label('Email', exact=True).fill(email)
        page.get_by_label('Password', exact=True).fill(password)
        page.get_by_role('button', name='Log in', exact=True).click()
        page.get_by_label('Your next idea').fill(fixture['request'])
        page.get_by_role('button', name='Let’s plan').click()
        expect(page.get_by_role('region', name='Planning progress')).to_be_visible()
        expect(page.get_by_role('heading', name='Your itinerary')).to_be_visible(timeout=20000)
        expect(page.get_by_role('heading', name='Synthetic Sample Museum')).to_be_visible()
        page.get_by_role('button', name='Source 1 for Synthetic Sample Museum').click()
        expect(page.get_by_role('dialog')).to_be_visible()
        expect(page.get_by_role('dialog')).to_contain_text('Synthetic test content; CC0')
        assert page.evaluate('Object.keys(localStorage).every(key => !/token/i.test(key))')
        browser.close()

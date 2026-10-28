"""
Pinterest Profile Scraper

Scrapes public Pinterest user profiles by parsing HTML page data.
Extracts follower counts, pin counts, bio, and website links.

Features:
- Parses embedded JSON from page source
- No authentication required
- Extracts email and phone from bio text
"""

import requests
from typing import Dict, Optional
import logging
import re
import json

from app.scrapers.stealth import random_user_agent, get_requests_proxies
from app.scrapers.utils import extract_email

logger = logging.getLogger(__name__)


def scrape_profile(username: str) -> Optional[Dict]:
    """
    Fetch Pinterest profile data.

    Args:
        username: Pinterest username
    """
    username = username.strip().lower()

    url = f'https://www.pinterest.com/{username}/'

    headers = {
        'User-Agent': random_user_agent(),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    try:
        r = requests.get(url, headers=headers, timeout=20, proxies=get_requests_proxies())

        if r.status_code == 404:
            logger.error(f"Pinterest user {username} not found")
            return None

        if r.status_code != 200:
            logger.error(f"Pinterest error {r.status_code} for {username}")
            return None

        html = r.text

        if 'User not found' in html or "This page isn't available" in html:
            logger.error(f"Pinterest user {username} not found")
            return None

        return _extract_profile_data(html, username)

    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching Pinterest profile {username}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching Pinterest profile {username}: {e}")
        return None


def _extract_profile_data(html: str, username: str) -> Optional[Dict]:
    """Extract profile data from Pinterest HTML.

    Only trusts a user record whose username matches. The page also embeds
    pins, boards and other accounts, so page-wide regex matches can belong
    to someone else.
    """
    user_data = None

    for script_id in ('__PWS_INITIAL_PROPS__', '__PWS_DATA__'):
        match = re.search(
            rf'<script[^>]*id="{script_id}"[^>]*>(.*?)</script>', html, re.DOTALL
        )
        if not match:
            continue
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        user_data = _find_user_in_pws(data, username)
        if user_data:
            break

    if not user_data:
        logger.error(f"Pinterest profile data not found for {username}")
        return None

    bio = user_data.get('about') or ''

    return {
        'username': username,
        'full_name': user_data.get('full_name') or '',
        'bio': bio,
        'email': _extract_email(bio),
        'website': user_data.get('website_url') or '',
        'follower_count': user_data.get('follower_count') or 0,
        'following_count': user_data.get('following_count') or 0,
        'pin_count': user_data.get('pin_count') or 0,
        'board_count': user_data.get('board_count') or 0,
        'verified': bool(user_data.get('is_verified_merchant')),
        'platform': 'pinterest',
        'profile_url': f'https://pinterest.com/{username}/',
    }


def _find_user_in_pws(data, username: str) -> Optional[Dict]:
    """Find the fullest user record for username in Pinterest page JSON.

    The same user appears many times (as board owner, collaborator, etc.)
    with only a few fields; the full profile record has the most keys.
    """
    best = None
    stack = [(data, 0)]

    while stack:
        node, depth = stack.pop()
        if depth > 20:
            continue

        if isinstance(node, dict):
            node_username = node.get('username')
            if (isinstance(node_username, str)
                    and node_username.lower() == username.lower()
                    and 'follower_count' in node
                    and (best is None or len(node) > len(best))):
                best = node
            stack.extend((v, depth + 1) for v in node.values())
        elif isinstance(node, list):
            stack.extend((v, depth + 1) for v in node)

    return best


_extract_email = extract_email

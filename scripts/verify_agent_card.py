#!/usr/bin/env python3
"""Fetches the agent card from a running tfl-status agent and prints its
skills -- confirms the A2A discovery route works before any caller relies
on it.

Usage: python3 scripts/verify_agent_card.py [base_url]
"""
import sys

import httpx

base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8002"
response = httpx.get(f"{base_url}/.well-known/agent-card.json", timeout=10)
response.raise_for_status()
card = response.json()
print(f"Agent: {card['name']}")
print(f"Skills: {[s['id'] for s in card['skills']]}")

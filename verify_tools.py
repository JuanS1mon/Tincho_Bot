#!/usr/bin/env python
"""Verify tool calling configuration."""
import os
import sys

# Override env vars
os.environ['TOOL_CALLING_TINCHO2'] = 'true'
os.environ['TOOL_CALLING_TINCHO1'] = 'true'

sys.path.insert(0, '.')

from config.settings import settings

print("=" * 70)
print("TOOL CALLING CONFIGURATION")
print("=" * 70)
print(f"\ntool_calling_tincho1: {settings.tool_calling_tincho1}")
print(f"tool_calling_tincho2: {settings.tool_calling_tincho2}")
print(f"tool_calling_marquitos: {settings.tool_calling_marquitos}")
print(f"\nai_model: {settings.ai_model}")
print(f"ai_base_url: {settings.ai_base_url[:50] if settings.ai_base_url else None}...")

print("\n" + "=" * 70)
print("TOOL DEFINITIONS")
print("=" * 70)

from ai.tool_definitions import TINCHO2_TOOLS

print(f"\nTINCHO2 has {len(TINCHO2_TOOLS)} tools:")
for tool in TINCHO2_TOOLS:
    print(f"  - {tool.get('name')}")
    params = tool.get('parameters', {}).get('properties', {})
    if params:
        param_names = list(params.keys())
        print(f"    Parameters: {param_names}")

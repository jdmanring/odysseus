# [UPSTREAM] SearXNG JSON Format Documentation

## Problem
`.env.example` fails to mention that SearXNG's JSON API format must be explicitly enabled in `settings.yml`. Users following the guide will encounter 404 errors on all search requests.

## Fix
Add a critical warning to `.env.example` explaining that `formats: [html, json]` must be enabled in the SearXNG config.

## Status
- [ ] Identified
- [ ] PR ready for upstream `dev` branch

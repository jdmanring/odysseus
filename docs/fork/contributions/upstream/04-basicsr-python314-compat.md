# [UPSTREAM] BasicsR Python 3.14 Compatibility

## Problem
`basicsr` (required by `realesrgan`) is broken on Python 3.14 in two ways:
1. Build-time: `setup.py` uses `exec()+locals()` which fails on 3.14.
2. Runtime: `torchvision.transforms.functional_tensor` was moved to `torchvision.transforms.functional`.

## Fix
Provide a pre-patched wheel for Python 3.14 or implement a version-gated installer in the Cookbook that handles these patches automatically.

## Status
- [ ] Patches verified in this fork (`install-basicsr.sh`)
- [ ] PR ready for upstream `dev` branch

"""python -m mapworkshop.native.capture build: rebuild capture.dll."""
import sys

from mapworkshop.native.capture import build

if sys.argv[1:] != ['build']:
    raise SystemExit(__doc__)
print(build())

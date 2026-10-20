"""Where the JavaScript of the interface is"""

from pathlib import Path

# The npm workspace: `interface-core` (the library) and `interface-app` (the application)
JS_ROOT = Path(__file__).parent / "js"
APP_PATH = JS_ROOT / "interface-app"
CORE_PATH = JS_ROOT / "interface-core"


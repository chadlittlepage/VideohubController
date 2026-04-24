"""py2app setup script for building a standalone macOS .app bundle.

Build with:
    pip3 install py2app
    python3 setup.py py2app

Output: dist/Videohub Controller.app

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from setuptools import setup

APP_NAME = "Videohub Controller"
APP_VERSION = "0.4.0"

BUNDLE_ID = "com.chadlittlepage.videohubcontroller"

APP = ["app_entry.py"]

DATA_FILES = [
    ("assets", ["assets/about_background.jpg"]),
]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "assets/AppIcon.icns",
    "plist": {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleVersion": APP_VERSION,
        "CFBundleShortVersionString": APP_VERSION,
        "NSHumanReadableCopyright": "2026 Chad Littlepage",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "14.0",
        "NSLocalNetworkUsageDescription":
            "Videohub Controller connects to your Blackmagic Videohub "
            "router on the local network to control video routing.",
        "NSBonjourServices": ["_videohub._tcp."],
    },
    "packages": [
        "videohub_controller",
    ],
    "excludes": [
        "tkinter",
    ],
}

setup(
    name=APP_NAME,
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    install_requires=[],
)

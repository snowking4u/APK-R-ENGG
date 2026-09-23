"""AndroidManifest.xml parser (Phase 02).

Reads the **decoded** (text) ``AndroidManifest.xml`` produced by Apktool
and extracts the immutable APK facts the IDE needs for the APK Info panel
and status labels.

The module is deliberately read-only:

* it never writes to or modifies the manifest,
* it never inspects or executes any code in the APK,
* unknown values are reported as ``None`` (rendered as ``N/A`` by the UI);
  nothing is ever fabricated.

Parsing is defensive: malformed or surprisingly structured XML must never
crash the application.
"""

import os

from xml.etree import ElementTree

from app.core.logger import logger


class ManifestInfo:
    """Facts extracted from an ``AndroidManifest.xml``."""

    __slots__ = (
        "source_path",
        "package",
        "version_name",
        "version_code",
        "min_sdk",
        "target_sdk",
        "permissions",
        "activities",
        "services",
        "receivers",
        "providers",
    )

    def __init__(self):
        self.source_path = None
        self.package = None
        self.version_name = None
        self.version_code = None
        self.min_sdk = None
        self.target_sdk = None
        self.permissions = []
        self.activities = []
        self.services = []
        self.receivers = []
        self.providers = []

    @property
    def permission_count(self):
        return len(self.permissions)

    @property
    def activity_count(self):
        return len(self.activities)

    @property
    def service_count(self):
        return len(self.services)

    @property
    def receiver_count(self):
        return len(self.receivers)

    @property
    def provider_count(self):
        return len(self.providers)


def _local_name(tag):
    """Strip an XML namespace from a tag string if one is present."""
    return tag.rsplit("}", 1)[-1] if tag.startswith("{") else tag


_ANDROID_NS = "http://schemas.android.com/apk/res/android"


def _attr(element, *names):
    """Return the first non-None attribute value found, else None.

    Reads both plain attributes (``package``, ``versionCode``) and the
    Android-namespaced form (``android:minSdkVersion`` becomes the
    ElementTree key ``{http://schemas.android.com/apk/res/android}minSdkVersion``).
    """
    for name in names:
        value = element.get(name)
        if value is not None:
            return value
        namespaced = "{%s}%s" % (_ANDROID_NS, name)
        value = element.get(namespaced)
        if value is not None:
            return value
    return None


def _boolish(value):
    """Best-effort parse of an Android boolean string; None on unknown."""
    if value is None:
        return None
    text = value.strip().lower()
    if text in ("true", "1", "yes"):
        return True
    if text in ("false", "0", "no"):
        return False
    return None


def _uses_sdk(element):
    """Return (min_sdk, target_sdk) from a ``uses-sdk`` element."""
    min_sdk = _attr(element, "minSdkVersion", "minSdk")
    target_sdk = _attr(element, "targetSdkVersion", "targetSdk")
    min_value = _coerce_int(min_sdk)
    target_value = _coerce_int(target_sdk)
    return (min_value, target_value)


def _coerce_int(value):
    """Return an int for a numeric string, else None."""
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_manifest_tree(root):
    """Extract ManifestInfo from a parsed ElementTree ``<manifest>`` root."""
    info = ManifestInfo()
    first = True

    for element in root.iter():
        name = _local_name(element.tag)

        if name == "manifest" and first:
            first = False
            info.package = _attr(element, "package")
            info.version_name = _attr(element, "versionName", "versionname")
            info.version_code = _coerce_int(_attr(element, "versionCode", "versioncode"))

        elif name == "uses-sdk":
            min_sdk, target_sdk = _uses_sdk(element)
            info.min_sdk = min_sdk
            info.target_sdk = target_sdk

        elif name == "uses-permission":
            permission = _attr(element, "name")
            if permission:
                permission = permission.strip()
                if permission not in info.permissions:
                    info.permissions.append(permission)

        elif name == "activity":
            component = _attr(element, "name")
            if component:
                info.activities.append(component)

        elif name == "service":
            component = _attr(element, "name")
            if component:
                info.services.append(component)

        elif name == "receiver":
            component = _attr(element, "name")
            if component:
                info.receivers.append(component)

        elif name == "provider":
            component = _attr(element, "name")
            if component:
                info.providers.append(component)

    return info


def parse_manifest_text(text):
    """Parse ``AndroidManifest.xml`` text into a ManifestInfo.

    Never raises. Returns a fully-defaulted ManifestInfo on failure.
    """
    info = ManifestInfo()
    if not text:
        logger.warning("Manifest parse: empty manifest text")
        return info

    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        logger.warning("Manifest parse: invalid XML (%s)" % exc)
        return info

    info = _parse_manifest_tree(root)
    info.source_path = None
    return info


def parse_manifest_file(path):
    """Parse an ``AndroidManifest.xml`` on disk into a ManifestInfo.

    Never raises. Unknown/failed parses return a defaulted ManifestInfo.
    """
    info = ManifestInfo()
    if not path or not os.path.isfile(path):
        logger.warning("Manifest parse: file unavailable: %s" % (path or "None"))
        return info

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError as exc:
        logger.warning("Manifest parse: cannot read %s (%s)" % (path, exc))
        return info

    info = parse_manifest_text(text)
    info.source_path = path
    return info

from __future__ import annotations

import obsws_python as obs


class OBSController:
    """OBS WebSocket v5 controller for one scene item and its opacity filter."""

    FILTER_KIND = "color_filter"

    def __init__(self, host: str, port: int, password: str):
        self.client = obs.ReqClient(
            host=host,
            port=int(port),
            password=password,
            timeout=3
        )
        self.opacity_scale = 1.0

    @staticmethod
    def _field(obj, *names, default=None):
        for name in names:
            if isinstance(obj, dict) and name in obj:
                return obj[name]
            if hasattr(obj, name):
                return getattr(obj, name)
        return default

    def find_scene_item(self, scene_name: str, source_name: str):
        response = self.client.get_scene_item_list(scene_name)
        items = self._field(response, "scene_items", "sceneItems", default=[]) or []
        for item in items:
            name = self._field(item, "sourceName", "source_name")
            if name == source_name:
                return item
        raise RuntimeError(
            f'Could not find source "{source_name}" in scene "{scene_name}". '
            "Check the exact names in OBS."
        )

    def find_scene_item_id(self, scene_name: str, source_name: str) -> int:
        item = self.find_scene_item(scene_name, source_name)
        item_id = self._field(item, "sceneItemId", "scene_item_id")
        if item_id is None:
            raise RuntimeError("OBS did not return a scene item ID.")
        return int(item_id)

    def get_scene_item_enabled(self, scene_name: str, item_id: int) -> bool:
        response = self.client.get_scene_item_list(scene_name)
        items = self._field(response, "scene_items", "sceneItems", default=[]) or []
        for item in items:
            found_id = self._field(item, "sceneItemId", "scene_item_id")
            if found_id is not None and int(found_id) == int(item_id):
                return bool(self._field(item, "sceneItemEnabled", "scene_item_enabled",
                                        default=True))
        return True

    def set_camera_visible(self, scene_name: str, item_id: int, visible: bool):
        self.client.set_scene_item_enabled(
            scene_name,
            int(item_id),
            bool(visible)
        )

    def ensure_opacity_filter(self, source_name: str, filter_name: str):
        """Create a Color Correction filter if needed and detect its opacity scale."""
        response = self.client.get_source_filter_list(source_name)
        filters = self._field(response, "filters", default=[]) or []
        existing = any(
            self._field(item, "filterName", "filter_name", "name") == filter_name
            for item in filters
        )

        if not existing:
            self.client.create_source_filter(
                source_name,
                filter_name,
                self.FILTER_KIND,
                {"opacity": 1.0}
            )

        # OBS modern color_filter uses opacity 0.0-1.0. Some legacy builds
        # expose the older integer 0-100 setting; detect it from defaults.
        try:
            defaults_response = self.client.get_source_filter_default_settings(
                self.FILTER_KIND
            )
            defaults = self._field(
                defaults_response, "default_filter_settings",
                "defaultFilterSettings", default={}
            ) or {}
            default_opacity = defaults.get("opacity", 1.0)
            self.opacity_scale = 100.0 if (
                isinstance(default_opacity, int) and default_opacity > 1
            ) else 1.0
        except Exception:
            self.opacity_scale = 1.0

        self.client.set_source_filter_enabled(source_name, filter_name, True)
        self.set_opacity(source_name, filter_name, 1.0)

    def set_opacity(self, source_name: str, filter_name: str, opacity: float):
        opacity = max(0.0, min(1.0, float(opacity)))
        value = opacity * self.opacity_scale
        self.client.set_source_filter_settings(
            source_name,
            filter_name,
            {"opacity": value},
            True
        )

    def disconnect(self):
        try:
            self.client.disconnect()
        except Exception:
            pass

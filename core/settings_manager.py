from core.config import settings as main_settings
from core.stt_config import stt_settings as initial_stt_settings
from typing import Dict, Any

class SettingsManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
            cls._instance.main_settings = main_settings
            cls._instance.stt_settings = initial_stt_settings.model_copy() # Create a mutable copy
        return cls._instance

    def update_stt_settings(self, new_settings_data: Dict[str, Any]):
        """
        Updates the STT settings at runtime.
        Note: These changes are not persistent across application restarts.
        """
        for key, value in new_settings_data.items():
            if hasattr(self.stt_settings, key):
                setattr(self.stt_settings, key, value)
            else:
                # Log a warning if an unknown setting is passed
                print(f"Warning: Attempted to update unknown STT setting: {key}")

# Create a singleton instance
settings_manager = SettingsManager()

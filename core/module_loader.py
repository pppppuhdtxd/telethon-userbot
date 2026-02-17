# core/module_loader.py
# Loads all modules from the modules directory, calls their setup, and aggregates their help text.

import importlib.util
import os
import logging
from config import MODULES_DIR # فرض کنید این مسیر پوشه modules است
from client import client # برای فراخوانی setup

logger = logging.getLogger(__name__)

# متغیری برای ذخیره متن کمک همه ماژول‌ها
_aggregated_help_texts = []

def load_modules():
    """Loads all modules from the modules directory and aggregates their help text."""
    global _aggregated_help_texts
    modules_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), MODULES_DIR) # از پوشه اصلی به modules می‌رود
    _aggregated_help_texts = [] # ریست کردن لیست قبلی
    for filename in os.listdir(modules_dir):
        if filename.endswith('.py') and not filename.startswith('__'):
            module_name = filename[:-3] # حذف .py
            spec = importlib.util.spec_from_file_location(module_name, os.path.join(modules_dir, filename))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # فعال کردن ماژول (ثبت رویدادها)
            if hasattr(module, 'setup'):
                try:
                    module.setup(client) # فرض بر این است که setup(client) وجود دارد
                    logger.debug(f"Module {module_name} loaded and setup called.")
                except Exception as e:
                    logger.error(f"Error calling setup for module {module_name}: {repr(e)}")

            # خواندن متن کمک
            if hasattr(module, 'HELP_TEXT'):
                _aggregated_help_texts.append(getattr(module, 'HELP_TEXT'))
                logger.debug(f"Help text loaded from {module_name}.")

def get_aggregated_help_texts():
    """Returns the list of help texts collected from all modules."""
    return _aggregated_help_texts
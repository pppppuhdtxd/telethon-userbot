# core/event_manager.py
# Centralized manager for registering event handlers with the client.

import logging
from telethon import events

logger = logging.getLogger(__name__)

def register_handlers(client_instance, handlers_list):
    """
    Registers a list of (event, callback) tuples with the client.
    This provides a central place to attach all dynamically loaded handlers.
    """
    for event_builder, callback in handlers_list:
        try:
            client_instance.add_event_handler(callback, event_builder)
            logger.debug(f"Registered handler for event: {event_builder}")
        except Exception as e:
            logger.error(f"Failed to register handler for {event_builder}: {repr(e)}")
    logger.info(f"Registered {len(handlers_list)} event handlers.")

# Example usage (this would typically be called from module_loader after loading modules):
# handlers = [
#     (events.NewMessage(incoming=True), some_incoming_handler),
#     (events.NewMessage(outgoing=True), some_outgoing_handler),
# ]
# register_handlers(client, handlers)
# client.run_until_disconnected() # or your reconnection loop
\# Telethon Userbot



A modular Telegram userbot built with Telethon.

This project is designed with a plugin-based architecture to allow easy extension and maintenance.



---



\## Overview



\- Language: Python

\- Library: Telethon

\- Architecture: Async, plugin-based

\- Purpose: Managing a Telegram account via independent modules



---



\## Entry Point



\### main.py

The main entry point of the application.

Responsible only for starting the core system.



---



\## Core Architecture



\### client.py

Initializes the Telethon client.



\### core/client\_manager.py

Provides a singleton instance of the Telethon client.

The client is initialized once and shared across the project.



\### core/event\_manager.py

Centralized system for registering Telegram event handlers.

All modules must register events through this manager.



\### core/module\_loader.py

Dynamically loads all modules from the `modules/` directory.



---



\## Modules System



\- Each file in `modules/` represents one independent feature

\- Modules do NOT initialize the client

\- Modules do NOT depend on other modules

\- Modules only interact via `event\_manager`



Examples:

\- auto\_forwarder.py

\- auto\_clearer.py

\- help\_handler.py



---



\## Helpers



The `helpers/` directory contains stateless utility functions

used across the project.



---



\## Execution Flow



main.py  

→ client\_manager  

→ event\_manager  

→ module\_loader  

→ modules/\*.py  



---



\## Architecture Rules (Important)



\- Async-only codebase

\- One shared Telethon client (singleton)

\- Core files should not be modified unless necessary

\- Modules must be isolated and independent



---



\## Goal



To allow easy addition, removal, or modification of features

by simply managing files inside the `modules/` directory.




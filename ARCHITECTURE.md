\# Project Architecture



This document describes the internal architecture and dependency rules

of the Telethon Userbot project.



---



\## Design Style



\- Plugin-based architecture

\- Asynchronous execution

\- Centralized client and event system

\- Loose coupling between features



---



\## Core Components



\### main.py

\- Application entry point

\- Starts the core system

\- Contains no business logic



\### client.py

\- Telethon client initialization



\### core/client\_manager.py

\- Provides a singleton Telethon client

\- Ensures only one client instance exists



\### core/event\_manager.py

\- Centralized registration for all Telegram events

\- Acts as a bridge between modules and Telethon



\### core/module\_loader.py

\- Dynamically loads all modules from the `modules/` directory

\- No module is hardcoded



---



\## Modules Layer



Location: `modules/`



Rules:

\- Each module represents exactly one feature

\- Modules must not initialize the client

\- Modules must not import or depend on other modules

\- Modules communicate only via event\_manager



---



\## Helpers Layer



Location: `helpers/`



Rules:

\- Stateless functions only

\- No side effects

\- Safe to import anywhere



---



\## Dependency Rules (Strict)



Allowed dependencies:



modules  

→ core/event\_manager  



core/event\_manager  

→ core/client\_manager  



core/client\_manager  

→ client  



Disallowed dependencies:



\- modules → modules

\- modules → client

\- modules → main.py



---



\## Modification Policy



\- Core files should only be modified when absolutely necessary

\- New features should be added as new modules

\- Refactoring must preserve module isolation



---



\## Goal



Maintain a stable core while allowing rapid feature development

through independent and replaceable modules.




@echo off
rem SPDX-License-Identifier: Apache-2.0
rem Double-click: show the HUD if it is not running, hide it if it is.
rem ASCII only on purpose: cmd reads .bat files in the console code page.
python "%~dp0hud.py" --toggle %*
if errorlevel 1 pause

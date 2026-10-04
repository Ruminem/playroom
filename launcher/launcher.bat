@echo off
rem SPDX-License-Identifier: Apache-2.0
rem ASCII only on purpose: cmd reads .bat files in the console code page.
start "" pythonw "%~dp0launcher.py"

#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# 맥판 sysmon.bat: Finder 에서 더블클릭하면 켜고, 다시 누르면 끈다.
/usr/bin/python3 "$(dirname "$0")/sysmon.py" --toggle "$@"
# 더블클릭하면 터미널 창이 열려 남으므로 이 창을 닫는다
osascript -e 'tell application "Terminal" to close (every window whose name contains "sysmon.command")' &
exit 0

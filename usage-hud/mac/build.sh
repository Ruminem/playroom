#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# UsageBar.swift 를 이 폴더에 UsageBar 로 묶는다. Xcode 나 Command Line Tools 의 swiftc 가 있어야 함
cd "$(dirname "$0")" && swiftc -O UsageBar.swift -o UsageBar

# -*- coding: utf-8 -*-
"""
System Information Collector - 电脑配置信息采集器
策略: 1.PowerShell Get-CimInstance -> 2.wmic -> 3.platform 模块
"""

import argparse
import copy
import csv
import hashlib
import hmac
import json
import logging
import os
import platform
import subprocess
import sys
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

# Windows 专有模块，延迟导入以支持跨平台检查
msvcrt = None

logger = logging.getLogger(__name__)
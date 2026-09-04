# -*- coding: utf-8 -*-
"""
腾讯云 SCF 入口文件 index.py
将 invoice_scanner.py 的 main_handler 暴露给云函数
"""
from invoice_scanner import main_handler as _main_handler

def main_handler(event, context):
    return _main_handler(event, context)

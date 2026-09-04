#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发票自动扫描云函数
功能：连接企业微信邮箱(IMAP) → 扫描含发票邮件 → 提取附件与信息 → 同步到GitHub Gist
部署：腾讯云 SCF / 阿里云 FC / 本地定时执行
"""

import os
import re
import json
import base64
import imaplib
import email
import requests
from io import BytesIO
from datetime import datetime, timedelta
from email.header import decode_header

# ============ 环境变量配置 ============
IMAP_SERVER = os.environ.get('IMAP_SERVER', 'imap.exmail.qq.com')  # 企业微信邮箱
IMAP_PORT = int(os.environ.get('IMAP_PORT', '993'))
IMAP_USER = os.environ.get('IMAP_USER')          # 邮箱账号
IMAP_PASS = os.environ.get('IMAP_PASS')          # 邮箱密码/客户端专用密码
GITHUB_TOKEN = os.environ.get('GIST_TOKEN') or os.environ.get('GITHUB_TOKEN')    # GitHub Personal Access Token
GIST_ID = os.environ.get('GIST_ID')              # Gist ID
SCAN_DAYS = int(os.environ.get('SCAN_DAYS', '7'))  # 扫描最近N天

# 发票邮件关键词（主题或正文包含即视为发票邮件）
INVOICE_KEYWORDS = ['发票', '电子发票', '增值税', 'invoice', '票号', '开票']

# ============ 日志工具 ============
def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

# ============ 邮件解码 ============
def decode_str(s):
    """解码邮件头中的编码字符串"""
    if not s:
        return ''
    parts = decode_header(s)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            try:
                result.append(part.decode(charset or 'utf-8', errors='ignore'))
            except:
                result.append(part.decode('utf-8', errors='ignore'))
        else:
            result.append(part)
    return ''.join(result)

def get_email_body(msg):
    """获取邮件纯文本正文"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == 'text/plain':
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or 'utf-8'
                    body = payload.decode(charset, errors='ignore')
                    break
                except:
                    continue
            elif content_type == 'text/html' and not body:
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or 'utf-8'
                    html = payload.decode(charset, errors='ignore')
                    # 简单去除HTML标签
                    body = re.sub(r'<[^>]+>', ' ', html)
                except:
                    continue
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or 'utf-8'
            body = payload.decode(charset, errors='ignore')
        except:
            pass
    return body

# ============ PDF 文本提取 ============
def extract_pdf_text(pdf_bytes):
    """从PDF字节中提取文本，优先使用pdfplumber，回退到PyPDF2"""
    text = ""
    # 尝试 pdfplumber（精度更好）
    try:
        import pdfplumber
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        if text.strip():
            return text
    except Exception as e:
        log(f"pdfplumber提取失败: {e}")

    # 回退 PyPDF2
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(BytesIO(pdf_bytes))
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    except Exception as e:
        log(f"PyPDF2提取失败: {e}")

    return text

# ============ 发票信息解析 ============
def parse_invoice(text, subject="", body=""):
    """
    从文本中解析发票关键字段
    返回 dict: {amount, date, invoiceNumber, invoiceCode, seller, buyer, taxAmount, checkCode}
    """
    result = {}
    full_text = f"{subject}\n{body}\n{text}"

    # 1. 发票代码 (10或12位数字)
    code_match = re.search(r'(?:发票代码|代码)[：:\s]*(\d{10,12})', full_text)
    if code_match:
        result['invoiceCode'] = code_match.group(1)

    # 2. 发票号码 (8-20位数字)
    number_match = re.search(r'(?:发票号码|号码|发票号码|No\.?)[：:\s]*(\d{8,20})', full_text)
    if number_match:
        result['invoiceNumber'] = number_match.group(1)

    # 3. 金额 - 多种模式匹配
    # 优先匹配"合计金额"、"价税合计"后面的金额
    amount_patterns = [
        r'(?:价税合计|合计金额|总计|总金额)[（(]大写[)）][^\n]*?([¥￥]\s*[\d,]+\.?\d{0,2})',
        r'(?:价税合计|合计金额|总计)[：:\s]*[¥￥]?\s*([\d,]+\.?\d{0,2})',
        r'[¥￥]\s*([\d,]+\.\d{2})(?=\D*$|\D*\n)',  # 行尾或段尾的 ¥金额
        r'金额[：:\s]*([\d,]+\.?\d{0,2})',
    ]
    for pattern in amount_patterns:
        amt_match = re.search(pattern, full_text)
        if amt_match:
            amt_str = amt_match.group(1).replace(',', '').replace('¥', '').replace('￥', '').strip()
            try:
                result['amount'] = float(amt_str)
                break
            except:
                continue

    # 4. 日期
    date_patterns = [
        r'(\d{4}[年/-]\d{1,2}[月/-]\d{1,2})',
        r'(\d{4}[年/-]\d{1,2}[月/-]\d{1,2}[日]?)',
    ]
    for pattern in date_patterns:
        date_match = re.search(pattern, full_text)
        if date_match:
            date_str = date_match.group(1)
            date_str = date_str.replace('年', '-').replace('月', '-').replace('日', '').replace('/', '-')
            # 标准化为 YYYY-MM-DD
            try:
                parts = date_str.split('-')
                if len(parts) == 3:
                    y, m, d = parts
                    result['date'] = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
                    break
            except:
                continue

    # 5. 销售方名称
    seller_patterns = [
        r'(?:销售方|销方|销售单位)[：:\s]*\n?\s*名称[：:\s]*([^\n]{2,50})',
        r'(?:销售方|销方)[：:\s]*([^\n]{2,50})',
    ]
    for pattern in seller_patterns:
        seller_match = re.search(pattern, full_text)
        if seller_match:
            result['seller'] = seller_match.group(1).strip()
            break

    # 6. 购买方名称
    buyer_patterns = [
        r'(?:购买方|购方|买方)[：:\s]*\n?\s*名称[：:\s]*([^\n]{2,50})',
    ]
    for pattern in buyer_patterns:
        buyer_match = re.search(pattern, full_text)
        if buyer_match:
            result['buyer'] = buyer_match.group(1).strip()
            break

    # 7. 校验码（后6位）
    check_match = re.search(r'校验码[：:\s]*(\d{6,20})', full_text)
    if check_match:
        result['checkCode'] = check_match.group(1)

    # 8. 税额
    tax_match = re.search(r'(?:税额|税金)[：:\s]*([\d,]+\.?\d{0,2})', full_text)
    if tax_match:
        try:
            result['taxAmount'] = float(tax_match.group(1).replace(',', ''))
        except:
            pass

    return result

# ============ GitHub Gist 操作 ============
def get_gist_data():
    """从Gist读取现有发票池和元数据"""
    if not GIST_ID or not GITHUB_TOKEN:
        return {'invoices': [], 'meta': {'lastCheckTime': None}}
    try:
        resp = requests.get(
            f'https://api.github.com/gists/{GIST_ID}',
            headers={'Authorization': f'token {GITHUB_TOKEN}'},
            timeout=30
        )
        if resp.status_code == 200:
            gist = resp.json()
            files = gist.get('files', {})
            result = {'invoices': [], 'meta': {'lastCheckTime': None}}

            if 'invoice_pool.json' in files:
                try:
                    content = files['invoice_pool.json'].get('content', '[]')
                    result['invoices'] = json.loads(content)
                except:
                    pass

            if 'invoice_meta.json' in files:
                try:
                    meta_content = files['invoice_meta.json'].get('content', '{}')
                    result['meta'] = json.loads(meta_content)
                except:
                    pass

            return result
    except Exception as e:
        log(f"读取Gist失败: {e}")
    return {'invoices': [], 'meta': {'lastCheckTime': None}}

def update_gist_data(invoices, meta):
    """更新Gist中的发票池和元数据"""
    if not GIST_ID or not GITHUB_TOKEN:
        return False
    try:
        resp = requests.patch(
            f'https://api.github.com/gists/{GIST_ID}',
            headers={
                'Authorization': f'token {GITHUB_TOKEN}',
                'Content-Type': 'application/json'
            },
            json={
                'files': {
                    'invoice_pool.json': {
                        'content': json.dumps(invoices, ensure_ascii=False, indent=2)
                    },
                    'invoice_meta.json': {
                        'content': json.dumps(meta, ensure_ascii=False, indent=2)
                    }
                }
            },
            timeout=30
        )
        return resp.status_code == 200
    except Exception as e:
        log(f"更新Gist失败: {e}")
        return False

# ============ 主扫描逻辑 ============
def scan_invoices():
    """扫描邮箱中的发票邮件并提取信息"""
    if not all([IMAP_USER, IMAP_PASS, GITHUB_TOKEN, GIST_ID]):
        return {'error': '缺少必要的环境变量，请检查 IMAP_USER/IMAP_PASS/GITHUB_TOKEN/GIST_ID'}

    log("开始连接邮箱...")
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select('INBOX')
        log("邮箱连接成功")
    except Exception as e:
        return {'error': f'邮箱连接失败: {str(e)}'}

    # 读取已有数据
    gist_data = get_gist_data()
    existing_invoices = gist_data.get('invoices', [])
    meta = gist_data.get('meta', {'lastCheckTime': None})

    # 用邮件Message-ID去重
    existing_ids = {inv.get('messageId', '') for inv in existing_invoices}

    # 计算扫描时间范围
    since_date = (datetime.now() - timedelta(days=SCAN_DAYS)).strftime('%d-%b-%Y')
    log(f"扫描 {since_date} 之后的邮件")

    # 搜索邮件（未读+已读，按日期过滤）
    try:
        _, msgnums = mail.search(None, f'(SINCE {since_date})')
        msg_list = msgnums[0].split()
        log(f"找到 {len(msg_list)} 封邮件")
    except Exception as e:
        return {'error': f'搜索邮件失败: {str(e)}'}

    new_invoices = []
    processed_count = 0

    for num in msg_list:
        try:
            _, data = mail.fetch(num, '(RFC822)')
            msg = email.message_from_bytes(data[0][1])

            subject = decode_str(msg.get('Subject', ''))
            from_addr = decode_str(msg.get('From', ''))
            date_str = msg.get('Date', '')
            message_id = msg.get('Message-ID', '') or f"{date_str}_{subject}"

            # 去重检查
            if message_id in existing_ids:
                continue

            # 关键词过滤：主题或正文包含发票关键词
            body = get_email_body(msg)
            full_content = f"{subject} {body}"
            if not any(kw in full_content for kw in INVOICE_KEYWORDS):
                continue

            processed_count += 1
            log(f"处理发票邮件: {subject[:50]}")

            invoice_record = {
                'id': f"inv_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(new_invoices)}",
                'messageId': message_id,
                'subject': subject,
                'from': from_addr,
                'emailDate': date_str,
                'scanTime': datetime.now().isoformat(),
                'attachments': [],
                'parsed': {},
                'status': 'pending',  # pending / matched / failed
                'matchedExpenseId': None,
                'source': 'email'
            }

            # 先尝试从邮件正文解析
            email_parsed = parse_invoice(body, subject, body)
            if email_parsed:
                invoice_record['parsed'].update(email_parsed)
                log(f"  从邮件正文解析到信息: {email_parsed}")

            # 处理附件
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                if part.get('Content-Disposition') is None:
                    continue

                filename = decode_str(part.get_filename())
                if not filename:
                    continue

                # 只处理常见发票格式
                ext = os.path.splitext(filename)[1].lower()
                if ext not in ['.pdf', '.jpg', '.jpeg', '.png', '.ofd']:
                    continue

                try:
                    payload = part.get_payload(decode=True)
                    if not payload:
                        continue

                    # 附件信息（不存完整base64到Gist，只存元数据和前1KB用于预览）
                    attachment = {
                        'filename': filename,
                        'contentType': part.get_content_type(),
                        'size': len(payload),
                        'preview': base64.b64encode(payload[:1024]).decode('utf-8') if len(payload) > 0 else ''
                    }

                    # 对PDF尝试提取文本进一步解析
                    if ext == '.pdf' and len(payload) > 0:
                        pdf_text = extract_pdf_text(payload)
                        if pdf_text:
                            pdf_parsed = parse_invoice(pdf_text, subject, body)
                            # PDF解析结果优先级更高，覆盖邮件解析结果
                            if pdf_parsed:
                                invoice_record['parsed'].update(pdf_parsed)
                                invoice_record['parsed']['_pdfExtracted'] = True
                                log(f"  从PDF提取到信息: {pdf_parsed}")

                    invoice_record['attachments'].append(attachment)
                except Exception as e:
                    log(f"  附件处理失败 {filename}: {e}")

            # 只要有附件或解析到关键信息，就加入发票池
            if invoice_record['attachments'] or invoice_record['parsed'].get('amount'):
                new_invoices.append(invoice_record)
                existing_ids.add(message_id)

        except Exception as e:
            log(f"处理单封邮件失败: {e}")
            continue

    # 关闭邮箱连接
    try:
        mail.close()
        mail.logout()
    except:
        pass

    # 更新Gist
    if new_invoices:
        all_invoices = existing_invoices + new_invoices
        meta['lastCheckTime'] = datetime.now().isoformat()
        meta['lastScanCount'] = len(new_invoices)
        meta['totalInvoiceCount'] = len(all_invoices)

        success = update_gist_data(all_invoices, meta)
        if success:
            log(f"成功同步 {len(new_invoices)} 张新发票到Gist")
        else:
            log("Gist同步失败")

        return {
            'status': 'success',
            'newInvoices': len(new_invoices),
            'totalInvoices': len(all_invoices),
            'scannedEmails': processed_count,
            'gistUpdated': success,
            'invoices': new_invoices
        }
    else:
        # 更新检查时间
        meta['lastCheckTime'] = datetime.now().isoformat()
        update_gist_data(existing_invoices, meta)
        log("未发现新发票")
        return {
            'status': 'success',
            'newInvoices': 0,
            'totalInvoices': len(existing_invoices),
            'scannedEmails': processed_count,
            'gistUpdated': True
        }

# ============ 云函数入口 ============
def main_handler(event, context):
    """
    腾讯云 SCF / 阿里云 FC 入口函数
    event 可包含: {scanDays: 7} 覆盖默认扫描天数
    """
    global SCAN_DAYS
    if event and isinstance(event, dict):
        if 'scanDays' in event:
            SCAN_DAYS = int(event['scanDays'])

    result = scan_invoices()

    return {
        'statusCode': 200 if 'error' not in result else 500,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(result, ensure_ascii=False)
    }

# ============ 本地测试入口 ============
if __name__ == '__main__':
    # 本地测试时可以从环境变量或命令行读取配置
    import sys
    if len(sys.argv) > 1:
        # 支持 python invoice_scanner.py 14 扫描14天
        SCAN_DAYS = int(sys.argv[1])

    result = scan_invoices()
    print(json.dumps(result, ensure_ascii=False, indent=2))

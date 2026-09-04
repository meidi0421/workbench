#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发票解析测试脚本
用于测试发票文本解析功能，不需要连接邮箱
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from invoice_scanner import parse_invoice

# 测试用例
test_cases = [
    {
        'name': '增值税电子普通发票（文本格式）',
        'text': '''
电子发票（普通发票）
发票代码：044032100211
发票号码：20001234
开票日期：2024年03月15日
校 验 码：123456

购买方
名称：某某科技有限公司
纳税人识别号：91440300MA5XXXXXX

销售方
名称：阿里巴巴（中国）有限公司
纳税人识别号：91330100799655058B

项目名称    规格型号    数量    单价    金额    税率    税额
*信息技术服务*云服务器服务费           1    1000.00  1000.00  6%     60.00

价税合计（大写）壹仟零陆拾元整 （小写）¥1060.00
'''
    },
    {
        'name': '发票邮件正文',
        'subject': '您的电子发票已开具 - 订单号20240315001',
        'body': '''
尊敬的客户：

您在我司消费的电子发票已开具，详情如下：

发票金额：¥299.00
发票类型：增值税电子普通发票
开票日期：2024-03-15
发票号码：12345678
销售方：某某有限公司

请查收附件中的PDF发票文件。
'''
    },
    {
        'name': '滴滴出行发票邮件',
        'subject': '【滴滴出行】您的行程电子发票',
        'body': '''
您好，您申请的电子发票已开具：
发票抬头：某某科技有限公司
税号：91440300MA5XXXXXX
金额：¥86.50
开票日期：2024-03-10
发票代码：044032100211
发票号码：20001235
销售方：北京小桔科技有限公司

详见附件。
'''
    },
]

def run_tests():
    print("=" * 60)
    print("发票解析测试")
    print("=" * 60)
    
    passed = 0
    for i, tc in enumerate(test_cases, 1):
        print(f"\n测试 {i}: {tc['name']}")
        print("-" * 40)
        result = parse_invoice(tc.get('text', ''), tc.get('subject', ''), tc.get('body', ''))
        for k, v in result.items():
            print(f"  {k}: {v}")
        
        # 基础校验：至少能解析出金额
        if result.get('amount'):
            print(f"  ✓ 金额解析成功: ¥{result['amount']}")
            passed += 1
        else:
            print(f"  ✗ 金额解析失败")
    
    print("\n" + "=" * 60)
    print(f"测试结果：{passed}/{len(test_cases)} 项解析出金额")
    print("=" * 60)

if __name__ == '__main__':
    run_tests()

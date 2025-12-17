#!/bin/bash
# DuckDNS 域名设置脚本
# 使用方法：
# 1. 访问 https://www.duckdns.org/ 注册账号
# 2. 创建一个域名（例如：podcast-insight）
# 3. 获取你的Token
# 4. 运行此脚本：bash setup_duckdns.sh

echo "=========================================="
echo "DuckDNS 域名设置向导"
echo "=========================================="
echo ""
echo "请先完成以下步骤："
echo "1. 访问 https://www.duckdns.org/"
echo "2. 使用GitHub/Google账号登录"
echo "3. 创建一个域名（例如：podcast-insight）"
echo "4. 复制你的Token"
echo ""
read -p "请输入你的DuckDNS域名（例如：podcast-insight）: " DOMAIN
read -p "请输入你的DuckDNS Token: " TOKEN

if [ -z "$DOMAIN" ] || [ -z "$TOKEN" ]; then
    echo "错误：域名和Token不能为空"
    exit 1
fi

FULL_DOMAIN="${DOMAIN}.duckdns.org"
echo ""
echo "你的完整域名将是: ${FULL_DOMAIN}"
echo ""

# 更新DuckDNS IP
echo "正在更新DuckDNS记录..."
CURRENT_IP=$(curl -s ifconfig.me)
UPDATE_URL="https://www.duckdns.org/update?domains=${DOMAIN}&token=${TOKEN}&ip=${CURRENT_IP}"
RESPONSE=$(curl -s "${UPDATE_URL}")

if [ "$RESPONSE" = "OK" ]; then
    echo "✓ DuckDNS更新成功！"
    echo "  域名: ${FULL_DOMAIN}"
    echo "  IP: ${CURRENT_IP}"
else
    echo "✗ DuckDNS更新失败: ${RESPONSE}"
    exit 1
fi

# 创建DuckDNS更新脚本
cat > /home/wzw/update_duckdns.sh << EOF
#!/bin/bash
# DuckDNS自动更新脚本
# 此脚本会定期更新你的IP地址到DuckDNS

DOMAIN="${DOMAIN}"
TOKEN="${TOKEN}"
CURRENT_IP=\$(curl -s ifconfig.me)
UPDATE_URL="https://www.duckdns.org/update?domains=\${DOMAIN}&token=\${TOKEN}&ip=\${CURRENT_IP}"
RESPONSE=\$(curl -s "\${UPDATE_URL}")

if [ "\$RESPONSE" = "OK" ]; then
    echo "\$(date): DuckDNS updated successfully - \${CURRENT_IP}"
else
    echo "\$(date): DuckDNS update failed - \${RESPONSE}"
fi
EOF

chmod +x /home/wzw/update_duckdns.sh
echo ""
echo "✓ 已创建自动更新脚本: /home/wzw/update_duckdns.sh"

# 设置cron任务（每5分钟更新一次）
(crontab -l 2>/dev/null | grep -v "update_duckdns.sh"; echo "*/5 * * * * /home/wzw/update_duckdns.sh >> /home/wzw/duckdns.log 2>&1") | crontab -
echo "✓ 已设置自动更新任务（每5分钟）"

# 保存配置
cat > /home/wzw/duckdns_config.txt << EOF
DOMAIN=${DOMAIN}
TOKEN=${TOKEN}
FULL_DOMAIN=${FULL_DOMAIN}
EOF

echo ""
echo "=========================================="
echo "配置完成！"
echo "=========================================="
echo "域名: ${FULL_DOMAIN}"
echo "配置已保存到: /home/wzw/duckdns_config.txt"
echo ""
echo "下一步："
echo "1. 等待DNS传播（通常几分钟）"
echo "2. 运行 nginx_setup.sh 配置Nginx反向代理"
echo "3. 测试访问: http://${FULL_DOMAIN}"
echo ""


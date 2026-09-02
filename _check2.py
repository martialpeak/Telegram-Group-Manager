import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('2.27.29.113', port=22, username='root', password='0915951a', timeout=10)

stdin, stdout, stderr = ssh.exec_command("tail -40 /root/Telegram-Group-Manager/bot.log | grep -v getUpdates", timeout=10)
print("=== RECENT LOG ===")
print(stdout.read().decode())

stdin, stdout, stderr = ssh.exec_command("grep -c 'cmd_lock\\|cmd_top\\|cmd_translate\\|cmd_remind\\|cmd_addfilter' /root/Telegram-Group-Manager/main.py /root/Telegram-Group-Manager/bot/handlers/commands.py /root/Telegram-Group-Manager/bot/handlers/__init__.py", timeout=10)
print("=== HANDLER COUNTS ===")
print(stdout.read().decode())

# Check bot process start time vs file change time
stdin, stdout, stderr = ssh.exec_command("ps -o pid,lstart,cmd -C python3.11 | head -3; stat -c '%y %n' /root/Telegram-Group-Manager/main.py", timeout=10)
print("=== PROCESS vs FILE TIME ===")
print(stdout.read().decode())

ssh.close()

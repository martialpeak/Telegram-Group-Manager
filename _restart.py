import paramiko, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('2.27.29.113', port=22, username='root', password='0915951a', timeout=10)

stdin, stdout, stderr = ssh.exec_command("pkill -9 -f 'python3.11 main.py'; sleep 2; echo KILLED", timeout=15)
print("KILL:", stdout.read().decode().strip())

stdin, stdout, stderr = ssh.exec_command("cd /root/Telegram-Group-Manager && python3.11 -m compileall -q bot main.py settings_panel.py config.py i18n.py 2>&1 && echo COMPILE_OK", timeout=30)
print("COMPILE:", stdout.read().decode().strip())

transport = ssh.get_transport()
channel = transport.open_session()
channel.exec_command("cd /root/Telegram-Group-Manager && nohup python3.11 main.py </dev/null > bot.log 2>&1 &")
channel.close()
time.sleep(6)

stdin, stdout, stderr = ssh.exec_command("tail -3 /root/Telegram-Group-Manager/bot.log", timeout=10)
print("LOG:", stdout.read().decode().strip())

# Verify new commands present
stdin, stdout, stderr = ssh.exec_command("grep -c 'cmd_top\\|cmd_lock\\|cmd_translate\\|cmd_remind\\|cmd_addfilter' /root/Telegram-Group-Manager/main.py", timeout=10)
print("NEW HANDLERS in main.py:", stdout.read().decode().strip())

ssh.close()

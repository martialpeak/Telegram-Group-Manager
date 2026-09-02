import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('2.27.29.113', port=22, username='root', password='0915951a', timeout=10)

# Check what git head the server is on
stdin, stdout, stderr = ssh.exec_command("cd /root/Telegram-Group-Manager && git log --oneline -3", timeout=15)
print("GIT LOG:")
print(stdout.read().decode())

# Simple grep test
stdin, stdout, stderr = ssh.exec_command("grep 'cmd_top' /root/Telegram-Group-Manager/main.py | head -2", timeout=10)
print("CMD_TOP in main.py:")
print(stdout.read().decode())

stdin, stdout, stderr = ssh.exec_command("grep 'cmd_lock' /root/Telegram-Group-Manager/bot/handlers/commands.py | head -3", timeout=10)
print("CMD_LOCK in commands.py:")
print(stdout.read().decode())

# Check remote git state
stdin, stdout, stderr = ssh.exec_command("cd /root/Telegram-Group-Manager && git status -sb", timeout=15)
print("STATUS:")
print(stdout.read().decode())

ssh.close()

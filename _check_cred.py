import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('2.27.29.113', port=22, username='root', password='0915951a', timeout=10)

# Check git credential config
stdin, stdout, stderr = ssh.exec_command("cd /root/Telegram-Group-Manager && git config --list | grep -iE 'credential|user' ; ls -la ~/.git-credentials 2>/dev/null; git remote -v", timeout=15)
print("GIT CONFIG:")
print(stdout.read().decode())
print(stderr.read().decode()[:200])

# Check remote URL
stdin, stdout, stderr = ssh.exec_command("cd /root/Telegram-Group-Manager && git config --get remote.origin.url", timeout=10)
print("REMOTE URL:", stdout.read().decode().strip())

ssh.close()

import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('2.27.29.113', port=22, username='root', password='0915951a', timeout=10)

# Check for errors and command usage
stdin, stdout, stderr = ssh.exec_command("grep -iE 'error|traceback|exception|NameError|ImportError|AttributeError' /root/Telegram-Group-Manager/bot.log | tail -30", timeout=10)
print("=== ERRORS ===")
print(stdout.read().decode())

ssh.close()
